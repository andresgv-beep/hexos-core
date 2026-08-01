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
 *   POST /api/command      -> cuerpo en texto plano = comando del REPL
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "hexos_serve.h"

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

static int             g_listen_fd = -1;
static volatile int    g_running;
static const char     *g_web_root;

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
    char json[256];
    int n = snprintf(json, sizeof(json), "{\"state\":\"%s\"}",
                     engine_state_name(engine_state()));
    respond(fd, "200 OK", "application/json; charset=utf-8", json, (size_t)n);
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
                     engine_state_name(engine_state()));
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

    char *body = strstr(req, "\r\n\r\n");
    size_t body_len = 0;
    if (body) {
        body += 4;
        body_len = len - (size_t)(body - req);
        /* Si el cuerpo venía partido, se completa con Content-Length. */
        const char *cl = strcasestr(req, "content-length:");
        if (cl) {
            size_t want = (size_t)atol(cl + 15);
            while (body_len < want && len < sizeof(req) - 1) {
                ssize_t n = recv(fd, req + len, sizeof(req) - 1 - len, 0);
                if (n <= 0) break;
                len += (size_t)n;
                body_len += (size_t)n;
            }
            req[len] = '\0';
            if (body_len > want) body_len = want;
        }
        body[body_len] = '\0';
    }

    if (!strcmp(method, "GET") && !strcmp(path, "/api/events")) {
        serve_sse(fd);
    } else if (!strcmp(method, "GET") && !strcmp(path, "/api/status")) {
        serve_status(fd);
    } else if (!strcmp(method, "POST") && !strcmp(path, "/api/chat")) {
        bool ok = body && body_len && engine_send(body);
        respond(fd, ok ? "202 Accepted" : "409 Conflict",
                "application/json", ok ? "{\"ok\":true}" : "{\"ok\":false}",
                ok ? 11 : 12);
    } else if (!strcmp(method, "POST") && !strcmp(path, "/api/command")) {
        bool ok = body && body_len && engine_command(body);
        respond(fd, ok ? "202 Accepted" : "409 Conflict",
                "application/json", ok ? "{\"ok\":true}" : "{\"ok\":false}",
                ok ? 11 : 12);
    } else if (!strcmp(method, "GET")) {
        serve_static(fd, path);
    } else {
        respond(fd, "405 Method Not Allowed", "text/plain", "", 0);
    }

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
