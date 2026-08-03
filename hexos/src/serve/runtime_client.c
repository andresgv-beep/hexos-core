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
#include "hexos_chats.h"
#include "hera_profile.h"
#include "hera_queue.h"
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
static pthread_mutex_t  g_turno_lock = PTHREAD_MUTEX_INITIALIZER;
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

/* La transcripcion canonica ya NO vive aqui: la lleva el registro de chats,
 * que es durable y sobrevive a que muera Hector. Aqui solo queda el
 * acumulador de la respuesta en curso y el rastro de que perfil se metio en
 * el KV de cada chat. */

typedef struct {
    char id[CHAT_ID_MAX];
    unsigned long long perfil_hash;
} kv_chat_t;

#define KV_CHATS_MAX 64
static kv_chat_t       g_kv[KV_CHATS_MAX];
static size_t          g_kv_n;
static pthread_mutex_t g_tr_lock = PTHREAD_MUTEX_INITIALIZER;
static char           *g_respuesta;      /* lo que va diciendo este turno */
static size_t          g_respuesta_len, g_respuesta_cap;
static char            g_chat_en_curso[CHAT_ID_MAX];

/* Entrada congelada del turno en vuelo, para encolarlo a reflexión cuando
 * termine BIEN. Se guarda al enviar porque después ya no se puede reconstruir
 * con fidelidad: el perfil habrá podido cambiar y el marco es de este turno.
 * Ni contrato ni razonamiento — el job no tiene dónde meterlos. */
static struct {
    char mensaje[HERA_JOB_TEXTO_MAX];
    char acto[32], registro[32];
    int  vis, think;
    char evidencia[HERA_ID_MAX];
    char perfil_hash[24];
    unsigned turno;
    bool listo;
} g_turno;

static unsigned long long hash64(const char *s) {
    unsigned long long h = 1469598103934665603ULL;
    for (const unsigned char *p = (const unsigned char *)s; *p; p++) {
        h ^= *p; h *= 1099511628211ULL;
    }
    return h;
}

static kv_chat_t *kv_de(const char *id) {
    for (size_t i = 0; i < g_kv_n; i++)
        if (strcmp(g_kv[i].id, id) == 0) return &g_kv[i];
    if (g_kv_n >= KV_CHATS_MAX) return NULL;
    kv_chat_t *k = &g_kv[g_kv_n++];
    memset(k, 0, sizeof(*k));
    snprintf(k->id, sizeof(k->id), "%s", id);
    return k;
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

/* Nombre corto del perfil: el último tramo de HELIOS_HOME. Es lo que hace que
 * el id del job sea `perfil/sesion/turno` y no una ruta entera. */
static const char *perfil_corto(void) {
    const char *h = getenv("HELIOS_HOME");
    if (!h || !*h) return "default";
    const char *b = strrchr(h, '/');
    return (b && b[1]) ? b + 1 : h;
}

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
                /* Lo dicho va al registro durable, no a una lista en RAM que
                 * muere con el proceso. Se anota tambien lo cancelado a
                 * medias: representarlo honestamente es parte del trato. */
                char razon_fin[32] = "";
                campo_str(linea, "finish_reason", razon_fin, sizeof(razon_fin));
                if (g_respuesta && g_respuesta_len && g_chat_en_curso[0]) {
                    /* Se guarda lo que alcanzó a decir, MARCADO como detenido
                     * si se cortó. Enseñarlo como una respuesta entera sería
                     * mentir sobre lo que dijo. */
                    chats_anotar_estado(g_chat_en_curso, "assistant",
                                        g_respuesta,
                                        !strcmp(razon_fin, "cancelled"));
                }

                /* REFLEXIÓN: solo tras un `completed` normal. Nada después de
                 * un error ni de una cancelación — reflexionar sobre media
                 * respuesta es reflexionar sobre algo que no ocurrió. Y va
                 * DESPUÉS de emitir el texto: encolar no puede retrasar lo que
                 * el usuario está esperando. Encolar no ejecuta nada: no hay
                 * trabajador todavía. */
                if (!strcmp(tipo, "completed") && strcmp(razon_fin, "cancelled") &&
                    g_turno.listo && g_chat_en_curso[0]) {
                    hera_job_t j;
                    memset(&j, 0, sizeof(j));
                    snprintf(j.perfil, sizeof(j.perfil), "%s",
                             hera_store_ruta());
                    snprintf(j.sesion, sizeof(j.sesion), "%s", g_chat_en_curso);
                    j.turno = g_turno.turno;
                    snprintf(j.id, sizeof(j.id), "%s/%s/%u",
                             perfil_corto(), g_chat_en_curso, j.turno);
                    snprintf(j.mensaje, sizeof(j.mensaje), "%s", g_turno.mensaje);
                    snprintf(j.respuesta, sizeof(j.respuesta), "%s",
                             g_respuesta ? g_respuesta : "");
                    snprintf(j.acto, sizeof(j.acto), "%s", g_turno.acto);
                    snprintf(j.registro, sizeof(j.registro), "%s", g_turno.registro);
                    j.visible_budget = g_turno.vis;
                    j.thinking_budget = g_turno.think;
                    snprintf(j.evidencia, sizeof(j.evidencia), "%s",
                             g_turno.evidencia);
                    snprintf(j.perfil_hash, sizeof(j.perfil_hash), "%s",
                             g_turno.perfil_hash);
                    snprintf(j.perfil, sizeof(j.perfil), "%s", perfil_corto());
                    hera_cola_encolar(&j);
                }
                g_turno.listo = false;
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

    if (!hera_cola_abrir()) {
        fprintf(stderr, "[serve] no pude abrir la cola de reflexión\n");
        return false;
    }
    if (!chats_abrir()) {
        fprintf(stderr, "[serve] no pude abrir el registro de chats\n");
        return false;
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
    pthread_mutex_lock(&g_turno_lock);
    const bool ok_turno = rt_send_bloqueado(text);
    pthread_mutex_unlock(&g_turno_lock);
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
    char ev_id[HERA_ID_MAX] = "";
    if (!hera_store_dijo(text, ev_id, sizeof(ev_id))) {
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

    /* 3. Chat activo. Sin ninguno, se crea uno: escribir es abrir conversación,
     *    y obligar a crearla antes seria ceremonia. */
    /* COPIA, no el puntero. `chats_activo()` devuelve el buffer estático del
     * registro: si otro hilo activa un chat a mitad de este turno, una
     * variable local que apuntara ahí cambiaría de valor sola y lo dicho se
     * anotaría en el chat equivocado. Justo lo que pasa al cambiar de chat
     * mientras el motor genera, que es el caso normal, no el raro. */
    char chat[CHAT_ID_MAX];
    snprintf(chat, sizeof(chat), "%s", chats_activo() ? chats_activo() : "");
    if (!chat[0]) {
        if (!chats_crear(NULL, chat, sizeof(chat))) {
            avisar("(no puedo abrir un chat: el turno no se envia)");
            return false;
        }
        chats_activar(chat);
    }
    snprintf(g_chat_en_curso, sizeof(g_chat_en_curso), "%s", chat);

    /* 4. Perfil vigente. EFÍMERO: vive en esta pila y muere al salir. */
    char perfil[8192];
    const size_t perfil_n = hera_recuperar(perfil, sizeof(perfil), 3000);
    const unsigned long long h = perfil_n ? hash64(perfil) : 0;

    /* ¿Cambió la memoria confirmada desde lo que hay dentro del KV? Entonces
     * no basta con mandar el hecho nuevo: el viejo sigue FÍSICAMENTE en el KV
     * y el modelo lo sigue leyendo. Hay que tirar el KV y rearmarlo desde la
     * transcripción canónica con el perfil de ahora. */
    /* Se reconstruye por DOS motivos distintos, y conviene no confundirlos:
     *   · la memoria confirmada cambio -> el KV lleva un hecho ya corregido;
     *   · este chat no tiene sesion viva -> o nunca la tuvo, o se cerro, o
     *     Hector murio y se llevo todas. En ese caso hay que rehacer el
     *     contexto desde la transcripcion durable: es lo que convierte una
     *     sesion vacia del motor en el chat que la persona recuerda. */
    pthread_mutex_lock(&g_tr_lock);
    kv_chat_t *kv = kv_de(chat);
    const bool viva = chats_sesion_viva(chat);
    const bool reconstruir = !viva || !kv || kv->perfil_hash != h;
    pthread_mutex_unlock(&g_tr_lock);

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
    const chat_t *info_chat = chats_buscar(chat);
    size_t cap = strlen(text) * 2 + contrato.len * 2 + perfil_n * 2 + 8192;
    if (info_chat)
        for (size_t i = 0; i < info_chat->lineas_n; i++)
            cap += strlen(info_chat->lineas[i].texto) * 2 + 64;

    char *esc_txt = malloc(cap), *esc_aux = malloc(cap), *linea = malloc(cap * 2);
    if (!esc_txt || !esc_aux || !linea) {
        free(esc_txt); free(esc_aux); free(linea); ck_str_free(&contrato);
        return false;
    }

    char chat_esc[CHAT_ID_MAX * 2];
    esc_into(chat, chat_esc, sizeof(chat_esc));
    int n = snprintf(linea, cap * 2,
        "{\"type\":\"turn\",\"request_id\":\"r%u\",\"session\":\"%s\","
        "\"messages\":[", ++g_seq, chat_esc);
    const char *coma = "";

    if (reconstruir && perfil_n) {
        esc_into(perfil, esc_aux, cap);
        n += snprintf(linea + n, cap * 2 - n,
                      "{\"role\":\"system\",\"content\":\"%s\"}", esc_aux);
        coma = ",";
    }
    if (reconstruir && info_chat) {
        /* La transcripción canónica del REGISTRO: solo lo que se dijo. Ni
         * perfil ni contrato viejos — esos se recomponen, nunca se replican. */
        for (size_t i = 0; i < info_chat->lineas_n; i++) {
            esc_into(info_chat->lineas[i].texto, esc_aux, cap);
            n += snprintf(linea + n, cap * 2 - n,
                          "%s{\"role\":\"%s\",\"content\":\"%s\"}",
                          coma, info_chat->lineas[i].rol, esc_aux);
            coma = ",";
        }
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
    if (reconstruir && viva) {
        /* Va primero y por el mismo cerrojo: si se colara una escritura entre
         * el reset y el turno, el KV se rearmaría a medias. */
        char r[128];
        snprintf(r, sizeof(r),
                 "{\"type\":\"reset\",\"request_id\":\"x%u\",\"session\":\"%s\"}",
                 g_seq, chat_esc);
        trazar("request", r);
        ok = escribir(r) && escribir("\n");
    }
    ok = ok && escribir(linea);
    pthread_mutex_unlock(&g_wr);

    if (ok) {
        const chat_t *ci = chats_buscar(chat);
        g_turno.listo = true;
        g_turno.turno = (unsigned)(ci ? ci->lineas_n : 0);
        snprintf(g_turno.mensaje, sizeof(g_turno.mensaje), "%s", text);
        snprintf(g_turno.acto, sizeof(g_turno.acto), "%s",
                 ck_response_act_name(frame.act));
        snprintf(g_turno.registro, sizeof(g_turno.registro), "%s", g_registro);
        g_turno.vis = vis;
        g_turno.think = think;
        snprintf(g_turno.evidencia, sizeof(g_turno.evidencia), "%s", ev_id);
        snprintf(g_turno.perfil_hash, sizeof(g_turno.perfil_hash), "%llx", h);

        g_adjuntos_n = 0;
        pthread_mutex_lock(&g_tr_lock);
        if (kv) kv->perfil_hash = h;
        pthread_mutex_unlock(&g_tr_lock);
        chats_marcar_sesion(chat, true);
        chats_titular_por_mensaje(chat, text);   /* antes de anotar: mira si es el primero */
        chats_anotar(chat, "user", text);
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
        chats_sesion_viva(chats_activo()) ? "true" : "false");
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

/* Cancela lo que se esté generando. Es lo que convierte "activar otro chat"
 * en una pausa de verdad: sin esto, el motor sigue ocupado, el chat nuevo
 * recibe un 409 y la persona tiene que esperar a que termine algo que ya no
 * está mirando. La cancelación es la de siempre: para en un límite de token y
 * conserva lo emitido. */
bool rt_cancelar(void) {
    if (rt_state() == ENGINE_IDLE || rt_state() == ENGINE_DEAD) return false;
    /* El objetivo se calcula ANTES de tocar el contador: `++g_seq` y
     * `g_seq - 1` en la misma expresión es orden de evaluación indefinido, y
     * el cancel podía apuntar a un turno que no era. */
    const unsigned objetivo = g_seq;
    char linea[160];
    snprintf(linea, sizeof(linea),
             "{\"type\":\"cancel\",\"request_id\":\"x%u\",\"target\":\"r%u\"}",
             ++g_seq, objetivo);
    trazar("request", linea);
    pthread_mutex_lock(&g_wr);
    const bool ok = escribir(linea) && escribir("\n");
    pthread_mutex_unlock(&g_wr);
    return ok;
}

bool rt_cerrar_sesion(const char *chat) {
    if (!chat || !*chat) return false;
    if (!chats_sesion_viva(chat)) { chats_cerrar_sesion(chat); return true; }
    char linea[256], id[CHAT_ID_MAX * 2];
    esc_into(chat, id, sizeof(id));
    snprintf(linea, sizeof(linea),
             "{\"type\":\"session_close\",\"request_id\":\"k%u\","
             "\"session\":\"%s\"}", ++g_seq, id);
    trazar("request", linea);
    pthread_mutex_lock(&g_wr);
    const bool ok = escribir(linea) && escribir("\n");
    pthread_mutex_unlock(&g_wr);
    if (ok) {
        chats_cerrar_sesion(chat);
        pthread_mutex_lock(&g_tr_lock);
        kv_chat_t *k = kv_de(chat);
        if (k) k->perfil_hash = 0;
        pthread_mutex_unlock(&g_tr_lock);
    }
    return ok;
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
    free(g_respuesta); g_respuesta = NULL;
    g_respuesta_len = g_respuesta_cap = 0;
    g_kv_n = 0;
    hera_store_cerrar();
    hera_cola_cerrar();
    chats_cerrar();
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
