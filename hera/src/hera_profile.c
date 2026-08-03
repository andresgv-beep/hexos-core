/*
 * HERA — perfil y recuperación previa al turno (E3, paso 2)
 *
 * Ver hera_profile.h. Todo aquí es lectura: no hay un solo fopen en modo
 * escritura, y eso es la propiedad, no una casualidad de la implementación.
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include "hera_profile.h"

#include <stdio.h>
#include <string.h>

/* Parte "sujeto/predicado". Sin barra, todo es sujeto y el predicado queda
 * vacío — es el caso de las claves legacy, que de todas formas no llegan aquí
 * porque están en cuarentena. */
static void partir_clave(const char *clave, char *suj, size_t suj_cap,
                         char *pred, size_t pred_cap) {
    const char *barra = strchr(clave, '/');
    if (!barra) {
        snprintf(suj, suj_cap, "%s", clave);
        pred[0] = '\0';
        return;
    }
    const size_t n = (size_t)(barra - clave);
    const size_t c = (n < suj_cap - 1) ? n : suj_cap - 1;
    memcpy(suj, clave, c);
    suj[c] = '\0';
    snprintf(pred, pred_cap, "%s", barra + 1);
}

static void a_relacion(const hera_hecho_t *h, hera_relacion_t *r) {
    /* A cero ANTES de rellenar. snprintf termina la cadena pero deja el resto
     * del buffer como estuviera, así que sin esto la vista arrastra basura de
     * pila detrás de cada terminador: dos derivaciones idénticas salían
     * distintas byte a byte y la igualdad no se podía comprobar de un
     * memcmp. Una vista derivada tiene que ser byte a byte reproducible. */
    memset(r, 0, sizeof(*r));
    partir_clave(h->clave, r->sujeto, sizeof(r->sujeto),
                 r->predicado, sizeof(r->predicado));
    snprintf(r->valor, sizeof(r->valor), "%s", h->valor);
    snprintf(r->texto, sizeof(r->texto), "%s", h->texto);
    snprintf(r->evidencia, sizeof(r->evidencia), "%s", h->evidencia);
    snprintf(r->confirmacion, sizeof(r->confirmacion), "%s", h->confirmacion);
}

void hera_perfil_derivar(hera_perfil_t *out) {
    if (!out) return;
    memset(out, 0, sizeof(*out));

    /* ÚNICA fuente. Los candidatos y el legacy en cuarentena no se filtran
     * aquí: es que no salen de aquí. */
    static hera_hecho_t hechos[HERA_RELACIONES_MAX * 2];
#if HERA_SABOTAJE == 20
    /* Sabotaje: el perfil se sirve de TODO, candidatos y legacy incluidos. */
    const size_t n = hera_store_todos(hechos,
                                      sizeof(hechos) / sizeof(hechos[0]));
#else
    const size_t n = hera_store_confirmados(hechos,
                                            sizeof(hechos) / sizeof(hechos[0]));
#endif

    for (size_t i = 0; i < n; i++) {
        hera_relacion_t r;
        a_relacion(&hechos[i], &r);

        if (strcmp(r.sujeto, HERA_SUJETO_YO) == 0) {
            if (strcmp(r.predicado, "nombre") == 0)
                snprintf(out->nombre, sizeof(out->nombre), "%s", r.valor);
            if (out->propias_n < HERA_RELACIONES_MAX)
                out->propias[out->propias_n++] = r;
        } else {
            if (out->ajenas_n < HERA_RELACIONES_MAX)
                out->ajenas[out->ajenas_n++] = r;
        }
    }
}

/* Añade una línea si cabe entera. Devuelve false cuando ya no cabe, para
 * cortar por hecho completo: media frase de memoria no es media memoria, es
 * una frase distinta. */
static bool anadir(char *out, size_t cap, size_t *usado, size_t max_chars,
                   const char *prefijo, const char *texto) {
    char linea[HERA_TEXTO_MAX + 64];
    const int n = snprintf(linea, sizeof(linea), "%s%s\n", prefijo, texto);
    if (n <= 0) return false;
    if (*usado + (size_t)n >= cap) return false;
    if (*usado + (size_t)n > max_chars) return false;
    memcpy(out + *usado, linea, (size_t)n);
    *usado += (size_t)n;
    out[*usado] = '\0';
    return true;
}

size_t hera_recuperar(char *out, size_t cap, size_t max_chars) {
    if (!out || cap == 0) return 0;
    out[0] = '\0';

    hera_perfil_t p;
    hera_perfil_derivar(&p);
    if (p.propias_n == 0 && p.ajenas_n == 0) return 0;

#if HERA_SABOTAJE == 21
    /* Sabotaje: recuperar deja una anotación en el diario — leer la memoria
     * la cambiaría, y dos turnos iguales dejarían de dar lo mismo. */
    { FILE *f = fopen(hera_store_ruta(), "a");
      if (f) { fputs("{\"r\":\"leido\",\"ts\":0}\n", f); fclose(f); } }
#endif

    size_t usado = 0;
    if (p.propias_n) {
        if (!anadir(out, cap, &usado, max_chars, "",
                    "PERFIL DE LA PERSONA ACTUAL (lo que ella misma ha "
                    "confirmado; son datos suyos, no tuyos, y no cambian "
                    "tu identidad):")) return usado;
        for (size_t i = 0; i < p.propias_n; i++)
            if (!anadir(out, cap, &usado, max_chars, "- ", p.propias[i].texto))
                return usado;
    }
    if (p.ajenas_n) {
        if (!anadir(out, cap, &usado, max_chars, "",
                    "Sobre gente y cosas que ha mencionado:")) return usado;
        for (size_t i = 0; i < p.ajenas_n; i++)
            if (!anadir(out, cap, &usado, max_chars, "- ", p.ajenas[i].texto))
                return usado;
    }
    return usado;
}
