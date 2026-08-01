/*
 * HEXOS Serve - Punto de entrada
 *
 * HEXOS abre el puerto y lanza a Héctor; Héctor no sabe que existe la red.
 *
 * Nota de diseño: nada más arrancar se manda /fast al motor. El governor de
 * ritmo de helios_chat frena la generación a 18 tok/s para que en el terminal
 * parezca natural, pero eso resuelve en el motor un problema que es de
 * dibujado. En la web el cliente reparte los caracteres a 60 fps, así que la
 * generación debe ir a toda máquina: el ritmo percibido lo pone el navegador
 * y el ritmo real solo debería frenarlo la energía o la térmica.
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "hexos_serve.h"

#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define DEFAULT_PORT 8080
#define DEFAULT_BIND "0.0.0.0"
#define DEFAULT_ROOT "hexos/web"
#define DEFAULT_ENGINE "helios_chat"

static void on_chunk(const char *text, size_t len, void *user)
{
    (void)user;
    char esc[16 * 1024];
    char json[16 * 1024 + 64];
    json_escape(text, len, esc, sizeof(esc));
    snprintf(json, sizeof(json), "{\"t\":\"%s\"}", esc);
    serve_broadcast("token", json);
}

static void on_event(const char *event, void *user)
{
    (void)user;
    char json[128];
    snprintf(json, sizeof(json), "{\"state\":\"%s\"}",
             engine_state_name(engine_state()));
    serve_broadcast(event, json);

    if (!strcmp(event, "ready")) {
        /* El navegador suaviza; el motor va suelto. */
        engine_command("/fast");
        fprintf(stderr, "[serve] motor listo (ritmo pleno, la UI suaviza)\n");
    }
}

static void on_signal(int sig)
{
    (void)sig;
    serve_stop();
}

static void usage(const char *prog)
{
    fprintf(stderr,
        "uso: %s --model <modelo.hnf> [opciones]\n"
        "\n"
        "  --model <ruta>    HNF a cargar (obligatorio)\n"
        "  --engine <ruta>   binario de helios_chat (por defecto: %s del PATH)\n"
        "  --temp <t>        temperatura (por defecto 0.7)\n"
        "  --port <n>        puerto (por defecto %d)\n"
        "  --bind <ip>       interfaz (por defecto %s, toda la LAN)\n"
        "  --root <dir>      raíz de ficheros web (por defecto %s)\n",
        prog, DEFAULT_ENGINE, DEFAULT_PORT, DEFAULT_BIND, DEFAULT_ROOT);
}

int main(int argc, char **argv)
{
    const char *model  = NULL;
    const char *engine = DEFAULT_ENGINE;
    const char *temp   = "0.7";
    const char *bind_addr = DEFAULT_BIND;
    const char *root   = DEFAULT_ROOT;
    int port = DEFAULT_PORT;

    for (int i = 1; i < argc; i++) {
        const char *next = (i + 1 < argc) ? argv[i + 1] : NULL;
        if (!strcmp(argv[i], "--model")  && next) { model = next; i++; }
        else if (!strcmp(argv[i], "--engine") && next) { engine = next; i++; }
        else if (!strcmp(argv[i], "--temp")   && next) { temp = next; i++; }
        else if (!strcmp(argv[i], "--bind")   && next) { bind_addr = next; i++; }
        else if (!strcmp(argv[i], "--root")   && next) { root = next; i++; }
        else if (!strcmp(argv[i], "--port")   && next) { port = atoi(next); i++; }
        else { usage(argv[0]); return 1; }
    }
    if (!model) { usage(argv[0]); return 1; }

    signal(SIGINT,  on_signal);
    signal(SIGTERM, on_signal);

    /* El puerto primero: si está ocupado, se sabe al instante y no se han
     * cargado gigabytes de modelo para nada. */
    if (!serve_bind(bind_addr, port)) return 1;

    engine_set_callbacks(on_chunk, on_event, NULL);
    if (!engine_start(engine, model, temp)) {
        fprintf(stderr, "[serve] no pude arrancar el motor\n");
        return 1;
    }
    fprintf(stderr, "[serve] cargando %s...\n", model);
    fprintf(stderr, "[serve] http://localhost:%d  (y en la LAN por %s)\n",
            port, bind_addr);

    serve_run(root);

    fprintf(stderr, "\n[serve] cerrando: dejo que Héctor destile la memoria\n");
    engine_stop();
    return 0;
}
