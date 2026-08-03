/*
 * HERA — MemoryDelta (E3, paso 3). Ver hera_delta.h.
 *
 * El troceo del array NO cuenta llaves a lo bruto: una llave dentro de un
 * string ("texto":"usa { así") desalinearía el conteo y partiría los objetos
 * por sitios que no son. Es el mismo bug que ya apareció en el parser del
 * runtime en E1, así que aquí se lleva estado de string y de escape desde el
 * principio.
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

/* Campo string dentro de UN objeto ya acotado. */
static bool campo(const char *obj, size_t len, const char *clave,
                  char *out, size_t cap) {
    char pat[64];
    const int pl = snprintf(pat, sizeof(pat), "\"%s\"", clave);
    if (pl <= 0) return false;

    bool en_string = false;
    for (size_t i = 0; i + (size_t)pl <= len; i++) {
        if (obj[i] == '\\' && en_string) { i++; continue; }
        if (obj[i] == '"') {
            /* Una clave empieza en comilla; comprobamos aquí antes de
             * cambiar de estado, porque la clave ES un string. */
            if (!en_string && memcmp(obj + i, pat, (size_t)pl) == 0) {
                size_t j = i + (size_t)pl;
                while (j < len && (obj[j] == ' ' || obj[j] == ':')) j++;
                if (j >= len || obj[j] != '"') return false;
                j++;
                size_t o = 0;
                for (; j < len && o + 1 < cap; j++) {
                    if (obj[j] == '\\') {
                        j++;
                        if (j >= len) break;
                        switch (obj[j]) {
                            case 'n':  out[o++] = '\n'; break;
                            case 't':  out[o++] = '\t'; break;
                            case '"':  out[o++] = '"';  break;
                            case '\\': out[o++] = '\\'; break;
                            default:   out[o++] = obj[j];
                        }
                        continue;
                    }
                    if (obj[j] == '"') break;
                    out[o++] = obj[j];
                }
                out[o] = '\0';
                return true;
            }
            en_string = !en_string;
        }
    }
    return false;
}

/* Siguiente objeto `{...}` del array, respetando strings y escapes. */
static const char *siguiente_objeto(const char *p, const char *fin,
                                    size_t *out_len) {
    while (p < fin && *p != '{') {
        if (*p == ']') return NULL;
        p++;
    }
    if (p >= fin) return NULL;

    int prof = 0;
    bool en_string = false;
    for (const char *q = p; q < fin; q++) {
        if (en_string) {
            if (*q == '\\') { q++; continue; }
            if (*q == '"') en_string = false;
            continue;
        }
        if (*q == '"') { en_string = true; continue; }
        if (*q == '{') prof++;
        else if (*q == '}') {
            if (--prof == 0) { *out_len = (size_t)(q - p) + 1; return p; }
        }
    }
    return NULL;   /* objeto sin cerrar: el delta está roto */
}

bool hera_delta_leer(const char *json, hera_delta_t *out) {
    if (!out) return false;
    memset(out, 0, sizeof(*out));
    if (!json) return false;

    const char *arr = strstr(json, "\"memory_delta\"");
    if (!arr) return false;
    arr = strchr(arr + 14, '[');
    if (!arr) return false;

    const char *fin = json + strlen(json);
    const char *p = arr + 1;
    bool roto = false;

    while (out->n < HERA_DELTA_OPS_MAX) {
        size_t len = 0;
        const char *obj = siguiente_objeto(p, fin, &len);
        if (!obj) {
            /* Distinguir "se acabó el array" de "hay un objeto sin cerrar":
             * lo segundo es un delta corrupto y no puede pasar por vacío. */
            const char *r = p;
            while (r < fin && (*r == ' ' || *r == '\n' || *r == ',')) r++;
            if (r < fin && *r == '{') roto = true;
            break;
        }
        p = obj + len;

        hera_delta_op_t *o = &out->ops[out->n];
        memset(o, 0, sizeof(*o));

        char verbo[32] = "";
        campo(obj, len, "op", verbo, sizeof(verbo));
        if (!strcmp(verbo, "proponer"))       o->op = HERA_OP_PROPONER;
        else if (!strcmp(verbo, "confirmar")) o->op = HERA_OP_CONFIRMAR;
        else if (!strcmp(verbo, "corregir"))  o->op = HERA_OP_CORREGIR;
        else                                  o->op = HERA_OP_DESCONOCIDA;

        campo(obj, len, "id",           o->id,           sizeof(o->id));
        campo(obj, len, "clave",        o->clave,        sizeof(o->clave));
        campo(obj, len, "valor",        o->valor,        sizeof(o->valor));
        campo(obj, len, "texto",        o->texto,        sizeof(o->texto));
        campo(obj, len, "evidencia",    o->evidencia,    sizeof(o->evidencia));
        campo(obj, len, "confirmacion", o->confirmacion,
              sizeof(o->confirmacion));

        /* Ensayo contra las reglas REALES. Aquí no se decide nada nuevo: se
         * pregunta al almacén qué diría, y el almacén contesta con el mismo
         * código que usaría al escribir. */
        switch (o->op) {
            case HERA_OP_PROPONER:
                o->veredicto = hera_store_ensayar_proponer(
                    o->clave, o->valor, o->evidencia);
                break;
            case HERA_OP_CONFIRMAR:
                o->veredicto = hera_store_ensayar_confirmar(
                    o->id, o->confirmacion);
                break;
            case HERA_OP_CORREGIR:
                o->veredicto = hera_store_ensayar_corregir(
                    o->clave, o->valor, o->evidencia, o->confirmacion);
                break;
            default:
                o->veredicto = HERA_RECHAZO_INVALIDO;
                break;
        }
#if HERA_SABOTAJE == 22
        /* Sabotaje: el delta se aplica al leerlo. Reflexionar escribiría sin
         * que nadie hubiera decidido aplicarlo. */
        if (o->veredicto == HERA_OK && o->op == HERA_OP_PROPONER)
            hera_store_proponer(o->clave, o->valor, o->texto, o->evidencia,
                                NULL, 0);
#endif
        if (o->veredicto == HERA_OK) out->aceptables++;
        out->n++;
    }

    out->bien_formado = !roto;
    return out->bien_formado;
}

size_t hera_delta_resumir(const hera_delta_t *d, char *out, size_t cap) {
    if (!d || !out || !cap) return 0;
    /* Sin el texto de los recuerdos: un resumen que se copia a un log acaba
     * siendo una copia de la memoria en un sitio sin reglas. */
    const int n = snprintf(out, cap, "%zu ops · %zu aceptables · %zu rechazadas%s",
                           d->n, d->aceptables, d->n - d->aceptables,
                           d->bien_formado ? "" : " · delta mal formado");
    return (n > 0) ? (size_t)n : 0;
}
