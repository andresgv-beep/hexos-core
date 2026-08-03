/*
 * HERA — MemoryDelta (E3/E4). Ver hera_delta.h para el contrato.
 *
 * Parser ESTRICTO. La primera versión buscaba las claves con `strstr` y
 * troceaba el array contando llaves; eso lee bien un delta bien escrito y
 * también lee "bien" media docena de cosas que no son un delta. Mientras la
 * reflexión estuvo desconectada daba igual; en cuanto la salida de un modelo
 * entre por aquí, todo lo que este parser acepte de más es superficie por la
 * que puede colarse algo que nadie escribió.
 *
 * Ahora se recorre el JSON con un escáner que respeta strings y escapes desde
 * el principio, y todo lo que no esté EXACTAMENTE en el esquema tumba el delta
 * entero. Que sea estricto no lo hace seguro por sí solo — la autoridad sigue
 * viniendo del almacén — pero hace que "lo que el modelo no puede decir" sea
 * una frase con contenido.
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include "hera_delta.h"

#include <stdio.h>
#include <string.h>

const char *hera_op_nombre(hera_op_t op) {
    switch (op) {
        case HERA_OP_PROPONER:    return "proponer";
        case HERA_OP_CONFIRMAR:   return "confirmar";
        case HERA_OP_CORREGIR:    return "corregir";
        case HERA_OP_DESCONOCIDA: return "desconocida";
    }
    return "?";
}

/* ------------------------------------------------------------------------
 * Escáner
 * ------------------------------------------------------------------------ */

typedef struct {
    const char *p, *fin;
    char        motivo[160];
} sc_t;

static bool falla(sc_t *s, const char *m) {
    if (!s->motivo[0]) snprintf(s->motivo, sizeof(s->motivo), "%s", m);
    return false;
}

static void espacios(sc_t *s) {
    while (s->p < s->fin &&
           (*s->p == ' ' || *s->p == '\t' || *s->p == '\n' || *s->p == '\r'))
        s->p++;
}

static bool ver(sc_t *s, char c) {
    espacios(s);
    return s->p < s->fin && *s->p == c;
}

static bool comer(sc_t *s, char c) {
    if (!ver(s, c)) return false;
    s->p++;
    return true;
}

/* Lee un string JSON. `desbordo` avisa si no cabía en el destino: eso NO se
 * trunca en silencio — un valor recortado es un dato distinto, y guardar "Rufo
 * de la casa gr" por "Rufo de la casa grande" es exactamente el tipo de
 * mentira pequeña que después nadie sabe de dónde salió. */
static bool leer_string(sc_t *s, char *out, size_t cap, bool *desbordo) {
    if (!comer(s, '"')) return falla(s, "se esperaba un string");
    size_t o = 0;
    *desbordo = false;
    while (s->p < s->fin) {
        const unsigned char c = (unsigned char)*s->p;
        if (c == '"') {
            s->p++;
            if (out && cap) out[o < cap ? o : cap - 1] = '\0';
            return true;
        }
        if (c == '\\') {
            s->p++;
            if (s->p >= s->fin) return falla(s, "escape sin terminar");
            char d;
            switch (*s->p) {
                case 'n': d = '\n'; break;
                case 't': d = '\t'; break;
                case 'r': d = '\r'; break;
                case 'b': d = '\b'; break;
                case 'f': d = '\f'; break;
                case '"': d = '"';  break;
                case '\\': d = '\\'; break;
                case '/': d = '/';  break;
                case 'u':
                    /* No se admiten escapes \u: nadie los emite en este
                     * esquema y aceptarlos a medias sería peor que no
                     * aceptarlos. */
                    return falla(s, "escape \\u no admitido en el esquema");
                default:
                    return falla(s, "escape desconocido");
            }
            s->p++;
            if (out && o + 1 < cap) out[o++] = d;
            else *desbordo = true;
            continue;
        }
        if (c < 0x20) return falla(s, "carácter de control dentro de un string");
        s->p++;
        if (out && o + 1 < cap) out[o++] = (char)c;
        else *desbordo = true;
    }
    return falla(s, "string sin cerrar");
}

/* Salta un valor cualquiera: hace falta para los campos de nivel superior que
 * no son `memory_delta` y que no nos incumben. */
static bool saltar_valor(sc_t *s) {
    espacios(s);
    if (s->p >= s->fin) return falla(s, "valor vacío");
    if (*s->p == '"') { bool d; return leer_string(s, NULL, 0, &d); }
    if (*s->p == '{' || *s->p == '[') {
        const char abre = *s->p, cierra = (abre == '{') ? '}' : ']';
        int prof = 0;
        while (s->p < s->fin) {
            if (*s->p == '"') { bool d; if (!leer_string(s, NULL, 0, &d)) return false; continue; }
            if (*s->p == abre) prof++;
            else if (*s->p == cierra) { prof--; s->p++; if (!prof) return true; continue; }
            s->p++;
        }
        return falla(s, "objeto o array sin cerrar");
    }
    while (s->p < s->fin && *s->p != ',' && *s->p != '}' && *s->p != ']') s->p++;
    return true;
}

/* ------------------------------------------------------------------------
 * Esquema de una operación
 * ------------------------------------------------------------------------ */

/* Las ÚNICAS claves admitidas. Cualquier otra tumba el delta: un campo que el
 * esquema no conoce es o un modelo inventándose capacidades, o una versión del
 * formato que este código no sabe leer. En los dos casos, seguir adelante es
 * fingir que se entendió. */
static const char *CLAVES[] = {"op", "id", "clave", "valor", "texto",
                               "evidencia", "confirmacion", NULL};

static bool clave_valida(const char *k) {
#if HERA_SABOTAJE == 23
    /* Sabotaje: vale cualquier clave, como el parser viejo. */
    (void)k; return true;
#endif
    for (int i = 0; CLAVES[i]; i++) if (!strcmp(k, CLAVES[i])) return true;
    return false;
}

static bool leer_op(sc_t *s, hera_delta_op_t *o) {
    memset(o, 0, sizeof(*o));
    o->op = HERA_OP_DESCONOCIDA;
    if (!comer(s, '{')) return falla(s, "un elemento del array no es un objeto");

    bool visto[8] = {false};
    char verbo[32] = "";
    bool hay_verbo = false;

    if (!ver(s, '}')) {
        do {
            char k[64];
            bool desb = false;
            if (!leer_string(s, k, sizeof(k), &desb)) return false;
            if (desb || !clave_valida(k)) {
                char m[160];
                snprintf(m, sizeof(m), "clave fuera del esquema: \"%.40s\"", k);
                return falla(s, m);
            }
            if (!comer(s, ':')) return falla(s, "falta ':' tras una clave");

            int idx = 0;
            for (; CLAVES[idx]; idx++) if (!strcmp(k, CLAVES[idx])) break;
            if (visto[idx]) return falla(s, "clave repetida dentro de una operación");
            visto[idx] = true;

            char *dst; size_t cap;
            if      (!strcmp(k, "op"))           { dst = verbo;          cap = sizeof(verbo); hay_verbo = true; }
            else if (!strcmp(k, "id"))           { dst = o->id;          cap = sizeof(o->id); }
            else if (!strcmp(k, "clave"))        { dst = o->clave;       cap = sizeof(o->clave); }
            else if (!strcmp(k, "valor"))        { dst = o->valor;       cap = sizeof(o->valor); }
            else if (!strcmp(k, "texto"))        { dst = o->texto;       cap = sizeof(o->texto); }
            else if (!strcmp(k, "evidencia"))    { dst = o->evidencia;   cap = sizeof(o->evidencia); }
            else                                 { dst = o->confirmacion; cap = sizeof(o->confirmacion); }

            if (!leer_string(s, dst, cap, &desb)) return false;
#if HERA_SABOTAJE == 23
            desb = false;   /* Sabotaje: recortar en silencio. */
#endif
            if (desb) {
                char m[160];
                snprintf(m, sizeof(m), "el campo \"%s\" no cabe: %zu bytes como mucho",
                         k, cap - 1);
                return falla(s, m);
            }
        } while (comer(s, ','));
    }
    if (!comer(s, '}')) return falla(s, "operación sin cerrar");

    if (!hay_verbo) return falla(s, "una operación sin \"op\"");
    if      (!strcmp(verbo, "proponer"))  o->op = HERA_OP_PROPONER;
    else if (!strcmp(verbo, "confirmar")) o->op = HERA_OP_CONFIRMAR;
    else if (!strcmp(verbo, "corregir"))  o->op = HERA_OP_CORREGIR;
    else {
        char m[160];
        snprintf(m, sizeof(m), "verbo inventado: \"%.40s\"", verbo);
        return falla(s, m);
    }

    /* Campos obligatorios por verbo. Faltar uno no es "una operación pobre":
     * es una operación que no se puede evaluar, y evaluarla igual daría un
     * rechazo semántico que esconde un error de formato. */
    const char *falta = NULL;
    if (o->op == HERA_OP_CONFIRMAR) {
        if (!o->id[0])            falta = "id";
        else if (!o->confirmacion[0]) falta = "confirmacion";
    } else {
        if (!o->clave[0])         falta = "clave";
        else if (!o->valor[0])    falta = "valor";
        else if (!o->evidencia[0]) falta = "evidencia";
        else if (o->op == HERA_OP_CORREGIR && !o->confirmacion[0])
            falta = "confirmacion";
    }
#if HERA_SABOTAJE == 23
    /* Sabotaje: un campo obligatorio que falta se deja pasar y ya lo dirá el
     * almacén — escondiendo un error de formato tras un rechazo semántico. */
    falta = NULL;
#endif
    if (falta) {
        char m[160];
        snprintf(m, sizeof(m), "a una \"%s\" le falta \"%s\"", verbo, falta);
        return falla(s, m);
    }
    return true;
}

/* ------------------------------------------------------------------------ */

static bool leer_array(sc_t *s, hera_delta_t *out) {
    if (!comer(s, '[')) return falla(s, "\"memory_delta\" no es un array");
    if (comer(s, ']')) return true;              /* array vacío: válido */
    do {
        if (out->n >= HERA_DELTA_OPS_MAX) {
#if HERA_SABOTAJE == 23
            return true;   /* Sabotaje: truncar en silencio. */
#endif
            char m[160];
            snprintf(m, sizeof(m), "más de %d operaciones en un delta",
                     HERA_DELTA_OPS_MAX);
            return falla(s, m);
        }
        if (!leer_op(s, &out->ops[out->n])) return false;
        out->n++;
    } while (comer(s, ','));
#if HERA_SABOTAJE == 23
    /* Sabotaje: da igual si el array cierra o no. */
    comer(s, ']');
    return true;
#endif
    if (!comer(s, ']')) return falla(s, "el array no se cierra");
    return true;
}

bool hera_delta_leer(const char *json, hera_delta_t *out) {
    if (!out) return false;
    memset(out, 0, sizeof(*out));
    if (!json) { snprintf(out->motivo, sizeof(out->motivo), "delta vacío"); return false; }

    sc_t s = { json, json + strlen(json), {0} };
    bool hay_array = false;

    if (!comer(&s, '{')) {
        falla(&s, "el delta no es un objeto");
    } else if (!ver(&s, '}')) {
        do {
            char k[64];
            bool desb = false;
            if (!leer_string(&s, k, sizeof(k), &desb)) break;
            if (!comer(&s, ':')) { falla(&s, "falta ':' tras una clave"); break; }
            /* Solo cuenta como el array bueno si es una CLAVE de nivel
             * superior. El parser viejo hacía strstr y se habría comido un
             * "memory_delta" escrito dentro del texto de un recuerdo. */
            if (!strcmp(k, "memory_delta") && !desb) {
                if (hay_array) { falla(&s, "dos \"memory_delta\""); break; }
                hay_array = true;
                if (!leer_array(&s, out)) break;
            } else if (!saltar_valor(&s)) break;
        } while (comer(&s, ','));
    }

    if (!s.motivo[0] && !comer(&s, '}')) falla(&s, "el objeto no se cierra");
    if (!s.motivo[0]) {
        espacios(&s);
        if (s.p != s.fin) falla(&s, "basura detrás del delta");
    }
    if (!s.motivo[0] && !hay_array) falla(&s, "no trae \"memory_delta\"");

    if (s.motivo[0]) {
        snprintf(out->motivo, sizeof(out->motivo), "%s", s.motivo);
        out->n = 0;              /* nada a medias: o entero o nada */
        out->aceptables = 0;
        out->bien_formado = false;
        return false;
    }

    /* Solo con el esquema entero validado se pregunta al almacén. Al revés
     * daría veredictos semánticos de operaciones que ni siquiera estaban bien
     * escritas. */
    for (size_t i = 0; i < out->n; i++) {
        hera_delta_op_t *o = &out->ops[i];
        switch (o->op) {
            case HERA_OP_PROPONER:
                o->veredicto = hera_store_ensayar_proponer(o->clave, o->valor,
                                                           o->evidencia);
                break;
            case HERA_OP_CONFIRMAR:
                o->veredicto = hera_store_ensayar_confirmar(o->id,
                                                            o->confirmacion);
                break;
            case HERA_OP_CORREGIR:
                o->veredicto = hera_store_ensayar_corregir(o->clave, o->valor,
                                                           o->evidencia,
                                                           o->confirmacion);
                break;
            default:
                o->veredicto = HERA_RECHAZO_INVALIDO;
                break;
        }
#if HERA_SABOTAJE == 22
        /* Sabotaje: el delta se aplica al leerlo. */
        if (o->veredicto == HERA_OK && o->op == HERA_OP_PROPONER)
            hera_store_proponer(o->clave, o->valor, o->texto, o->evidencia,
                                NULL, 0);
#endif
        if (o->veredicto == HERA_OK) out->aceptables++;
    }

    out->bien_formado = true;
    return true;
}

size_t hera_delta_resumir(const hera_delta_t *d, char *out, size_t cap) {
    if (!d || !out || !cap) return 0;
    /* Sin el texto de los recuerdos: un resumen que se copia a un log acaba
     * siendo una copia de la memoria en un sitio sin reglas. El motivo sí va:
     * describe la FORMA del delta, no lo que decía. */
    int n;
    if (!d->bien_formado)
        n = snprintf(out, cap, "delta rechazado: %s", d->motivo);
    else
        n = snprintf(out, cap, "%zu ops · %zu aceptables · %zu rechazadas",
                     d->n, d->aceptables, d->n - d->aceptables);
    return (n > 0) ? (size_t)n : 0;
}
