/*
 * HEXOS Serve - Servidor HTTP mínimo con SSE
 *
 * Un hilo por conexión: las conexiones SSE viven mucho pero son un puñado,
 * y así el bucle de accept no se bloquea nunca. Sin dependencias externas,
 * como el resto de HEXOS.
 *
 * Rutas:
 *   GET  /                 -> web/index.html
 *   GET  /<fichero>        -> estático desde web_root
 *   GET  /api/events       -> SSE: token, start, end, ready, dead
 *   GET  /api/status       -> JSON con el estado del motor
 *   POST /api/chat         -> cuerpo en texto plano = mensaje del usuario
 *   POST /api/attachment/rgb8 -> RGB8 crudo + cabeceras de geometría
 *   POST /api/command      -> cuerpo en texto plano = comando del REPL
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "hexos_serve.h"
#include "hexos_chats.h"

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

#define MAX_SSE_CLIENTS 16
#define REQ_CAP         (64 * 1024)
#define ATTACHMENT_CAP  ((size_t)300 * 1024 * 1024)

static int             g_listen_fd = -1;
static volatile int    g_running;
static const char     *g_web_root;
static hexos_model_report_t g_model_report;
static bool            g_has_model_report;

static int             g_sse[MAX_SSE_CLIENTS];
static pthread_mutex_t g_sse_lock = PTHREAD_MUTEX_INITIALIZER;

/* ------------------------------------------------------------------------ */

size_t json_escape(const char *in, size_t in_len, char *out, size_t out_cap)
{
    size_t o = 0;
    for (size_t i = 0; i < in_len && o + 8 < out_cap; i++) {
        unsigned char c = (unsigned char)in[i];
        switch (c) {
            case '"':  out[o++] = '\\'; out[o++] = '"';  break;
            case '\\': out[o++] = '\\'; out[o++] = '\\'; break;
            case '\n': out[o++] = '\\'; out[o++] = 'n';  break;
            case '\t': out[o++] = '\\'; out[o++] = 't';  break;
            case '\b': out[o++] = '\\'; out[o++] = 'b';  break;
            case '\f': out[o++] = '\\'; out[o++] = 'f';  break;
            case '\r': break;   /* el REPL no los emite; fuera por si acaso */
            default:
                if (c < 0x20) {
                    o += (size_t)snprintf(out + o, out_cap - o, "\\u%04x", c);
                } else {
                    /* UTF-8 pasa tal cual: ya es válido dentro de un string */
                    out[o++] = (char)c;
                }
        }
    }
    out[o] = '\0';
    return o;
}

static void write_all(int fd, const char *buf, size_t len)
{
    while (len) {
        ssize_t w = send(fd, buf, len, MSG_NOSIGNAL);
        if (w <= 0) {
            if (w < 0 && errno == EINTR) continue;
            return;
        }
        buf += w; len -= (size_t)w;
    }
}

/* ------------------------------------------------------------------------
 * SSE
 * ------------------------------------------------------------------------ */

static void sse_add(int fd)
{
    pthread_mutex_lock(&g_sse_lock);
    for (int i = 0; i < MAX_SSE_CLIENTS; i++) {
        if (g_sse[i] < 0) { g_sse[i] = fd; break; }
    }
    pthread_mutex_unlock(&g_sse_lock);
}

static void sse_remove(int fd)
{
    pthread_mutex_lock(&g_sse_lock);
    for (int i = 0; i < MAX_SSE_CLIENTS; i++) {
        if (g_sse[i] == fd) { g_sse[i] = -1; break; }
    }
    pthread_mutex_unlock(&g_sse_lock);
}

void serve_broadcast(const char *event, const char *json_payload)
{
    char frame[16 * 1024];
    int n = snprintf(frame, sizeof(frame), "event: %s\ndata: %s\n\n",
                     event, json_payload ? json_payload : "{}");
    if (n <= 0) return;

    pthread_mutex_lock(&g_sse_lock);
    for (int i = 0; i < MAX_SSE_CLIENTS; i++) {
        if (g_sse[i] >= 0) write_all(g_sse[i], frame, (size_t)n);
    }
    pthread_mutex_unlock(&g_sse_lock);
}

/* ------------------------------------------------------------------------
 * Respuestas
 * ------------------------------------------------------------------------ */

static void respond(int fd, const char *status, const char *ctype,
                    const char *body, size_t len)
{
    char head[512];
    int n = snprintf(head, sizeof(head),
                     "HTTP/1.1 %s\r\n"
                     "Content-Type: %s\r\n"
                     "Content-Length: %zu\r\n"
                     "Access-Control-Allow-Origin: *\r\n"
                     "Cache-Control: no-store\r\n"
                     "Connection: close\r\n\r\n",
                     status, ctype, len);
    if (n > 0) write_all(fd, head, (size_t)n);
    if (body && len) write_all(fd, body, len);
}

static const char *mime_for(const char *path)
{
    const char *dot = strrchr(path, '.');
    if (!dot) return "application/octet-stream";
    if (!strcmp(dot, ".html")) return "text/html; charset=utf-8";
    if (!strcmp(dot, ".js"))   return "text/javascript; charset=utf-8";
    if (!strcmp(dot, ".css"))  return "text/css; charset=utf-8";
    if (!strcmp(dot, ".json")) return "application/json; charset=utf-8";
    if (!strcmp(dot, ".svg"))  return "image/svg+xml";
    if (!strcmp(dot, ".png"))  return "image/png";
    if (!strcmp(dot, ".jpg") || !strcmp(dot, ".jpeg")) return "image/jpeg";
    if (!strcmp(dot, ".ico"))  return "image/x-icon";
    return "application/octet-stream";
}

static void serve_static(int fd, const char *path)
{
    /* Un ".." en la ruta no es un ataque aquí, es un bug del cliente; se
     * rechaza igual para que un error de camino no sirva medio disco. */
    if (strstr(path, "..")) {
        respond(fd, "400 Bad Request", "text/plain", "ruta inválida", 13);
        return;
    }
    char full[1024];
    snprintf(full, sizeof(full), "%s%s", g_web_root,
             (!strcmp(path, "/")) ? "/index.html" : path);

    FILE *f = fopen(full, "rb");
    if (!f) {
        respond(fd, "404 Not Found", "text/plain", "no está", 7);
        return;
    }
    struct stat st;
    if (stat(full, &st) != 0 || st.st_size < 0) { fclose(f); return; }

    char *body = malloc((size_t)st.st_size);
    if (!body) { fclose(f); return; }
    size_t got = fread(body, 1, (size_t)st.st_size, f);
    fclose(f);
    respond(fd, "200 OK", mime_for(full), body, got);
    free(body);
}

static void serve_status(int fd)
{
    char json[4096];
    size_t used = (size_t)snprintf(json, sizeof(json),
                                  "{\"state\":\"%s\"",
                                  engine_state_name(ruta_state()));
    if (g_has_model_report && used < sizeof(json)) {
        used += (size_t)snprintf(
            json + used, sizeof(json) - used,
            ",\"model\":{\"schema_version\":%u,"
            "\"text_architecture\":\"%s\",\"multimodal\":%s,"
            "\"modalities\":{",
            g_model_report.schema_version,
            g_model_report.text_architecture,
            g_model_report.multimodal ? "true" : "false");
        for (int i = 0; i < HEXOS_MODEL_MODALITY_COUNT && used < sizeof(json); i++) {
            const hexos_modality_capability_t *cap =
                &g_model_report.modalities[i];
            used += (size_t)snprintf(
                json + used, sizeof(json) - used,
                "%s\"%s\":{\"present\":%s,\"status\":\"%s\","
                "\"architecture\":\"%s\",\"adapter\":\"%s\"}",
                i ? "," : "",
                hexos_model_modality_name((hexos_model_modality_t)i),
                cap->present ? "true" : "false",
                hexos_adapter_status_name(cap->status),
                cap->architecture, cap->adapter);
        }
        if (used < sizeof(json)) {
            used += (size_t)snprintf(json + used, sizeof(json) - used, "}}");
        }
    }
    if (used < sizeof(json)) json[used++] = '}';
    else used = sizeof(json) - 1;
    json[used] = '\0';
    respond(fd, "200 OK", "application/json; charset=utf-8", json, used);
}

static void serve_sse(int fd)
{
    static const char head[] =
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: text/event-stream; charset=utf-8\r\n"
        "Cache-Control: no-store\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "X-Accel-Buffering: no\r\n"
        "Connection: keep-alive\r\n\r\n";
    write_all(fd, head, sizeof(head) - 1);

    /* Estado inicial para el que acaba de entrar. */
    char hello[192];
    int n = snprintf(hello, sizeof(hello),
                     "event: state\ndata: {\"state\":\"%s\"}\n\n",
                     engine_state_name(ruta_state()));
    write_all(fd, hello, (size_t)n);

    sse_add(fd);

    /* El hilo se queda aquí: la conexión vive hasta que el cliente la corta
     * o el proceso termina. Un comentario cada 15 s mantiene viva la
     * conexión a través de proxies y detecta el cierre del cliente. */
    while (g_running) {
        sleep(15);
        if (send(fd, ": ping\n\n", 8, MSG_NOSIGNAL) <= 0) break;
    }
    sse_remove(fd);
}

static bool parse_u64_header(const char *headers, size_t header_len,
                             const char *name, uint64_t *value)
{
    const size_t name_len = strlen(name);
    const char *p = headers;
    const char *end = headers + header_len;
    while (p < end) {
        const char *line_end = memchr(p, '\n', (size_t)(end - p));
        if (!line_end) line_end = end;
        if ((size_t)(line_end - p) > name_len &&
            !strncasecmp(p, name, name_len)) {
            const char *number = p + name_len;
            while (number < line_end && (*number == ' ' || *number == '\t')) number++;
            char buffer[32];
            size_t count = (size_t)(line_end - number);
            if (count && number[count - 1] == '\r') count--;
            if (!count || count >= sizeof(buffer)) return false;
            memcpy(buffer, number, count);
            buffer[count] = '\0';
            char *tail = NULL;
            errno = 0;
            unsigned long long parsed = strtoull(buffer, &tail, 10);
            if (errno || !tail || *tail) return false;
            *value = (uint64_t)parsed;
            return true;
        }
        p = line_end < end ? line_end + 1 : end;
    }
    return false;
}

/* ------------------------------------------------------------------------
 * Bucle de conexión
 * ------------------------------------------------------------------------ */

static void *conn_thread(void *arg)
{
    int fd = (int)(intptr_t)arg;
    char req[REQ_CAP];
    size_t len = 0;

    /* Cabeceras completas: hasta \r\n\r\n */
    while (len < sizeof(req) - 1) {
        ssize_t n = recv(fd, req + len, sizeof(req) - 1 - len, 0);
        if (n <= 0) { close(fd); return NULL; }
        len += (size_t)n;
        req[len] = '\0';
        if (strstr(req, "\r\n\r\n")) break;
    }
    req[len] = '\0';

    char method[8] = {0}, path[512] = {0};
    if (sscanf(req, "%7s %511s", method, path) != 2) {
        respond(fd, "400 Bad Request", "text/plain", "", 0);
        close(fd);
        return NULL;
    }

    char *body_start = strstr(req, "\r\n\r\n");
    if (!body_start) {
        respond(fd, "400 Bad Request", "application/json",
                "{\"ok\":false}", 12);
        close(fd);
        return NULL;
    }
    size_t header_len = body_start
        ? (size_t)(body_start + 4 - req) : len;
    size_t body_in_req = body_start ? len - header_len : 0;
    const bool attachment_route =
        !strcmp(method, "POST") && !strcmp(path, "/api/attachment/rgb8");
    uint64_t content_length = 0;
    const bool has_content_length = parse_u64_header(
        req, header_len, "content-length:", &content_length);
    const size_t body_cap = attachment_route ? ATTACHMENT_CAP : REQ_CAP;
    /* Un POST SIN `Content-Length` es un POST sin cuerpo, y eso ahora es
     * normal: las acciones de un chat (activar, liberar, borrar) no llevan
     * nada. Antes se respondía 413 a todas ellas — la regla venía de cuando
     * todo POST traía carga y un tamaño sin declarar era un riesgo de
     * verdad. Sigue siéndolo: por eso se rechaza un `Content-Length`
     * excesivo, y por eso nunca se lee más allá de las cabeceras si no viene
     * declarado. Lo que no puede es rechazar una petición que simplemente no
     * tiene cuerpo. */
    (void)has_content_length;
    if (content_length > body_cap ||
        content_length > SIZE_MAX - 1) {
        respond(fd, "413 Payload Too Large", "application/json",
                "{\"ok\":false}", 12);
        close(fd);
        return NULL;
    }

    size_t body_len = (size_t)content_length;
    unsigned char *body = NULL;
    if (body_len) {
        body = malloc(body_len + 1);
        if (!body) {
            respond(fd, "503 Service Unavailable", "application/json",
                    "{\"ok\":false}", 12);
            close(fd);
            return NULL;
        }
        size_t copied = body_in_req < body_len ? body_in_req : body_len;
        if (copied) memcpy(body, req + header_len, copied);
        while (copied < body_len) {
            ssize_t n = recv(fd, body + copied, body_len - copied, 0);
            if (n < 0 && errno == EINTR) continue;
            if (n <= 0) break;
            copied += (size_t)n;
        }
        if (copied != body_len) {
            free(body);
            close(fd);
            return NULL;
        }
        body[body_len] = '\0';
    }

    if (!strcmp(method, "GET") && !strcmp(path, "/api/events")) {
        serve_sse(fd);
    } else if (!strcmp(method, "GET") && !strcmp(path, "/api/status")) {
        serve_status(fd);
    } else if (!strncmp(path, "/api/chats", 10) && ruta_activa_tipada()) {
        /* Registro de chats. Solo en la ruta tipada: la legacy no tiene
         * sesiones que multiplexar. */
        char *json = malloc(256 * 1024);
        if (!json) { close(fd); free(body); return NULL; }
        size_t n = 0;
        const char *estado = "200 OK";

        if (!strcmp(method, "GET") && !strcmp(path, "/api/chats")) {
            n = chats_listar_json(json, 256 * 1024);
        } else if (!strcmp(method, "POST") && !strcmp(path, "/api/chats")) {
            char id[CHAT_ID_MAX] = "";
            char titulo[CHAT_TITULO_MAX] = "";
            if (body && body_len && body_len < sizeof(titulo))
                memcpy(titulo, body, body_len);
            if (chats_crear(titulo, id, sizeof(id))) {
                n = (size_t)snprintf(json, 256 * 1024, "{\"id\":\"%s\"}", id);
            } else { estado = "409 Conflict"; n = (size_t)snprintf(json, 64, "{\"ok\":false}"); }
        } else {
            /* /api/chats/<id>[/accion] */
            const char *resto = path + 10;
            if (*resto == '/') resto++;
            char id[CHAT_ID_MAX] = "", accion[32] = "";
            const char *barra = strchr(resto, '/');
            const size_t l = barra ? (size_t)(barra - resto) : strlen(resto);
            if (l && l < sizeof(id)) memcpy(id, resto, l);
            if (barra) snprintf(accion, sizeof(accion), "%s", barra + 1);

            bool ok = false;
            if (!strcmp(method, "GET") && !accion[0]) {
                n = chats_json(id, json, 256 * 1024);
                ok = n > 0;
            } else if (!strcmp(method, "POST") && !strcmp(accion, "activar")) {
                /* Activar NO cierra el anterior: queda pausado con su KV.
                 * Pero sí para lo que estuviera generando — mirar otro chat
                 * no puede obligar a esperar a uno que ya no se mira. */
                if (strcmp(id, chats_activo() ? chats_activo() : "")) {
                    rt_cancelar();
                    for (int t = 0; t < 200 && ruta_state() != ENGINE_IDLE; t++)
                        usleep(20000);   /* que la pausa sea real al volver */
                }
                ok = chats_activar(id);
            } else if (!strcmp(method, "POST") && !strcmp(accion, "renombrar")) {
                char t[CHAT_TITULO_MAX] = "";
                if (body && body_len && body_len < sizeof(t))
                    memcpy(t, body, body_len);
                ok = chats_renombrar(id, t);
            } else if (!strcmp(method, "POST") && !strcmp(accion, "liberar")) {
                /* "Liberar memoria", no "cerrar": suelta el KV y NO toca la
                 * conversación. El nombre importa — nadie debe borrar algo
                 * creyendo que solo liberaba VRAM. */
                ok = rt_cerrar_sesion(id);
            } else if (!strcmp(method, "POST") && !strcmp(accion, "cerrar")) {
                /* Libera el KV; la conversación se queda entera. */
                ok = rt_cerrar_sesion(id);
            } else if ((!strcmp(method, "DELETE") && !accion[0]) ||
                       (!strcmp(method, "POST") && !strcmp(accion, "borrar"))) {
                /* Operación distinta y explícita. */
                rt_cerrar_sesion(id);
                ok = chats_borrar(id);
            }
            if (!n) n = (size_t)snprintf(json, 64, "{\"ok\":%s}",
                                         ok ? "true" : "false");
            if (!ok && n <= 16) estado = "404 Not Found";
        }
        respond(fd, estado, "application/json; charset=utf-8", json, n);
        free(json);
    } else if (!strcmp(method, "GET") && !strcmp(path, "/api/memoria")) {
        if (!ruta_activa_tipada()) {
            respond(fd, "404 Not Found", "text/plain", "solo ruta tipada", 16);
        } else {
            char json[2048];
            const size_t n = rt_memoria_json(json, sizeof(json));
            respond(fd, "200 OK", "application/json; charset=utf-8", json, n);
        }
    } else if (!strcmp(method, "POST") && !strcmp(path, "/api/memoria/ensayo")) {
        /* Ensayo, nunca aplicación: devuelve qué diría el almacén. */
        if (!ruta_activa_tipada() || !body || !body_len) {
            respond(fd, "409 Conflict", "application/json", "{\"ok\":false}", 12);
        } else {
            char *json = malloc(64 * 1024);
            if (json) {
                const size_t n = rt_memoria_ensayo((const char *)body, json,
                                                   64 * 1024);
                respond(fd, "200 OK", "application/json; charset=utf-8", json, n);
                free(json);
            }
        }
    } else if (!strcmp(method, "POST") && !strcmp(path, "/api/chat")) {
        bool ok = body && body_len && !memchr(body, '\0', body_len) &&
                  ruta_send((const char *)body);
        respond(fd, ok ? "202 Accepted" : "409 Conflict",
                "application/json", ok ? "{\"ok\":true}" : "{\"ok\":false}",
                ok ? 11 : 12);
    } else if (!strcmp(method, "POST") && !strcmp(path, "/api/command")) {
        bool ok = body && body_len && !memchr(body, '\0', body_len) &&
                  ruta_command((const char *)body);
        respond(fd, ok ? "202 Accepted" : "409 Conflict",
                "application/json", ok ? "{\"ok\":true}" : "{\"ok\":false}",
                ok ? 11 : 12);
    } else if (attachment_route) {
        uint64_t width = 0, height = 0, stride = 0;
        bool geometry =
            parse_u64_header(req, header_len, "x-image-width:", &width) &&
            parse_u64_header(req, header_len, "x-image-height:", &height) &&
            parse_u64_header(req, header_len, "x-image-stride:", &stride) &&
            width <= UINT32_MAX && height <= UINT32_MAX && stride <= SIZE_MAX;
        engine_attachment_t attachment = {
            .kind = ENGINE_ATTACHMENT_RGB8,
            .data = body,
            .byte_size = body_len,
            .width = (uint32_t)width,
            .height = (uint32_t)height,
            .row_stride_bytes = (size_t)stride,
        };
        const bool model_accepts_vision = !g_has_model_report ||
            g_model_report.modalities[HEXOS_MODALITY_VISION].status ==
                HEXOS_ADAPTER_RUNTIME_READY;
        bool ok = geometry && model_accepts_vision && ruta_attach(&attachment);
        respond(fd, ok ? "202 Accepted" : "409 Conflict",
                "application/json", ok ? "{\"ok\":true}" : "{\"ok\":false}",
                ok ? 11 : 12);
    } else if (!strcmp(method, "GET")) {
        serve_static(fd, path);
    } else {
        respond(fd, "405 Method Not Allowed", "text/plain", "", 0);
    }

    free(body);
    close(fd);
    return NULL;
}

/* ------------------------------------------------------------------------ */

bool serve_bind(const char *bind_addr, int port)
{
    signal(SIGPIPE, SIG_IGN);
    for (int i = 0; i < MAX_SSE_CLIENTS; i++) g_sse[i] = -1;

    g_listen_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (g_listen_fd < 0) return false;

    int yes = 1;
    setsockopt(g_listen_fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));

    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_port   = htons((uint16_t)port);
    if (inet_pton(AF_INET, bind_addr, &addr.sin_addr) != 1) {
        fprintf(stderr, "[serve] dirección inválida: %s\n", bind_addr);
        return false;
    }
    if (bind(g_listen_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        fprintf(stderr, "[serve] no pude ocupar %s:%d: %s\n",
                bind_addr, port, strerror(errno));
        fprintf(stderr, "[serve] ¿hay otro hexos_serve vivo? "
                        "pgrep -af hexos_serve\n");
        close(g_listen_fd);
        g_listen_fd = -1;
        return false;
    }
    if (listen(g_listen_fd, 32) < 0) {
        close(g_listen_fd);
        g_listen_fd = -1;
        return false;
    }
    return true;
}

void serve_set_model_report(const hexos_model_report_t *report)
{
    if (!report || !report->valid) {
        memset(&g_model_report, 0, sizeof(g_model_report));
        g_has_model_report = false;
        return;
    }
    g_model_report = *report;
    g_has_model_report = true;
}

bool serve_run(const char *web_root)
{
    if (g_listen_fd < 0) return false;
    g_web_root = web_root;
    g_running = 1;
    while (g_running) {
        int fd = accept(g_listen_fd, NULL, NULL);
        if (fd < 0) {
            if (errno == EINTR) continue;
            break;
        }
        int one = 1;
        setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));

        pthread_t t;
        if (pthread_create(&t, NULL, conn_thread,
                           (void *)(intptr_t)fd) != 0) {
            close(fd);
            continue;
        }
        pthread_detach(t);
    }
    return true;
}

void serve_stop(void)
{
    g_running = 0;
    if (g_listen_fd >= 0) {
        shutdown(g_listen_fd, SHUT_RDWR);
        close(g_listen_fd);
        g_listen_fd = -1;
    }
}
