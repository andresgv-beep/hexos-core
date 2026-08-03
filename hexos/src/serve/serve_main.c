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
#define DEFAULT_MODEL_PROBE "helios_model_probe"

static void on_chunk(const char *text, size_t len, void *user)
{
    (void)user;
    char esc[16 * 1024];
    char json[16 * 1024 + 64];
    json_escape(text, len, esc, sizeof(esc));
    snprintf(json, sizeof(json), "{\"t\":\"%s\"}", esc);
    serve_broadcast("token", json);
}

/* Avisos del motor: van por su propio evento para que la UI los distinga de
 * lo que Héctor dice. Que un documento se haya truncado no es parte de la
 * respuesta, pero cambia cuánto vale la respuesta. */
static void on_notice(const char *text, size_t len, void *user)
{
    (void)user;
    char esc[1024];
    char json[1200];
    json_escape(text, len, esc, sizeof(esc));
    snprintf(json, sizeof(json), "{\"t\":\"%s\"}", esc);
    serve_broadcast("notice", json);
}

/* Telemetría del CK: acto, registro y presupuestos. El contrato NO viaja —
 * es efímero y no debe aparecer en la traza que ve el usuario. */
static void on_frame(const char *acto, const char *registro,
                     int visible_budget, int thinking_budget, void *user)
{
    (void)user;
    char json[256];
    snprintf(json, sizeof(json),
             "{\"acto\":\"%s\",\"registro\":\"%s\","
             "\"visible_budget\":%d,\"thinking_budget\":%d}",
             acto, registro, visible_budget, thinking_budget);
    serve_broadcast("ck_frame", json);
}

static void on_event(const char *event, void *user)
{
    (void)user;
    char json[128];
    snprintf(json, sizeof(json), "{\"state\":\"%s\"}",
             engine_state_name(ruta_state()));
    serve_broadcast(event, json);

    if (!strcmp(event, "ready") && !ruta_activa_tipada()) {
        /* El navegador suaviza; el motor va suelto. La ruta tipada no tiene
         * governor de ritmo que desactivar: nunca lo tuvo. */
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
        "  --probe <ruta>    sonda HNF de Héctor (por defecto: %s del PATH)\n"
        "  --no-probe        compatibilidad: no inspeccionar capacidades HNF\n"
        "  --temp <t>        temperatura (por defecto 0.7)\n"
        "  --port <n>        puerto (por defecto %d)\n"
        "  --bind <ip>       interfaz (por defecto %s, toda la LAN)\n"
        "  --root <dir>      raíz de ficheros web (por defecto %s)\n"
        "  --no-distill      no consolidar la memoria episódica al salir\n"
        "  --runtime <ruta>  RUTA TIPADA — EXPERIMENTAL (opt-in). HexOS\n"
        "                    clasifica el turno con su propio CK y lleva la\n"
        "                    memoria (HERA): solo entran al prompt los hechos\n"
        "                    confirmados con evidencia. La reflexión sigue\n"
        "                    desconectada. Sin este flag manda la legacy, que\n"
        "                    sigue siendo la predeterminada y el oráculo.\n"
        "\n"
        "Usa --no-distill mientras desarrollas. Cada cierre destila la sesión\n"
        "al diario de Héctor, así que veinte reinicios de prueba dejan veinte\n"
        "recuerdos basura — y el modelo los lee al arrancar y los imita.\n",
        prog, DEFAULT_ENGINE, DEFAULT_MODEL_PROBE,
        DEFAULT_PORT, DEFAULT_BIND, DEFAULT_ROOT);
}

int main(int argc, char **argv)
{
    const char *model  = NULL;
    const char *engine = DEFAULT_ENGINE;
    const char *probe = getenv("HELIOS_MODEL_PROBE");
    if (!probe || !*probe) probe = DEFAULT_MODEL_PROBE;
    const char *temp   = "0.7";
    const char *bind_addr = DEFAULT_BIND;
    const char *root   = DEFAULT_ROOT;
    int port = DEFAULT_PORT;
    bool no_distill = false;
    const char *runtime_bin = NULL;
    bool no_probe = false;

    for (int i = 1; i < argc; i++) {
        const char *next = (i + 1 < argc) ? argv[i + 1] : NULL;
        if (!strcmp(argv[i], "--no-distill")) { no_distill = true; }
        else if (!strcmp(argv[i], "--runtime") && next) { runtime_bin = next; i++; }
        else if (!strcmp(argv[i], "--no-probe")) { no_probe = true; }
        else if (!strcmp(argv[i], "--model")  && next) { model = next; i++; }
        else if (!strcmp(argv[i], "--engine") && next) { engine = next; i++; }
        else if (!strcmp(argv[i], "--probe")  && next) { probe = next; i++; }
        else if (!strcmp(argv[i], "--temp")   && next) { temp = next; i++; }
        else if (!strcmp(argv[i], "--bind")   && next) { bind_addr = next; i++; }
        else if (!strcmp(argv[i], "--root")   && next) { root = next; i++; }
        else if (!strcmp(argv[i], "--port")   && next) { port = atoi(next); i++; }
        else { usage(argv[0]); return 1; }
    }
    if (!model) { usage(argv[0]); return 1; }

    signal(SIGINT,  on_signal);
    signal(SIGTERM, on_signal);

    if (!no_probe) {
        hexos_model_report_t report;
        if (hexos_model_probe(probe, model, &report)) {
            serve_set_model_report(&report);
            fprintf(stderr, "[serve] HNF: text=%s multimodal=%s\n",
                    report.text_architecture,
                    report.multimodal ? "sí" : "no");
            for (int i = 0; i < HEXOS_MODEL_MODALITY_COUNT; i++) {
                const hexos_modality_capability_t *cap = &report.modalities[i];
                if (!cap->declared && !cap->present) continue;
                fprintf(stderr, "[serve]   %s: %s",
                        hexos_model_modality_name((hexos_model_modality_t)i),
                        hexos_adapter_status_name(cap->status));
                if (cap->adapter[0]) fprintf(stderr, " (%s)", cap->adapter);
                fputc('\n', stderr);
            }
        } else {
            fprintf(stderr, "[serve] aviso: no pude inspeccionar el HNF: %s\n",
                    report.error);
            fprintf(stderr, "[serve] continúo en compatibilidad de texto; "
                            "usa --probe para fijar la sonda\n");
        }
    }

    /* El puerto primero: si está ocupado, se sabe al instante y no se han
     * cargado gigabytes de modelo para nada. */
    if (!serve_bind(bind_addr, port)) return 1;

    /* El hijo hereda el entorno: así el motor sabe que esta sesión no debe
     * consolidarse. Sin esto, cada reinicio de desarrollo escribe una entrada
     * en ~/.helios/episodic.md, y una transcripción cruda o un bucle guardado
     * ahí no es un dato: es un ejemplo que el modelo imita en la sesión
     * siguiente. */
    if (no_distill) {
        setenv("HELIOS_NO_DISTILL", "1", 1);
        fprintf(stderr, "[serve] memoria episódica congelada "
                        "(esta sesión no se consolidará)\n");
    }

    if (runtime_bin) {
        // Ruta tipada: el CK vive aquí y Héctor solo genera.
        ruta_usar_tipada(true);
        rt_set_callbacks(on_chunk, on_event, on_notice, on_frame, NULL);
        if (!rt_start(runtime_bin, model, getenv("HELIOS_CTX"), temp)) {
            fprintf(stderr, "[serve] no pude arrancar helios_runtime\n");
            return 1;
        }
        fprintf(stderr,
            "[serve] ***** RUTA TIPADA — EXPERIMENTAL *****\n"
            "[serve] El CK y la memoria viven en HexOS. Solo gobiernan los\n"
            "[serve] hechos CONFIRMADOS: los candidatos y todo lo importado\n"
            "[serve] del almacén legacy están en cuarentena y no entran al\n"
            "[serve] prompt hasta que los confirmes (usa `hera`).\n"
            "[serve] La reflexión sigue DESCONECTADA: nada escribe memoria\n"
            "[serve] por su cuenta. La legacy es la predeterminada y el\n"
            "[serve] oráculo.\n");
    } else {
        engine_set_notice_cb(on_notice);
        engine_set_callbacks(on_chunk, on_event, NULL);
        if (!engine_start(engine, model, temp)) {
            fprintf(stderr, "[serve] no pude arrancar el motor\n");
            return 1;
        }
    }
    fprintf(stderr, "[serve] cargando %s...\n", model);
    fprintf(stderr, "[serve] http://localhost:%d  (y en la LAN por %s)\n",
            port, bind_addr);

    serve_run(root);

    fprintf(stderr, "\n[serve] cerrando: dejo que Héctor destile la memoria\n");
    if (ruta_activa_tipada()) rt_stop(); else engine_stop();
    return 0;
}
