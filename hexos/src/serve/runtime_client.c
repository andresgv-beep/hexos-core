/*
 * HEXOS Serve — cliente de `helios_runtime` (ruta tipada, E2)
 *
 * Ruta PARALELA a engine.c, no sustituta. La legacy sigue siendo la
 * predeterminada y el oráculo; esta se activa solo con --runtime.
 *
 * Aquí es donde el CK empieza a vivir en el sitio correcto: HexOS clasifica
 * el turno, compone el contrato efímero y manda mensajes tipados. Héctor ya
 * no decide el acto — lo recibe como un `system` cualquiera y no sabe que es
 * un contrato.
 *
 * LÍMITE DECLARADO de E2: esta ruta es cognitivamente incompleta a propósito.
 * Identidad, memoria, reflexión y consolidación siguen atrapadas en
 * `helios_chat` y NO se copian aquí — eso es E3/E5. Parchearlo trayendo los
 * quince prompts del oráculo sería exactamente la "mejora rápida" que el plan
 * prohíbe.
 *
 * El contrato es EFÍMERO: viaja al modelo y muere. No entra en transcripción,
 * ni en memoria, ni en la traza que ve el usuario.
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "hexos_serve.h"
#include "hexos_ck.h"
#include "hera_profile.h"
#include "hera_delta.h"

#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define RT_LINEA_MAX (1024 * 1024)

static pid_t            g_pid = -1;
static int              g_in = -1, g_out = -1;
static FILE            *g_out_f = NULL;
static pthread_t        g_reader;
static pthread_mutex_t  g_lock = PTHREAD_MUTEX_INITIALIZER;
/* Un adjunto son dos escrituras que deben ir pegadas (cabecera + bytes). Con
 * un hilo por conexión, dos subidas a la vez intercalarían los bloques y el
 * runtime leería el payload de una como cabecera de la otra. */
static pthread_mutex_t  g_wr = PTHREAD_MUTEX_INITIALIZER;
/* Un turno entero, de comprobar IDLE a escribirlo, es una sola operación. Con
 * un hilo por conexión, dos POST /api/chat a la vez veían LOS DOS el estado
 * IDLE, los dos pasaban el filtro y los dos mandaban su turno: el runtime
 * recibía dos peticiones pisándose sobre el mismo KV. Mirar el estado y
 * actuar en consecuencia no puede ser dos pasos. */
static pthread_mutex_t  g_turno = PTHREAD_MUTEX_INITIALIZER;
static engine_state_t   g_state = ENGINE_BOOTING;
static engine_chunk_cb  g_on_chunk;
static engine_event_cb  g_on_event;
static engine_notice_cb g_on_notice;
static rt_frame_cb      g_on_frame;      /* telemetría del CK */
static void            *g_user;
static volatile int     g_alive;
static unsigned         g_seq;

/* Estado de artefacto: mismo mecanismo que el oráculo (3 turnos), porque el
 * clasificador lo necesita para distinguir continuación de charla. */
static int  g_artefacto_turnos;
static char g_registro[32] = "neutral";

/* ------------------------------------------------------------------------
 * MEMORIA (E3). Dos cosas gobiernan este cableado:
 *
 * EFÍMERO. El bloque de perfil se compone en la pila de rt_send y muere ahí.
 * No entra en la transcripción canónica, ni en el diario, ni en nada que el
 * usuario vea. Igual que el contrato.
 *
 * EL KV NO SE PARCHEA, SE RECONSTRUYE. Inyectar el perfil en cada turno no
 * solo gasta contexto: no borra nada. Si un hecho se corrige, el viejo sigue
 * FÍSICAMENTE dentro del KV y el modelo lo sigue atendiendo por mucho que le
 * mandemos el nuevo detrás. Cuando el bloque de perfil cambia se manda un
 * `reset` y se rearma el turno con la transcripción canónica más el perfil
 * vigente. Es más caro y es la única forma de que una corrección sea real.
 * ------------------------------------------------------------------------ */

#define TRANSCRIPCION_MAX 64

typedef struct { char rol[16]; char *texto; } linea_t;
static linea_t         g_transcripcion[TRANSCRIPCION_MAX];
static size_t          g_transcripcion_n;
static pthread_mutex_t g_tr_lock = PTHREAD_MUTEX_INITIALIZER;
static char           *g_respuesta;      /* lo que va diciendo este turno */
static size_t          g_respuesta_len, g_respuesta_cap;
static unsigned long long g_perfil_hash;  /* del bloque metido en el KV */
static bool            g_perfil_puesto;
static bool            g_kv_con_algo;   /* ¿hay ya contexto que tirar? */

static unsigned long long hash64(const char *s) {
    unsigned long long h = 1469598103934665603ULL;
    for (const unsigned char *p = (const unsigned char *)s; *p; p++) {
        h ^= *p; h *= 1099511628211ULL;
    }
    return h;
}

/* La transcripción canónica guarda SOLO lo que se dijo: nunca el perfil ni el
 * contrato. Son contexto efímero, y meterlos aquí los volvería permanentes
 * por la puerta de atrás. */
static void transcribir(const char *rol, const char *texto) {
    if (!texto || !*texto) return;
    pthread_mutex_lock(&g_tr_lock);
    if (g_transcripcion_n == TRANSCRIPCION_MAX) {
        free(g_transcripcion[0].texto);
        memmove(&g_transcripcion[0], &g_transcripcion[1],
                sizeof(linea_t) * (TRANSCRIPCION_MAX - 1));
        g_transcripcion_n--;
        if (g_on_notice) {
            const char *aviso = "(la sesión es larga: al reconstruir el "
                                "contexto se perderán los turnos más viejos)";
            g_on_notice(aviso, strlen(aviso), g_user);
        }
    }
    linea_t *l = &g_transcripcion[g_transcripcion_n];
    snprintf(l->rol, sizeof(l->rol), "%s", rol);
    l->texto = strdup(texto);
    if (l->texto) g_transcripcion_n++;
    pthread_mutex_unlock(&g_tr_lock);
}

static void transcripcion_liberar(void) {
    pthread_mutex_lock(&g_tr_lock);
    for (size_t i = 0; i < g_transcripcion_n; i++) free(g_transcripcion[i].texto);
    g_transcripcion_n = 0;
    pthread_mutex_unlock(&g_tr_lock);
}

/* ------------------------------------------------------------------------
 * Toma de traza (HEXOS_RT_TRACE=<fichero>). Escribe lo que sale y lo que
 * entra en el formato que espera tools/protocolo_test.py, para que la
 * conformidad se mida sobre el tráfico REAL de la ruta y no sobre fixtures
 * escritos a mano. El payload de un adjunto no se vuelca: son megabytes de
 * píxeles y la cabecera es lo único que el protocolo comprueba.
 * ------------------------------------------------------------------------ */
static FILE           *g_traza;
static pthread_mutex_t g_traza_lock = PTHREAD_MUTEX_INITIALIZER;

static void trazar(const char *direccion, const char *json_linea) {
    if (!g_traza) return;
    pthread_mutex_lock(&g_traza_lock);
    fprintf(g_traza, "{\"direction\":\"%s\",\"payload\":%s}\n",
            direccion, json_linea);
    fflush(g_traza);
    pthread_mutex_unlock(&g_traza_lock);
}

static bool rt_send_bloqueado(const char *text);

/* Aviso al usuario por su canal propio. Un fallo de memoria no puede quedarse
 * solo en el log del servidor. */
static void avisar(const char *texto) {
    fprintf(stderr, "[serve] %s\n", texto);
    if (g_on_notice) g_on_notice(texto, strlen(texto), g_user);
}

static void set_state(engine_state_t st, const char *event) {
    pthread_mutex_lock(&g_lock);
    g_state = st;
    pthread_mutex_unlock(&g_lock);
    if (event && g_on_event) g_on_event(event, g_user);
}

engine_state_t rt_state(void) {
    pthread_mutex_lock(&g_lock);
    engine_state_t st = g_state;
    pthread_mutex_unlock(&g_lock);
    return st;
}

void rt_set_callbacks(engine_chunk_cb on_chunk, engine_event_cb on_event,
                      engine_notice_cb on_notice, rt_frame_cb on_frame,
                      void *user) {
    g_on_chunk = on_chunk;
    g_on_event = on_event;
    g_on_notice = on_notice;
    g_on_frame = on_frame;
    g_user = user;
}

/* ------------------------------------------------------------------------
 * JSON: escapar salida y extraer los pocos campos que emite el runtime.
 * ------------------------------------------------------------------------ */

static void esc_into(const char *s, char *out, size_t cap) {
    size_t o = 0;
    for (const unsigned char *p = (const unsigned char *)s; *p && o + 8 < cap; p++) {
        switch (*p) {
            case '"':  out[o++] = '\\'; out[o++] = '"';  break;
            case '\\': out[o++] = '\\'; out[o++] = '\\'; break;
            case '\n': out[o++] = '\\'; out[o++] = 'n';  break;
            case '\t': out[o++] = '\\'; out[o++] = 't';  break;
            case '\r': break;
            default:
                if (*p < 0x20) o += (size_t)snprintf(out + o, cap - o, "\\u%04x", *p);
                else out[o++] = (char)*p;
        }
    }
    out[o] = '\0';
}

static bool campo_str(const char *src, const char *clave, char *out, size_t cap) {
    char pat[64];
    snprintf(pat, sizeof(pat), "\"%s\"", clave);
    const char *k = strstr(src, pat);
    if (!k) return false;
    const char *c = strchr(k + strlen(pat), ':');
    if (!c) return false;
    const char *q = strchr(c, '"');
    if (!q) return false;
    size_t o = 0;
    for (const char *p = q + 1; *p && o + 1 < cap; p++) {
        if (*p == '\\') {
            p++;
            if (!*p) break;
            switch (*p) {
                case 'n': out[o++] = '\n'; break;
                case 't': out[o++] = '\t'; break;
                case '"': out[o++] = '"';  break;
                case '\\': out[o++] = '\\'; break;
                default: out[o++] = *p;
            }
            continue;
        }
        if (*p == '"') break;
        out[o++] = *p;
    }
    out[o] = '\0';
    return true;
}

/* ------------------------------------------------------------------------
 * Lector de eventos
 * ------------------------------------------------------------------------ */

static void *reader_thread(void *arg) {
    (void)arg;
    char *linea = malloc(RT_LINEA_MAX);
    if (!linea) return NULL;
    while (g_alive && fgets(linea, RT_LINEA_MAX, g_out_f)) {
        char tipo[32];
        if (!campo_str(linea, "type", tipo, sizeof(tipo))) continue;
        {   /* la línea llega con su '\n'; la traza pone el suyo */
            size_t l = strlen(linea);
            if (l && linea[l - 1] == '\n') linea[l - 1] = '\0';
            trazar("event", linea);
        }

        if (!strcmp(tipo, "ready")) {
            set_state(ENGINE_IDLE, "ready");
        } else if (!strcmp(tipo, "prefill")) {
            set_state(ENGINE_SPEAKING, "start");
        } else if (!strcmp(tipo, "text_delta")) {
            char *texto = malloc(RT_LINEA_MAX);
            if (texto && campo_str(linea, "text", texto, RT_LINEA_MAX)) {
                if (g_on_chunk) g_on_chunk(texto, strlen(texto), g_user);
                /* Se guarda para la transcripción canónica: es lo que habrá
                 * que volver a prefillear si el perfil cambia y hay que
                 * reconstruir el KV. */
                const size_t l = strlen(texto);
                if (g_respuesta_len + l + 1 > g_respuesta_cap) {
                    size_t nc = (g_respuesta_cap ? g_respuesta_cap : 4096);
                    while (nc < g_respuesta_len + l + 1) nc *= 2;
                    char *n = realloc(g_respuesta, nc);
                    if (n) { g_respuesta = n; g_respuesta_cap = nc; }
                }
                if (g_respuesta && g_respuesta_len + l + 1 <= g_respuesta_cap) {
                    memcpy(g_respuesta + g_respuesta_len, texto, l);
                    g_respuesta_len += l;
                    g_respuesta[g_respuesta_len] = '\0';
                }
            }
            free(texto);
        } else if (!strcmp(tipo, "notice")) {
            char aviso[512];
            if (campo_str(linea, "text", aviso, sizeof(aviso)) && g_on_notice) {
                g_on_notice(aviso, strlen(aviso), g_user);
            }
        } else if (!strcmp(tipo, "completed") || !strcmp(tipo, "error")) {
            /* Un `error` de adjunto llega con el motor ya en IDLE. Cerrar el
             * turno ahí emitiría un "end" que la UI cuenta como respuesta
             * terminada — y no había turno. */
            if (rt_state() != ENGINE_IDLE) {
                if (g_respuesta && g_respuesta_len)
                    transcribir("assistant", g_respuesta);
                g_respuesta_len = 0;
                if (g_respuesta) g_respuesta[0] = '\0';
                set_state(ENGINE_IDLE, "end");
            }
        }
    }
    free(linea);
    set_state(ENGINE_DEAD, "dead");
    return NULL;
}

/* ------------------------------------------------------------------------ */

bool rt_start(const char *binary, const char *model, const char *ctx,
              const char *temp) {
    int a[2], b[2];
    if (pipe(a) < 0) return false;
    if (pipe(b) < 0) { close(a[0]); close(a[1]); return false; }

    pid_t pid = fork();
    if (pid < 0) { close(a[0]); close(a[1]); close(b[0]); close(b[1]); return false; }
    if (pid == 0) {
        dup2(a[0], STDIN_FILENO);
        dup2(b[1], STDOUT_FILENO);
        close(a[0]); close(a[1]); close(b[0]); close(b[1]);
        setsid();
        execlp(binary, binary, "--model", model, "--ctx", ctx ? ctx : "4096",
               "--temp", temp ? temp : "0.7", (char *)NULL);
        fprintf(stderr, "[serve] no pude ejecutar %s: %s\n", binary, strerror(errno));
        _exit(127);
    }
    close(a[0]);
    close(b[1]);
    g_pid = pid; g_in = a[1]; g_out = b[0];
    g_out_f = fdopen(g_out, "r");
    if (!g_out_f) return false;
    /* La memoria se abre con la ruta. Si el perfil no es escribible es mejor
     * saberlo aquí que a mitad del primer turno. */
    if (!hera_store_abrir()) {
        fprintf(stderr, "[serve] no pude abrir la memoria del perfil\n");
        return false;
    }
    const size_t importados = hera_store_importar_legacy();
    if (importados) {
        fprintf(stderr, "[serve] %zu recuerdos legacy importados EN CUARENTENA "
                        "(candidatos: no gobiernan nada hasta que los "
                        "confirmes)\n", importados);
    }

    const char *traza = getenv("HEXOS_RT_TRACE");
    if (traza && *traza) {
        g_traza = fopen(traza, "w");
        if (g_traza) fprintf(stderr, "[serve] traza del protocolo → %s\n", traza);
    }
    g_state = ENGINE_BOOTING;
    g_alive = 1;
    return pthread_create(&g_reader, NULL, reader_thread, NULL) == 0;
}

static bool escribir_bytes(const void *p, size_t left) {
    const char *s = (const char *)p;
    while (left) {
        ssize_t w = write(g_in, s, left);
        if (w <= 0) { if (errno == EINTR) continue; return false; }
        s += w; left -= (size_t)w;
    }
    return true;
}

static bool escribir(const char *s) { return escribir_bytes(s, strlen(s)); }

/* ------------------------------------------------------------------------
 * Adjuntos. El runtime los guarda por id y los consume en el turno que los
 * nombra: aquí solo se apunta cuáles están pendientes.
 * ------------------------------------------------------------------------ */

#define RT_ADJUNTOS_MAX 8
static char   g_adjuntos[RT_ADJUNTOS_MAX][32];
static int    g_adjuntos_n;

bool rt_attach(const engine_attachment_t *a) {
    if (!a || a->kind != ENGINE_ATTACHMENT_RGB8 || !a->data || !a->byte_size)
        return false;
    if (g_adjuntos_n >= RT_ADJUNTOS_MAX) return false;
    if (rt_state() != ENGINE_IDLE) return false;

    char id[32];
    snprintf(id, sizeof(id), "a%u", ++g_seq);

    char cab[256];
    int n = snprintf(cab, sizeof(cab),
        "{\"type\":\"attachment\",\"request_id\":\"%s\",\"kind\":\"rgb8\","
        "\"width\":%u,\"height\":%u,\"stride\":%zu,\"bytes\":%zu}\n",
        id, a->width, a->height, a->row_stride_bytes, a->byte_size);
    if (n <= 0) return false;
    cab[n - 1] = '\0'; trazar("request", cab); cab[n - 1] = '\n';

    /* Cabecera y payload van pegados en el mismo flujo: el runtime lee los
     * bytes con read() justo después de la línea. No puede entrar otra
     * escritura en medio. */
    set_state(ENGINE_STAGING, NULL);
    pthread_mutex_lock(&g_wr);
    const bool ok = escribir_bytes(cab, (size_t)n) &&
                    escribir_bytes(a->data, a->byte_size) &&
                    escribir_bytes("\n", 1);
    pthread_mutex_unlock(&g_wr);
    set_state(ENGINE_IDLE, NULL);
    if (!ok) return false;

    snprintf(g_adjuntos[g_adjuntos_n++], sizeof(g_adjuntos[0]), "%s", id);
    return true;
}

bool rt_send(const char *text) {
    pthread_mutex_lock(&g_turno);
    const bool ok_turno = rt_send_bloqueado(text);
    pthread_mutex_unlock(&g_turno);
    return ok_turno;
}

static bool rt_send_bloqueado(const char *text) {
    if (rt_state() != ENGINE_IDLE) return false;

    /* 0. Releer el diario. La memoria puede cambiar desde FUERA de la ruta —
     *    una corrección por CLI hoy, un demonio de consolidación mañana — y
     *    el estado de HERA vive en RAM por proceso. Una ruta que solo leyera
     *    el diario al arrancar seguiría sirviendo un hecho que se corrigió
     *    hace una hora, que es exactamente el fallo que E3 viene a cerrar.
     *    Son unas decenas de líneas: cuesta menos que equivocarse. */
    if (!hera_store_abrir()) {
        /* Sin memoria no se sigue con un perfil vacío: sería contestar como
         * si no supiéramos nada de la persona sin decir que la memoria está
         * rota, y mañana ese turno sería indistinguible de uno normal. */
        avisar("(no puedo abrir tu memoria: el turno no se envía)");
        return false;
    }

    /* 1. Lo que dice la persona se registra como EVIDENCIA. Es lo único que
     *    después podrá respaldar un recuerdo. No crea ningún hecho: sin
     *    aplicador de MemoryDelta, nadie puede escribir memoria por aquí.
     *    Si esto falla, el turno tampoco sale: una conversación cuyas
     *    palabras no se han registrado no puede respaldar ningún recuerdo
     *    después, y el usuario creería que sí. */
    if (!hera_store_dijo(text, NULL, 0)) {
        avisar("(no pude registrar tus palabras: el turno no se envía)");
        return false;
    }

    /* 2. CK clasifica sobre mensaje + estado de artefacto. */
    const bool trae_artefacto =
        strstr(text, "```") != NULL || strlen(text) > 1500;
    const ck_turn_frame_t frame =
        ck_classify_turn(text, false, g_artefacto_turnos > 0,
                         g_adjuntos_n > 0);
    g_artefacto_turnos = trae_artefacto ? 3
                       : (g_artefacto_turnos > 0 ? g_artefacto_turnos - 1 : 0);

    const int vis = ck_visible_token_budget(&frame);
    const int think = ck_thinking_token_budget(&frame, strlen(text));

    /* 3. Perfil vigente. EFÍMERO: vive en esta pila y muere al salir. */
    char perfil[8192];
    const size_t perfil_n = hera_recuperar(perfil, sizeof(perfil), 3000);
    const unsigned long long h = perfil_n ? hash64(perfil) : 0;

    /* ¿Cambió la memoria confirmada desde lo que hay dentro del KV? Entonces
     * no basta con mandar el hecho nuevo: el viejo sigue FÍSICAMENTE en el KV
     * y el modelo lo sigue leyendo. Hay que tirar el KV y rearmarlo desde la
     * transcripción canónica con el perfil de ahora. */
    const bool reconstruir = (!g_perfil_puesto || h != g_perfil_hash);

    /* 4. Telemetría: acto, registro y presupuestos VISIBLES. El contrato no. */
    if (g_on_frame) {
        g_on_frame(ck_response_act_name(frame.act), g_registro, vis, think,
                   g_user);
    }

    /* 5. Contrato efímero. */
    ck_str_t contrato;
    ck_str_init(&contrato);
    if (ck_contract_needed(&frame)) {
        ck_response_contract(&frame, g_registro, NULL, &contrato);
    } else {
        ck_str_append(&contrato, ck_social_steer(&frame));
    }

    /* 6. Mensajes tipados. */
    size_t cap = strlen(text) * 2 + contrato.len * 2 + perfil_n * 2 + 8192;
    pthread_mutex_lock(&g_tr_lock);
    for (size_t i = 0; i < g_transcripcion_n; i++)
        cap += strlen(g_transcripcion[i].texto) * 2 + 64;
    pthread_mutex_unlock(&g_tr_lock);

    char *esc_txt = malloc(cap), *esc_aux = malloc(cap), *linea = malloc(cap * 2);
    if (!esc_txt || !esc_aux || !linea) {
        free(esc_txt); free(esc_aux); free(linea); ck_str_free(&contrato);
        return false;
    }

    int n = snprintf(linea, cap * 2,
        "{\"type\":\"turn\",\"request_id\":\"r%u\",\"messages\":[", ++g_seq);
    const char *coma = "";

    if (reconstruir && perfil_n) {
        esc_into(perfil, esc_aux, cap);
        n += snprintf(linea + n, cap * 2 - n,
                      "{\"role\":\"system\",\"content\":\"%s\"}", esc_aux);
        coma = ",";
    }
    if (reconstruir) {
        /* La transcripción canónica: solo lo que se dijo. Ni perfil ni
         * contrato viejos — esos se recomponen, nunca se replican. */
        pthread_mutex_lock(&g_tr_lock);
        for (size_t i = 0; i < g_transcripcion_n; i++) {
            esc_into(g_transcripcion[i].texto, esc_aux, cap);
            n += snprintf(linea + n, cap * 2 - n,
                          "%s{\"role\":\"%s\",\"content\":\"%s\"}",
                          coma, g_transcripcion[i].rol, esc_aux);
            coma = ",";
        }
        pthread_mutex_unlock(&g_tr_lock);
    }
    if (contrato.len > 0) {
        esc_into(contrato.data ? contrato.data : "", esc_aux, cap);
        n += snprintf(linea + n, cap * 2 - n,
                      "%s{\"role\":\"system\",\"content\":\"%s\"}",
                      coma, esc_aux);
        coma = ",";
    }
    esc_into(text, esc_txt, cap);
    n += snprintf(linea + n, cap * 2 - n,
                  "%s{\"role\":\"user\",\"content\":\"%s\"}]", coma, esc_txt);

    if (g_adjuntos_n > 0) {
        n += snprintf(linea + n, cap * 2 - n, ",\"attachment_ids\":[");
        for (int i = 0; i < g_adjuntos_n; i++)
            n += snprintf(linea + n, cap * 2 - n, "%s\"%s\"",
                          i ? "," : "", g_adjuntos[i]);
        n += snprintf(linea + n, cap * 2 - n, "]");
    }
    n += snprintf(linea + n, cap * 2 - n,
        ",\"generation\":{\"max_visible_tokens\":%d,"
        "\"max_thinking_tokens\":%d}}\n", vis, think);

    if (n > 0 && linea[n - 1] == '\n') {
        linea[n - 1] = '\0'; trazar("request", linea); linea[n - 1] = '\n';
    }

    set_state(ENGINE_THINKING, "thinking");
    pthread_mutex_lock(&g_wr);
    bool ok = true;
    /* El reset SOLO si hay algo viejo dentro. En el primer turno el KV está
     * vacío y resetear no borra nada: sería una ida y vuelta de más y, peor,
     * dejaría el `reset` sin significado. Que aparezca uno tiene que querer
     * decir exactamente una cosa: la memoria cambió y había contexto rancio. */
    if (reconstruir && g_kv_con_algo) {
        /* Va primero y por el mismo cerrojo: si se colara una escritura entre
         * el reset y el turno, el KV se rearmaría a medias. */
        char r[128];
        snprintf(r, sizeof(r),
                 "{\"type\":\"reset\",\"request_id\":\"x%u\"}", g_seq);
        trazar("request", r);
        ok = escribir(r) && escribir("\n");
    }
    ok = ok && escribir(linea);
    pthread_mutex_unlock(&g_wr);

    if (ok) {
        g_adjuntos_n = 0;
        g_perfil_hash = h;
        g_perfil_puesto = true;
        g_kv_con_algo = true;
        transcribir("user", text);
    } else {
        set_state(ENGINE_IDLE, NULL);
    }

    free(esc_txt); free(esc_aux); free(linea);
    ck_str_free(&contrato);   /* el contrato muere aquí */
    return ok;
}

/* Estado de la memoria para telemetría y auditoría. El bloque de perfil NO se
 * expone: es contexto efímero, y publicarlo lo convertiría en un sitio más
 * donde vive la memoria sin reglas. */
size_t rt_memoria_json(char *out, size_t cap) {
    hera_perfil_t p;
    hera_perfil_derivar(&p);
    hera_hecho_t hs[64];
    const size_t t = hera_store_todos(hs, 64);
    size_t candidatos = 0, sustituidos = 0;
    for (size_t i = 0; i < t; i++) {
        if (hs[i].estado == HERA_CANDIDATO)  candidatos++;
        if (hs[i].estado == HERA_SUSTITUIDO) sustituidos++;
    }
    char nombre[HERA_VALOR_MAX * 2];
    esc_into(p.nombre, nombre, sizeof(nombre));
    const int n = snprintf(out, cap,
        "{\"nombre\":\"%s\",\"confirmados\":%zu,\"candidatos\":%zu,"
        "\"sustituidos\":%zu,\"perfil_en_kv\":%s}",
        nombre, p.propias_n + p.ajenas_n, candidatos, sustituidos,
        g_perfil_puesto ? "true" : "false");
    return (n > 0) ? (size_t)n : 0;
}

/* Ensayo de un MemoryDelta: devuelve los veredictos SIN aplicar nada. No hay
 * aplicador en E3 y esto no lo es — es la ventana para ver qué diría el
 * almacén si algún día se conectara la reflexión. */
size_t rt_memoria_ensayo(const char *json_delta, char *out, size_t cap) {
    hera_delta_t d;
    hera_delta_leer(json_delta, &d);
    int n = snprintf(out, cap, "{\"bien_formado\":%s,\"aplicado\":false,\"ops\":[",
                     d.bien_formado ? "true" : "false");
    for (size_t i = 0; i < d.n && (size_t)n < cap; i++) {
        char clave[HERA_CLAVE_MAX * 2];
        esc_into(d.ops[i].clave, clave, sizeof(clave));
        n += snprintf(out + n, cap - n,
                      "%s{\"op\":\"%s\",\"clave\":\"%s\",\"veredicto\":\"%s\"}",
                      i ? "," : "", hera_op_nombre(d.ops[i].op), clave,
                      hera_veredicto_nombre(d.ops[i].veredicto));
    }
    n += snprintf(out + n, cap - n, "],\"aceptables\":%zu}", d.aceptables);
    return (n > 0) ? (size_t)n : 0;
}

void rt_set_registro(const char *registro) {
    if (!registro || !*registro) return;
    snprintf(g_registro, sizeof(g_registro), "%s", registro);
}

void rt_stop(void) {
    g_alive = 0;
    if (g_in >= 0) {
        /* También se traza: sin esto su `result` aparecía en la traza sin
         * petición que lo justificara, y la conformidad lo cantaba con razón. */
        trazar("request", "{\"type\":\"shutdown\",\"request_id\":\"q\"}");
        escribir("{\"type\":\"shutdown\",\"request_id\":\"q\"}\n");
        close(g_in);
        g_in = -1;
    }
    if (g_pid > 0) {
        for (int i = 0; i < 60; i++) {
            if (waitpid(g_pid, NULL, WNOHANG) == g_pid) { g_pid = -1; break; }
            usleep(100000);
        }
        if (g_pid > 0) { kill(g_pid, SIGTERM); waitpid(g_pid, NULL, 0); g_pid = -1; }
    }
    if (g_out_f) { fclose(g_out_f); g_out_f = NULL; g_out = -1; }
    if (g_traza) { fclose(g_traza); g_traza = NULL; }
    transcripcion_liberar();
    free(g_respuesta); g_respuesta = NULL;
    g_respuesta_len = g_respuesta_cap = 0;
    g_perfil_puesto = false;
    g_kv_con_algo = false;
    hera_store_cerrar();
}

/* ------------------------------------------------------------------------
 * Despacho legacy / tipada. La legacy es la PREDETERMINADA y el oraculo; la
 * tipada solo se activa con --runtime.
 * ------------------------------------------------------------------------ */

static bool g_ruta_tipada;

void ruta_usar_tipada(bool tipada) { g_ruta_tipada = tipada; }
bool ruta_activa_tipada(void) { return g_ruta_tipada; }
bool ruta_send(const char *text) {
    return g_ruta_tipada ? rt_send(text) : engine_send(text);
}
bool ruta_attach(const engine_attachment_t *a) {
    return g_ruta_tipada ? rt_attach(a) : engine_attach(a);
}
/* Los comandos son del REPL de helios_chat: /fast, /memoria, /salir. La ruta
 * tipada no tiene REPL — el protocolo es de eventos y no hay nada equivalente
 * que ejecutar. Se rechaza en vez de fingir que se hizo. */
bool ruta_command(const char *cmd) {
    return g_ruta_tipada ? false : engine_command(cmd);
}
engine_state_t ruta_state(void) {
    return g_ruta_tipada ? rt_state() : engine_state();
}
