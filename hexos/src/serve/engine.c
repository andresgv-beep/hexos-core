/*
 * HEXOS Serve - Driver del motor
 *
 * Lanza helios_chat con tuberías y traduce su salida de terminal a eventos
 * limpios. Todo el conocimiento sucio del REPL vive aquí:
 *
 *   - "helios> " (magenta) abre la respuesta
 *   - "tú> "     (cian)    cierra el turno y pide entrada
 *   - el resto son códigos ANSI de color que la web no necesita
 *
 * Es deliberadamente un parser y no un cambio en Héctor: el motor sigue
 * creyendo que tiene un terminal delante, así que la ruta de chat que Andrés
 * usa a diario no se toca ni se arriesga.
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "hexos_serve.h"

#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define PROMPT_USER     "tú>"      /* UTF-8: t \xc3\xba > */
#define PROMPT_ASSIST   "helios>"
#define MAX_MARKER      8          /* el más largo, "helios>", son 7 bytes */
#define READ_CHUNK      4096
#define PENDING_CAP     (READ_CHUNK * 4)

static pid_t            g_pid    = -1;
static int              g_in_fd  = -1;   /* escribimos al stdin del motor */
static int              g_out_fd = -1;   /* leemos su stdout */
static pthread_t        g_reader;
static pthread_mutex_t  g_lock   = PTHREAD_MUTEX_INITIALIZER;
static engine_state_t   g_state  = ENGINE_BOOTING;
static engine_chunk_cb  g_on_chunk;
static engine_event_cb  g_on_event;
static void            *g_user;
static volatile int     g_reader_alive;

/* Buffer de bytes ya limpios de ANSI pendientes de clasificar. */
static char   g_pending[PENDING_CAP];
static size_t g_pending_len;

/* ------------------------------------------------------------------------ */

const char *engine_state_name(engine_state_t st)
{
    switch (st) {
        case ENGINE_BOOTING:  return "booting";
        case ENGINE_IDLE:     return "idle";
        case ENGINE_THINKING: return "thinking";
        case ENGINE_SPEAKING: return "speaking";
        case ENGINE_DEAD:     return "dead";
    }
    return "unknown";
}

engine_state_t engine_state(void)
{
    pthread_mutex_lock(&g_lock);
    engine_state_t st = g_state;
    pthread_mutex_unlock(&g_lock);
    return st;
}

static void set_state(engine_state_t st, const char *event)
{
    pthread_mutex_lock(&g_lock);
    g_state = st;
    pthread_mutex_unlock(&g_lock);
    if (event && g_on_event) g_on_event(event, g_user);
}

void engine_set_callbacks(engine_chunk_cb on_chunk, engine_event_cb on_event,
                          void *user)
{
    g_on_chunk = on_chunk;
    g_on_event = on_event;
    g_user     = user;
}

/* ------------------------------------------------------------------------
 * Limpieza de ANSI
 *
 * Solo hay que quitar secuencias CSI ("ESC [ ... letra"), que es lo único
 * que helios_chat emite: colores y \033[0m. El estado vive entre llamadas
 * porque una secuencia puede partirse entre dos read().
 * ------------------------------------------------------------------------ */
static size_t strip_ansi(const char *in, size_t len, char *out)
{
    static int in_escape;   /* 1 = vimos ESC, 2 = estamos dentro del CSI */
    size_t o = 0;

    for (size_t i = 0; i < len; i++) {
        unsigned char c = (unsigned char)in[i];
        if (in_escape == 1) {
            in_escape = (c == '[') ? 2 : 0;
            continue;
        }
        if (in_escape == 2) {
            /* El CSI termina en el primer byte del rango 0x40-0x7E. */
            if (c >= 0x40 && c <= 0x7E) in_escape = 0;
            continue;
        }
        if (c == 0x1B) { in_escape = 1; continue; }
        if (c == '\r') continue;
        out[o++] = (char)c;
    }
    return o;
}

/* ------------------------------------------------------------------------
 * Máquina de turnos
 *
 * Se guarda hasta MAX_MARKER-1 bytes sin emitir por si el marcador viene
 * partido entre dos lecturas; sin eso, un "tú>" a caballo entre dos read()
 * dejaría el turno abierto para siempre.
 * ------------------------------------------------------------------------ */
static void consume_pending(void)
{
    for (;;) {
        engine_state_t st = engine_state();

        if (st == ENGINE_SPEAKING) {
            char *hit = memmem(g_pending, g_pending_len,
                               PROMPT_USER, strlen(PROMPT_USER));
            if (hit) {
                size_t upto = (size_t)(hit - g_pending);
                if (upto && g_on_chunk) g_on_chunk(g_pending, upto, g_user);
                size_t skip = upto + strlen(PROMPT_USER);
                memmove(g_pending, g_pending + skip, g_pending_len - skip);
                g_pending_len -= skip;
                set_state(ENGINE_IDLE, "end");
                continue;
            }
            /* Nada de marcador: emite todo menos la cola dudosa. */
            if (g_pending_len > MAX_MARKER) {
                size_t emit = g_pending_len - MAX_MARKER;
                /* Sin esto se parte por la mitad una letra multibyte y cada
                 * trozo viaja en un evento distinto: el navegador recibe dos
                 * secuencias UTF-8 inválidas y pinta "cr??ticas". Se retrocede
                 * al principio del carácter (los bytes 10xxxxxx son
                 * continuación, nunca comienzo). */
                while (emit > 0 &&
                       ((unsigned char)g_pending[emit] & 0xC0) == 0x80) {
                    emit--;
                }
                if (emit) {
                    if (g_on_chunk) g_on_chunk(g_pending, emit, g_user);
                    memmove(g_pending, g_pending + emit, g_pending_len - emit);
                    g_pending_len -= emit;
                }
            }
            return;
        }

        /* BOOTING / IDLE / THINKING: buscamos el marcador que toca y
         * tiramos el ruido de en medio (banners, avisos de memoria...). */
        const char *marker = (st == ENGINE_THINKING) ? PROMPT_ASSIST
                                                     : PROMPT_USER;
        char *hit = memmem(g_pending, g_pending_len, marker, strlen(marker));
        if (!hit) {
            if (g_pending_len > MAX_MARKER) {
                memmove(g_pending, g_pending + g_pending_len - MAX_MARKER,
                        MAX_MARKER);
                g_pending_len = MAX_MARKER;
            }
            return;
        }
        size_t skip = (size_t)(hit - g_pending) + strlen(marker);
        memmove(g_pending, g_pending + skip, g_pending_len - skip);
        g_pending_len -= skip;

        if (st == ENGINE_THINKING) {
            set_state(ENGINE_SPEAKING, "start");
        } else {
            /* Primer "tú>": el modelo terminó de cargar. */
            set_state(ENGINE_IDLE, st == ENGINE_BOOTING ? "ready" : NULL);
        }
    }
}

static void *reader_thread(void *arg)
{
    (void)arg;
    char raw[READ_CHUNK];
    char clean[READ_CHUNK];

    while (g_reader_alive) {
        ssize_t n = read(g_out_fd, raw, sizeof(raw));
        if (n <= 0) {
            if (n < 0 && errno == EINTR) continue;
            break;
        }
        size_t c = strip_ansi(raw, (size_t)n, clean);
        if (!c) continue;

        if (g_pending_len + c > PENDING_CAP) {
            /* Salvaguarda: si algo se descontrola, no crecemos sin límite. */
            size_t drop = g_pending_len + c - PENDING_CAP;
            if (drop > g_pending_len) drop = g_pending_len;
            memmove(g_pending, g_pending + drop, g_pending_len - drop);
            g_pending_len -= drop;
        }
        memcpy(g_pending + g_pending_len, clean, c);
        g_pending_len += c;
        consume_pending();
    }

    set_state(ENGINE_DEAD, "dead");
    return NULL;
}

/* ------------------------------------------------------------------------ */

bool engine_start(const char *binary, const char *model, const char *temp)
{
    int to_engine[2], from_engine[2];
    if (pipe(to_engine) < 0) return false;
    if (pipe(from_engine) < 0) {
        close(to_engine[0]); close(to_engine[1]);
        return false;
    }

    pid_t pid = fork();
    if (pid < 0) {
        close(to_engine[0]); close(to_engine[1]);
        close(from_engine[0]); close(from_engine[1]);
        return false;
    }

    if (pid == 0) {
        /* Hijo: stdin y stdout a las tuberías; stderr se queda en la
         * consola de HEXOS para que la carga del modelo sea visible. */
        dup2(to_engine[0], STDIN_FILENO);
        dup2(from_engine[1], STDOUT_FILENO);
        close(to_engine[0]);  close(to_engine[1]);
        close(from_engine[0]); close(from_engine[1]);
        setsid();   /* que el Ctrl-C de HEXOS no lo mate por accidente */
        execlp(binary, binary, model, temp ? temp : "0.7", (char *)NULL);
        fprintf(stderr, "[serve] no pude ejecutar %s: %s\n",
                binary, strerror(errno));
        _exit(127);
    }

    close(to_engine[0]);
    close(from_engine[1]);
    g_pid    = pid;
    g_in_fd  = to_engine[1];
    g_out_fd = from_engine[0];
    g_state  = ENGINE_BOOTING;
    g_pending_len  = 0;
    g_reader_alive = 1;

    if (pthread_create(&g_reader, NULL, reader_thread, NULL) != 0) {
        engine_stop();
        return false;
    }
    return true;
}

static bool write_line(const char *text)
{
    if (g_in_fd < 0) return false;
    size_t len = strlen(text);
    struct iovec parts[2] = {
        { (void *)text, len },
        { (void *)"\n", 1 }
    };
    for (int i = 0; i < 2; i++) {
        const char *p = parts[i].iov_base;
        size_t left = parts[i].iov_len;
        while (left) {
            ssize_t w = write(g_in_fd, p, left);
            if (w <= 0) {
                if (errno == EINTR) continue;
                return false;
            }
            p += w; left -= (size_t)w;
        }
    }
    return true;
}

bool engine_send(const char *text)
{
    if (engine_state() != ENGINE_IDLE) return false;
    set_state(ENGINE_THINKING, "thinking");

    /* El REPL lee por líneas: un mensaje con saltos se convertiría en varios
     * turnos. Para eso existe /pegar, que acumula hasta /fin y lo trata como
     * un solo mensaje (además con el encuadre correcto para texto pegado o
     * un fichero subido). Los mensajes de una línea van directos. */
    bool ok;
    if (strchr(text, '\n')) {
        ok = write_line("/pegar");
        if (ok) {
            const char *p = text;
            while (ok && *p) {
                const char *nl = strchr(p, '\n');
                size_t n = nl ? (size_t)(nl - p) : strlen(p);
                char line[8192];
                if (n >= sizeof(line)) n = sizeof(line) - 1;
                memcpy(line, p, n);
                line[n] = '\0';
                /* Una línea que dijera "/fin" cerraría el pegado antes de
                 * tiempo; se desactiva con un espacio. */
                if (!strcmp(line, "/fin")) strcpy(line, " /fin");
                ok = write_line(line);
                p = nl ? nl + 1 : p + strlen(p);
            }
            if (ok) ok = write_line("/fin");
        }
    } else {
        ok = write_line(text);
    }

    if (!ok) {
        set_state(ENGINE_IDLE, NULL);
        return false;
    }
    return true;
}

bool engine_command(const char *cmd)
{
    if (engine_state() != ENGINE_IDLE) return false;
    return write_line(cmd);
}

void engine_stop(void)
{
    g_reader_alive = 0;
    if (g_in_fd >= 0) {
        write_line("/salir");     /* deja que destile la memoria episódica */
        close(g_in_fd);
        g_in_fd = -1;
    }
    if (g_pid > 0) {
        for (int i = 0; i < 100; i++) {   /* hasta 10 s para el cierre limpio */
            if (waitpid(g_pid, NULL, WNOHANG) == g_pid) { g_pid = -1; break; }
            usleep(100000);
        }
        if (g_pid > 0) {
            kill(g_pid, SIGTERM);
            waitpid(g_pid, NULL, 0);
            g_pid = -1;
        }
    }
    if (g_out_fd >= 0) { close(g_out_fd); g_out_fd = -1; }
}
