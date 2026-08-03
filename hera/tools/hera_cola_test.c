/*
 * Batería de la cola durable (E4, paso 1).
 *
 * Lo que hay que demostrar aquí no es que encole: es que un reinicio no
 * duplique trabajo y que dos trabajadores no se lleven el mismo job. Sin eso,
 * el trabajador de mañana escribiría recuerdos repetidos y no habría forma de
 * saber si la culpa era suya o de la cola.
 *
 * Sabotajes (rango 30+):
 *   30  encolar deja de ser idempotente
 *   31  tomar no marca el job: dos trabajadores se llevan el mismo
 *   32  la telemetría se lleva el texto del recuerdo
 *   33  la recuperación no cuenta los intentos: bucle infinito con cara de ir bien
 *   34  al releer, un "encolado" repetido crea otro job
 *
 * Con `--tomar-uno` el binario abre la cola, toma UN job e imprime su id. Es
 * para la prueba multiproceso: hacen falta procesos exec'd de verdad, porque
 * tras un fork los hijos comparten la misma descripción de fichero y flock no
 * excluiría entre ellos — la prueba pasaría sin probar nada.
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "hera_queue.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static int g_fallos, g_pruebas;
static char g_base[512], g_dir[700];

static void ok_silencioso(bool cond) { (void)cond; }

static void ok(bool cond, const char *nombre, const char *detalle) {
    g_pruebas++;
    if (cond) printf("  \033[32m✓\033[0m %s\n", nombre);
    else { g_fallos++; printf("  \033[31m✗ %s\033[0m — %s\n", nombre, detalle); }
}

static void perfil_nuevo(const char *nombre) {
    snprintf(g_dir, sizeof(g_dir), "%s/%s", g_base, nombre);
    char cmd[800];
    snprintf(cmd, sizeof(cmd), "rm -rf '%s'", g_dir);
    if (system(cmd) != 0) { /* no existía */ }
    mkdir(g_dir, 0755);
    setenv("HELIOS_HOME", g_dir, 1);
    setenv("HERA_TS_FIJO", "1700000000", 1);
    hera_cola_cerrar();
    hera_cola_abrir();
}

static hera_job_t hacer(unsigned turno) {
    hera_job_t j;
    memset(&j, 0, sizeof(j));
    snprintf(j.perfil, sizeof(j.perfil), "p1");
    snprintf(j.sesion, sizeof(j.sesion), "s1");
    j.turno = turno;
    snprintf(j.id, sizeof(j.id), "%s/%s/%u", j.perfil, j.sesion, turno);
    snprintf(j.mensaje, sizeof(j.mensaje), "mi perro se llama Rufo (turno %u)", turno);
    snprintf(j.respuesta, sizeof(j.respuesta), "Anotado, turno %u", turno);
    snprintf(j.acto, sizeof(j.acto), "responder");
    snprintf(j.registro, sizeof(j.registro), "neutral");
    snprintf(j.evidencia, sizeof(j.evidencia), "u%u", turno);
    snprintf(j.perfil_hash, sizeof(j.perfil_hash), "abc123");
    j.visible_budget = 500;
    j.thinking_budget = 260;
    return j;
}

/* ---------------------------------------------------------------------- */

static void prueba_idempotencia(void) {
    printf("\n[1] encolar el mismo turno dos veces no crea dos jobs\n");
    perfil_nuevo("c1");

    hera_job_t j = hacer(1);
    ok(hera_cola_encolar(&j), "el turno entra", "no entró");
    ok(hera_cola_encolar(&j), "encolarlo otra vez no falla", "falló");
    ok(hera_cola_encolar(&j), "ni a la tercera", "falló");
    ok(hera_cola_pendientes() == 1, "y solo hay UN pendiente",
       "se duplicó el trabajo");

    /* La idempotencia vive en DOS sitios y hay que probar los dos por
     * separado: al escribir (no se anota una linea repetida) y al releer (una
     * linea repetida no crea otro job). La segunda tapaba a la primera, asi
     * que el diario podia crecer sin fin con la cuenta cuadrando. */
    FILE *f = fopen(hera_cola_ruta(), "r");
    int encolados = 0;
    if (f) {
        char l[16384];
        while (fgets(l, sizeof(l), f)) if (strstr(l, "\"r\":\"encolado\"")) encolados++;
        fclose(f);
    }
    ok(encolados == 1,
       "y el diario tiene UNA sola linea de encolado, no tres",
       "el diario crece con cada reintento de encolar");

    /* Y la guarda de relectura, con un diario que SÍ trae la línea repetida:
     * es lo que pasaría al leer un fichero escrito por una versión con el bug,
     * y no se puede probar con la de escritura puesta porque entonces el
     * diario nunca llega a tener duplicados. */
    char linea[16384] = "";
    f = fopen(hera_cola_ruta(), "r");
    if (f) { if (!fgets(linea, sizeof(linea), f)) linea[0] = '\0'; fclose(f); }
    f = fopen(hera_cola_ruta(), "a");
    if (f) { fputs(linea, f); fclose(f); }   /* mismo job, otra vez */
    hera_cola_cerrar();
    hera_cola_abrir();
    ok(hera_cola_pendientes() == 1,
       "un diario con la línea repetida sigue dando UN job al releer",
       "el trabajo se duplicó al arrancar");

    /* Otro turno sí es otro job. */
    hera_job_t k = hacer(2);
    hera_cola_encolar(&k);
    ok(hera_cola_pendientes() == 2, "otro turno sí es otro job", "no entró");
}

static void prueba_durabilidad(void) {
    printf("\n[2] la cola sobrevive al reinicio\n");
    perfil_nuevo("c2");

    for (unsigned t = 1; t <= 3; t++) { hera_job_t j = hacer(t); hera_cola_encolar(&j); }
    ok(hera_cola_pendientes() == 3, "tres pendientes", "cuenta distinta");

    hera_cola_cerrar();
    ok(hera_cola_abrir(), "se reabre", "no abre");
    ok(hera_cola_pendientes() == 3, "los tres siguen ahí tras reiniciar",
       "se perdió trabajo");

    /* Y reencolar tras el reinicio sigue sin duplicar: es lo que permite que
     * la recuperación sea reintentar a ciegas. */
    hera_job_t j = hacer(2);
    hera_cola_encolar(&j);
    ok(hera_cola_pendientes() == 3, "reencolar tras reiniciar no duplica",
       "duplicó");
}

static void prueba_tomar(void) {
    printf("\n[3] tomar marca, y respeta el orden\n");
    perfil_nuevo("c3");
    for (unsigned t = 1; t <= 3; t++) { hera_job_t j = hacer(t); hera_cola_encolar(&j); }

    hera_job_t a, b;
    ok(hera_cola_tomar(&a) && a.turno == 1, "se toma el más antiguo", "otro orden");
    ok(hera_cola_tomar(&b) && b.turno == 2, "y luego el siguiente, no el mismo",
       "se repitió el job");
    ok(hera_cola_pendientes() == 1, "queda uno pendiente", "cuenta distinta");

    /* La entrada llega congelada, entera. */
    ok(strstr(a.mensaje, "Rufo") != NULL, "el mensaje real viaja con el job",
       "se perdió el mensaje");
    ok(a.respuesta[0] && a.acto[0] && a.evidencia[0] && a.perfil_hash[0],
       "y también la respuesta visible, el marco, la evidencia y el hash",
       "falta parte de la entrada congelada");

    hera_cola_hecho(a.id, 3, 1);
    ok(hera_cola_pendientes() == 1, "cerrar un job no devuelve nada a la cola",
       "volvió a la cola");
}

/* Un trabajador que muere de VERDAD: hace falta otro proceso. Reabrir la cola
 * en el mismo proceso no simula nada — el dueño sigue vivo, y la cola hace
 * bien en no tocarle el job. */
static bool tomar_y_morir(void) {
    const pid_t p = fork();
    if (p == 0) {
        hera_job_t j;
        const bool cogio = hera_cola_tomar(&j);
        _exit(cogio ? 0 : 1);        /* muere sin cerrar el job */
    }
    int st = 0;
    waitpid(p, &st, 0);
    return WIFEXITED(st) && WEXITSTATUS(st) == 0;
}

static void prueba_recuperacion(void) {
    printf("\n[4] un trabajador que muere no pierde ni repite el job\n");
    perfil_nuevo("c4");
    hera_job_t j = hacer(1);
    hera_cola_encolar(&j);

    ok(tomar_y_morir(), "un trabajador lo toma", "no lo cogió");
    ok(hera_cola_pendientes() == 0, "tomado: ya no está pendiente", "sigue");

    hera_cola_cerrar();
    hera_cola_abrir();
    ok(hera_cola_pendientes() == 1,
       "muerto su dueño, vuelve a la cola: no se pierde", "se perdió");

    /* Y no eternamente: los intentos se cuentan EN EL DIARIO, así que
     * sobreviven a otro reinicio. Si solo vivieran en RAM, el bucle sería
     * infinito con toda la apariencia de estar recuperándose bien. */
    for (int i = 0; i < HERA_JOB_INTENTOS + 2; i++) {
        if (!tomar_y_morir()) break;
        hera_cola_cerrar();
        hera_cola_abrir();
    }
    ok(hera_cola_pendientes() == 0,
       "un job que mata a su trabajador acaba fallido, no en bucle",
       "sigue reintentándose para siempre");

    char json[256];
    hera_cola_estado_json(json, sizeof(json));
    ok(strstr(json, "\"fallidos\":1") != NULL, "y consta como fallido", json);
}

/* Y al revés: si el dueño SIGUE VIVO, abrir la cola no puede robarle el job.
 * Sin esto, dos trabajadores reflexionan el mismo turno y el recuerdo se
 * duplica — que es justo lo que la cola existe para impedir. */
static void prueba_no_robar(void) {
    printf("\n[4b] abrir la cola no le roba el job a un trabajador vivo\n");
    perfil_nuevo("c4b");
    hera_job_t j = hacer(1);
    hera_cola_encolar(&j);

    hera_job_t mio;
    ok(hera_cola_tomar(&mio), "lo tomo yo, y sigo vivo", "no lo cogí");

    /* Otro proceso abre la cola mientras tanto. */
    const pid_t p = fork();
    if (p == 0) {
        hera_cola_cerrar();
        hera_cola_abrir();
        hera_job_t otro;
        _exit(hera_cola_tomar(&otro) ? 1 : 0);   /* 1 = me lo he robado */
    }
    int st = 0;
    waitpid(p, &st, 0);
    ok(WIFEXITED(st) && WEXITSTATUS(st) == 0,
       "otro que abre la cola no se lo lleva", "se lo robó a un vivo");
}

static void prueba_fallar_no_bloquea(void) {
    printf("\n[5] un job que falla no atasca la cola\n");
    perfil_nuevo("c5");
    for (unsigned t = 1; t <= 2; t++) { hera_job_t j = hacer(t); hera_cola_encolar(&j); }

    hera_job_t a;
    hera_cola_tomar(&a);
    for (int i = 0; i < HERA_JOB_INTENTOS; i++) {
        hera_job_t x;
        hera_cola_fallido(a.id, "delta mal formado");
        if (hera_cola_tomar(&x) && strcmp(x.id, a.id) != 0) {
            /* ya pasó al siguiente */
            break;
        }
    }
    hera_job_t b;
    bool llega_el_otro = false;
    for (int i = 0; i < 4; i++) {
        if (hera_cola_tomar(&b) && b.turno == 2) { llega_el_otro = true; break; }
        hera_cola_fallido(b.id, "delta mal formado");
    }
    ok(llega_el_otro, "el segundo job llega igual", "el fallido atascó la cola");
}

/* Aplazar no es fallar. */
static void prueba_aplazado(void) {
    printf("\n[5b] aplazar devuelve el job SIN gastar intentos\n");
    perfil_nuevo("c5b");
    hera_job_t j = hacer(1);
    hera_cola_encolar(&j);

    /* Se aplaza más veces que intentos hay: si contara como fallo, a la
     * tercera el job estaría muerto. Un rato de conversación no puede dar por
     * imposible un trabajo que no ha fallado nunca. */
    for (int i = 0; i < HERA_JOB_INTENTOS + 3; i++) {
        hera_job_t x;
        ok_silencioso(hera_cola_tomar(&x));
        hera_cola_aplazado(x.id);
    }
    ok(hera_cola_pendientes() == 1,
       "tras aplazarlo más veces que intentos hay, sigue pendiente",
       "se dio por fallido");

    char json[256];
    hera_cola_estado_json(json, sizeof(json));
    ok(strstr(json, "\"fallidos\":0") != NULL,
       "y no consta ningún fallo", json);

    /* Y sigue pudiendo fallar de verdad las veces que le tocan. */
    hera_job_t x;
    for (int i = 0; i < HERA_JOB_INTENTOS; i++) {
        if (hera_cola_tomar(&x)) hera_cola_fallido(x.id, "delta corrupto");
    }
    hera_cola_estado_json(json, sizeof(json));
    ok(strstr(json, "\"fallidos\":1") != NULL,
       "los intentos de verdad seguían enteros y se gastan al fallar", json);
}

static void prueba_telemetria(void) {
    printf("\n[6] la telemetría no lleva contenido privado\n");
    perfil_nuevo("c6");
    hera_job_t j = hacer(1);
    hera_cola_encolar(&j);

    char json[512];
    hera_cola_estado_json(json, sizeof(json));
    ok(strstr(json, "\"pendientes\":1") != NULL, "cuenta lo que hay", json);
    ok(strstr(json, "Rufo") == NULL,
       "y no se lleva ni una palabra del recuerdo", json);
    ok(strstr(json, "Anotado") == NULL, "ni de la respuesta", json);
}

static void prueba_entrada_congelada(void) {
    printf("\n[7] la entrada congelada no tiene sitio para lo efímero\n");
    perfil_nuevo("c7");
    hera_job_t j = hacer(1);
    hera_cola_encolar(&j);

    FILE *f = fopen(hera_cola_ruta(), "r");
    char linea[16384] = "";
    if (f) { if (!fgets(linea, sizeof(linea), f)) linea[0] = '\0'; fclose(f); }

    ok(strstr(linea, "\"mensaje\"") && strstr(linea, "\"respuesta\"") &&
       strstr(linea, "\"acto\"") && strstr(linea, "\"perfil_hash\""),
       "el job guarda mensaje, respuesta, marco y hash del perfil",
       "falta parte de la entrada");
    ok(!strstr(linea, "contrato") && !strstr(linea, "Contrato") &&
       !strstr(linea, "thinking_text") && !strstr(linea, "razonamiento"),
       "y no hay campo donde meter el contrato ni el razonamiento",
       "se coló algo efímero en el job");

    /* Un turno más largo del máximo NO se recorta: se rechaza. */
    hera_job_t g = hacer(2);
    memset(g.respuesta, 'x', sizeof(g.respuesta) - 1);
    g.respuesta[sizeof(g.respuesta) - 1] = '\0';
    ok(!hera_cola_encolar(&g),
       "un turno que no cabe se rechaza, no se recorta",
       "se encoló una respuesta recortada");
}

/* ---------------------------------------------------------------------- */

int main(int argc, char **argv) {
    const char *tmp = getenv("TMPDIR");
    snprintf(g_base, sizeof(g_base), "%s/hera_e4_cola",
             tmp && *tmp ? tmp : "/tmp");
    mkdir(g_base, 0755);

    /* Modos para la prueba multiproceso. */
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--sembrar") && i + 1 < argc) {
            const int n = atoi(argv[i + 1]);
            if (!hera_cola_abrir()) return 1;
            for (int t = 1; t <= n; t++) {
                hera_job_t j = hacer((unsigned)t);
                if (!hera_cola_encolar(&j)) return 1;
            }
            return 0;
        }
        if (!strcmp(argv[i], "--tomar-uno")) {
            /* Toma Y CIERRA, que es el ciclo de vida real. Un trabajador que
             * toma y se muere sin cerrar deja el job abandonado a propósito, y
             * la cola hace bien en devolverlo: si esta prueba no cerrara,
             * estaría midiendo la recuperación y no la exclusión. */
            if (!hera_cola_abrir()) return 1;
            hera_job_t j;
            if (!hera_cola_tomar(&j)) return 1;
            printf("%s\n", j.id);
            fflush(stdout);
            hera_cola_hecho(j.id, 0, 0);
            return 0;
        }
    }

    int sabotaje = 0;
    for (int i = 1; i < argc; i++)
        if (!strcmp(argv[i], "--sabotaje") && i + 1 < argc)
            sabotaje = atoi(argv[++i]);
    if (sabotaje) printf("\n\033[33mSABOTAJE %d activo — "
                         "la batería DEBE fallar\033[0m\n", sabotaje);

    prueba_idempotencia();
    prueba_durabilidad();
    prueba_tomar();
    prueba_recuperacion();
    prueba_no_robar();
    prueba_fallar_no_bloquea();
    prueba_aplazado();
    prueba_telemetria();
    prueba_entrada_congelada();

    printf("\n%d pruebas · %d fallos\n", g_pruebas, g_fallos);
    if (sabotaje) {
        if (g_fallos == 0) {
            printf("\033[31mLA BATERÍA NO DETECTA EL SABOTAJE %d\033[0m\n", sabotaje);
            return 1;
        }
        printf("\033[32mel sabotaje %d se detecta (%d fallos)\033[0m\n",
               sabotaje, g_fallos);
        return 0;
    }
    return g_fallos ? 1 : 0;
}
