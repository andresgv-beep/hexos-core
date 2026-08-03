/*
 * HERA — perfil y recuperación previa al turno (E3, paso 2)
 *
 * DOS COSAS QUE ESTE MÓDULO NO ES:
 *
 * No es un segundo almacén. `hera_perfil_t` no guarda nada: se DERIVA leyendo
 * `hera_store_confirmados()` cada vez que se pide. Si tuviera estado propio
 * habría dos versiones de la verdad y llegaría el día en que discreparan —
 * y la que gobierna el prompt sería la copia, no el diario auditable.
 *
 * No escribe. La recuperación previa al turno es EXCLUSIVAMENTE LECTORA: no
 * anota, no promociona, no marca nada como usado. Reflexionar sobre lo que ha
 * pasado es trabajo posterior al turno y de otro módulo (`hera_delta.h`). Si
 * recuperar pudiera escribir, leer la memoria la cambiaría, y dos turnos
 * iguales dejarían de dar lo mismo.
 *
 * Solo consume CONFIRMADO. Los candidatos y todo lo importado del almacén
 * legacy están en cuarentena y no aparecen aquí — no es un filtro que se
 * aplique al final, es que la única fuente es `hera_store_confirmados()`.
 */

#ifndef HERA_PROFILE_H
#define HERA_PROFILE_H

#include "hera_store.h"

#define HERA_RELACIONES_MAX 128

/* Un hecho visto como relación: quién, qué y cuál. La "Relationship" del plan
 * no es una tabla aparte — es la clave `sujeto/predicado` del almacén leída
 * por sus dos mitades. */
typedef struct {
    char sujeto[64];
    char predicado[64];
    char valor[HERA_VALOR_MAX];
    char texto[HERA_TEXTO_MAX];
    char evidencia[HERA_ID_MAX];    /* con qué palabras se supo */
    char confirmacion[HERA_ID_MAX]; /* con cuáles se confirmó */
} hera_relacion_t;

typedef struct {
    /* Vacío si no hay un `yo/nombre` CONFIRMADO. Que el nombre estuviera en
     * el `facts.md` legacy no cuenta: eso está en cuarentena, y una identidad
     * sin cita es justo lo que no puede gobernar nada. */
    char            nombre[HERA_VALOR_MAX];
    hera_relacion_t propias[HERA_RELACIONES_MAX];   /* sujeto == "yo" */
    size_t          propias_n;
    hera_relacion_t ajenas[HERA_RELACIONES_MAX];    /* gente y cosas suyas */
    size_t          ajenas_n;
} hera_perfil_t;

/* Deriva el perfil de los hechos confirmados. Determinista: mismo diario,
 * mismo perfil, en el mismo orden (el del diario). No toca el disco. */
void hera_perfil_derivar(hera_perfil_t *out);

/* Recuperación previa al turno: renderiza el perfil como bloque de texto para
 * el prompt, hasta `max_chars`, cortando siempre por hecho entero para que el
 * recorte no cambie el sentido de una frase a medias. Devuelve los bytes
 * escritos. Cadena vacía si no hay nada confirmado — que es lo correcto en un
 * perfil nuevo: hablar sin saber quién eres, no inventarlo.
 *
 * NO ESCRIBE NADA. Lo verifica una prueba que compara el diario byte a byte
 * antes y después. */
size_t hera_recuperar(char *out, size_t cap, size_t max_chars);

#endif /* HERA_PROFILE_H */
