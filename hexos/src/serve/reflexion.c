/*
 * HEXOS — trabajador de reflexión (E4). SOLO ENSAYO.
 *
 * Toma el trabajo pendiente más antiguo, se lo da al modelo en una sesión
 * reservada, parsea el `MemoryDelta` con el parser estricto y lo ensaya contra
 * HERA. **No aplica nada.** No hay aplicador y su ausencia no es un descuido:
 * mientras no exista una puerta demostrada delante, dar autoridad a una
 * extracción del modelo es exactamente lo que este proyecto lleva media
 * evacuación intentando impedir.
 *
 *      salida del modelo → parsear → ensayar → telemetría
 *                                            ✗ aplicar
 *
 * Cuando el aplicador exista, el origen `reflexión` solo podrá PROPONER
 * candidatos. Confirmar y corregir seguirán necesitando una intervención
 * posterior y explícita de la persona.
 *
 * PRIORIDAD: el chat manda. Si llega un turno visible, la reflexión se corta y
 * el job vuelve a la cola APLAZADO — sin gastar intento y sin contar como
 * fallo. Una preempción es planificación normal.
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include "hexos_serve.h"
#include "hera_queue.h"
#include "hera_delta.h"

#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static pthread_t     g_hilo;
static volatile int  g_vivo;
static bool          g_arrancado;

/* Telemetría: recuentos y tiempos. NUNCA contenido. */
static struct {
    size_t trabajos, aplazados, fallidos;
    size_t ops, aceptables, rechazadas;
    double ms_total;
    pthread_mutex_t lock;
} g_tel = { 0, 0, 0, 0, 0, 0, 0.0, PTHREAD_MUTEX_INITIALIZER };

/* ------------------------------------------------------------------------
 * El renderer de reflexión. Es lo ÚNICO que ve el modelo, junto con la
 * entrada congelada: ni identidad, ni memoria, ni el contrato del chat. Un
 * trabajo de reflexión no es una conversación y no debe parecerlo.
 *
 * Pide un esquema cerrado a propósito. El fallo del 2026-07-31 fue que el
 * destilador escribió prosa libre y el modelo la recitaba al día siguiente
 * como recuerdo; con campos declarados eso es inexpresable. Y lo que salga
 * pasa igual por el parser estricto: pedirlo bien no es garantía de nada.
 * ------------------------------------------------------------------------ */
static const char *RENDERER =
    "Extraes hechos duraderos de un turno y respondes SOLO con JSON, sin nada "
    "alrededor.\n\n"
    "Ejemplo. Si te dieran:\n"
    "  ID de evidencia: u7\n"
    "  Lo que dijo la persona: me llamo Marta y trabajo de veterinaria\n"
    "responderias exactamente:\n"
    "{\"memory_delta\":[{\"op\":\"proponer\",\"clave\":\"yo/nombre\","
    "\"valor\":\"Marta\",\"texto\":\"Se llama Marta\",\"evidencia\":\"u7\"},"
    "{\"op\":\"proponer\",\"clave\":\"yo/oficio\",\"valor\":\"veterinaria\","
    "\"texto\":\"Trabaja de veterinaria\",\"evidencia\":\"u7\"}]}\n\n"
    "Reglas:\n"
    "- Copia el ID de evidencia que se te da, tal cual.\n"
    "- La clave es sujeto/predicado. El sujeto es 'yo' si el hecho es de quien "
    "habla; si es de otra persona, su nombre en minusculas.\n"
    "- El valor tiene que aparecer LITERALMENTE en lo que dijo la persona.\n"
    "- Nada de lo del ejemplo va en tu respuesta: son datos de otra "
    "conversacion.\n"
    "- Si no hay ningun hecho duradero, responde {\"memory_delta\":[]}.";

/* Presupuesto de pensamiento. Con cero, el modelo razona EN VOZ ALTA y la
 * respuesta sale llena de deliberación en vez de JSON — medido, no supuesto.
 * Darle sitio donde pensar es lo que hace que lo visible sea solo el delta.
 * Lo que piense no se guarda ni se mira: el job no tiene campo para ello. */
#define REFLEXION_PENSAMIENTO 400
#define REFLEXION_VISIBLE     300

/* ------------------------------------------------------------------------ */

static void ejecutar(const hera_job_t *j) {
    char *entrada = malloc(HERA_JOB_TEXTO_MAX * 2 + 512);
    if (!entrada) { hera_cola_fallido(j->id, "sin memoria"); return; }
    snprintf(entrada, HERA_JOB_TEXTO_MAX * 2 + 512,
             "ID de evidencia: %s\nLo que dijo la persona:\n%s\n\n"
             "Lo que se le contesto:\n%s",
             j->evidencia, j->mensaje, j->respuesta);

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    bool aplazada = false;
    char *salida = rt_reflexionar(RENDERER, entrada, REFLEXION_VISIBLE,
                                  REFLEXION_PENSAMIENTO, &aplazada);
    clock_gettime(CLOCK_MONOTONIC, &t1);
    free(entrada);

    if (aplazada) {
        /* Ni fallo ni intento gastado: el chat tenía prioridad y ya está. */
        hera_cola_aplazado(j->id);
        pthread_mutex_lock(&g_tel.lock);
        g_tel.aplazados++;
        pthread_mutex_unlock(&g_tel.lock);
        free(salida);
        return;
    }
    if (!salida) {
        hera_cola_fallido(j->id, "el motor no devolvio nada");
        pthread_mutex_lock(&g_tel.lock);
        g_tel.fallidos++;
        pthread_mutex_unlock(&g_tel.lock);
        return;
    }

    /* Parser estricto + ensayo contra las reglas REALES del almacén. Un delta
     * corrupto se rechaza entero, se cierra el job y la cola sigue: no puede
     * atascar a los que vienen detrás. */
    hera_delta_t d;
    const bool bien = hera_delta_leer(salida, &d);
    free(salida);

    const double ms = (t1.tv_sec - t0.tv_sec) * 1000.0 +
                      (t1.tv_nsec - t0.tv_nsec) / 1e6;
    pthread_mutex_lock(&g_tel.lock);
    g_tel.trabajos++;
    g_tel.ms_total += ms;
    if (bien) {
        g_tel.ops += d.n;
        g_tel.aceptables += d.aceptables;
        g_tel.rechazadas += d.n - d.aceptables;
    } else {
        g_tel.fallidos++;
    }
    pthread_mutex_unlock(&g_tel.lock);

    /* AQUÍ NO SE APLICA NADA. Ni siquiera las operaciones que el ensayo dio
     * por buenas: `aceptables` significa "pasaría las reglas hoy", no "se ha
     * hecho". */
    if (bien) {
        hera_cola_hecho(j->id, d.n, d.aceptables);
        fprintf(stderr, "[reflexion] %s · %zu ops · %zu aceptables · %.0f ms\n",
                j->id, d.n, d.aceptables, ms);
    } else {
        hera_cola_fallido(j->id, d.motivo);
        fprintf(stderr, "[reflexion] %s · delta rechazado: %s\n",
                j->id, d.motivo);
    }
}

static void *bucle(void *arg) {
    (void)arg;
    while (g_vivo) {
        hera_job_t j;
        /* Solo si el motor está libre: el trabajador nunca se pone delante de
         * un turno visible, y si aun así llega uno, la preempción lo aparta. */
        if (ruta_state() != ENGINE_IDLE || !hera_cola_tomar(&j)) {
            usleep(250000);
            continue;
        }
        ejecutar(&j);
    }
    return NULL;
}

/* ------------------------------------------------------------------------ */

bool reflexion_arrancar(void) {
    if (g_arrancado) return true;
    g_vivo = 1;
    if (pthread_create(&g_hilo, NULL, bucle, NULL) != 0) {
        g_vivo = 0;
        return false;
    }
    g_arrancado = true;
    return true;
}

/* Apagar el trabajador NO toca el chat ni la cola: los trabajos pendientes se
 * quedan donde están y el que estuviera en vuelo lo recupera la cola durable
 * al reabrir, porque su dueño habrá desaparecido. Es el interruptor de
 * rollback. */
void reflexion_parar(void) {
    if (!g_arrancado) return;
    g_vivo = 0;
    pthread_join(g_hilo, NULL);
    g_arrancado = false;
}

bool reflexion_activa(void) { return g_arrancado; }

size_t reflexion_telemetria_json(char *out, size_t cap) {
    pthread_mutex_lock(&g_tel.lock);
    /* Recuentos y tiempos. Ni una palabra de lo que se dijo: la telemetría
     * acaba en logs, y un log no tiene las reglas del almacén. */
    const int n = snprintf(out, cap,
        "{\"activa\":%s,\"trabajos\":%zu,\"aplazados\":%zu,\"fallidos\":%zu,"
        "\"ops\":%zu,\"aceptables\":%zu,\"rechazadas\":%zu,"
        "\"ms_medio\":%.0f,\"pendientes\":%zu,\"aplicados\":0}",
        g_arrancado ? "true" : "false", g_tel.trabajos, g_tel.aplazados,
        g_tel.fallidos, g_tel.ops, g_tel.aceptables, g_tel.rechazadas,
        g_tel.trabajos ? g_tel.ms_total / (double)g_tel.trabajos : 0.0,
        hera_cola_pendientes());
    pthread_mutex_unlock(&g_tel.lock);
    return (n > 0) ? (size_t)n : 0;
}
