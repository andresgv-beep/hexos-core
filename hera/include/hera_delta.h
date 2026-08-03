/*
 * HERA — MemoryDelta: la salida de la reflexión posterior al turno (E3, paso 3)
 *
 * DESCONECTADO A PROPÓSITO. Aquí se parsea y se valida; NO se aplica. No hay
 * función de aplicar y no es un olvido: mientras el cableado no exista, una
 * puerta que escriba es una puerta por la que se cuela algo sin que nadie lo
 * haya revisado. Cuando llegue, será una llamada explícita en el sitio del
 * plan, no un efecto secundario de reflexionar.
 *
 * POR QUÉ TIPADO Y NO PROSA. El fallo del 2026-07-31 fue que el destilador
 * escribió un relato entero en el diario y el modelo lo recitaba al día
 * siguiente como si fuera un recuerdo. Con una salida de campos declarados eso
 * es imposible de expresar: no existe el campo "párrafo libre". Lo que el
 * modelo no puede decir, no lo puede colar.
 *
 * Forma que se espera del modelo:
 *
 *   {"memory_delta":[
 *     {"op":"proponer","clave":"perro/nombre","valor":"Rufo",
 *      "texto":"Su perro se llama Rufo","evidencia":"u3"},
 *     {"op":"confirmar","id":"f2","confirmacion":"u5"},
 *     {"op":"corregir","clave":"yo/ciudad","valor":"Girona",
 *      "texto":"Vive en Girona","evidencia":"u7","confirmacion":"u7"}
 *   ]}
 *
 * Cada operación se ensaya contra las reglas REALES del almacén
 * (`hera_store_ensayar_*`), así que un delta que el modelo se invente se
 * rechaza por el mismo motivo por el que se rechazaría al escribirlo: sin
 * evidencia, sujeto ajeno, polaridad al revés, sin confirmación.
 */

#ifndef HERA_DELTA_H
#define HERA_DELTA_H

#include "hera_store.h"

#define HERA_DELTA_OPS_MAX 32

typedef enum {
    HERA_OP_PROPONER = 0,
    HERA_OP_CONFIRMAR,
    HERA_OP_CORREGIR,
    HERA_OP_DESCONOCIDA      /* el modelo se inventó un verbo */
} hera_op_t;

const char *hera_op_nombre(hera_op_t op);

typedef struct {
    hera_op_t        op;
    char             id[HERA_ID_MAX];            /* solo confirmar */
    char             clave[HERA_CLAVE_MAX];
    char             valor[HERA_VALOR_MAX];
    char             texto[HERA_TEXTO_MAX];
    char             evidencia[HERA_ID_MAX];
    char             confirmacion[HERA_ID_MAX];
    hera_veredicto_t veredicto;   /* qué diría el almacén si se aplicara */
} hera_delta_op_t;

typedef struct {
    hera_delta_op_t ops[HERA_DELTA_OPS_MAX];
    size_t          n;
    size_t          aceptables;   /* cuántas pasarían las reglas */
    bool            bien_formado; /* false si el JSON no se pudo leer */
} hera_delta_t;

/* Lee el delta y ensaya cada operación contra el almacén abierto. NO ESCRIBE
 * NADA — lo verifica una prueba que compara el diario byte a byte antes y
 * después. Devuelve false si el JSON está roto o no trae `memory_delta`.
 *
 * Que una operación traiga `veredicto == HERA_OK` significa que pasaría las
 * reglas HOY. No significa que se haya hecho: aplicar no existe todavía. */
bool hera_delta_leer(const char *json, hera_delta_t *out);

/* Resumen legible para telemetría: "3 ops · 1 aceptable · 2 rechazadas".
 * Nunca incluye el texto de los recuerdos — un resumen que se copia a un log
 * acaba siendo una copia de la memoria en un sitio sin reglas. */
size_t hera_delta_resumir(const hera_delta_t *d, char *out, size_t cap);

#endif /* HERA_DELTA_H */
