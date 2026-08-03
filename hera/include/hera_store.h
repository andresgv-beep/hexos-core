/*
 * HERA — almacén de memoria (E3 del plan de evacuación cognitiva)
 *
 * Sustituye a `append_fact` / `append_candidate` / `memory_is_duplicate` de
 * `helios_chat.cpp`, que sabían añadir líneas pero no sustituirlas.
 *
 * TRES REGLAS QUE EL TIPO HACE CUMPLIR, no la buena voluntad de quien llama:
 *
 * 1. NINGÚN RECUERDO NACE SIN EVIDENCIA. Un hecho solo se crea citando el id
 *    de algo que la persona escribió de verdad, y el dato tiene que aparecer
 *    LITERALMENTE en esas palabras. Por eso "Ana vive en Bilbao" es imposible
 *    de escribir: si nadie ha escrito nunca "Bilbao", no hay evidencia que
 *    citar y el almacén lo rechaza. No es una comprobación que se pueda
 *    olvidar — es la única puerta de entrada.
 *
 * 2. CORREGIR SUSTITUYE, NO AÑADE. Una corrección marca el hecho viejo como
 *    `superseded` y deja el puntero al nuevo. Las dos filas siguen en el
 *    diario: la corrección es una transición auditable, no una línea más que
 *    contradice a la anterior sin decirlo.
 *
 * 3. LOS CANDIDATOS NO SON HECHOS. Lo que el modelo propone entra como
 *    `candidate` y `hera_store_confirmados()` no lo devuelve nunca. Solo una
 *    confirmación explícita de la persona lo asciende.
 *
 * El diario es de SOLO AÑADIR (`hera.jsonl` dentro de HELIOS_HOME). Nada se
 * reescribe: el estado actual se deriva leyéndolo entero. Eso es lo que hace
 * que una corrección se pueda auditar hacia atrás — si el fichero se pudiera
 * editar, la auditoría contaría lo que quisiera el último que escribió.
 *
 * El almacén está atado a HELIOS_HOME. Dos perfiles son dos diarios, así que
 * un hecho de uno no puede ser evidencia en el otro: no hay código que lo
 * impida porque no hay código que pueda cruzarlos.
 */

#ifndef HERA_STORE_H
#define HERA_STORE_H

#include <stdbool.h>
#include <stddef.h>

#define HERA_ID_MAX      24
#define HERA_CLAVE_MAX   128
#define HERA_VALOR_MAX   256
#define HERA_TEXTO_MAX   512
#define HERA_UTTER_MAX   4096

typedef enum {
    HERA_CANDIDATO = 0,   /* lo propuso el modelo; NO entra al prompt */
    HERA_CONFIRMADO,      /* la persona lo pidió o lo confirmó */
    HERA_SUSTITUIDO       /* lo corrigió un hecho posterior */
} hera_estado_t;

typedef enum {
    HERA_OK = 0,
    HERA_RECHAZO_SIN_EVIDENCIA,   /* no cita ninguna cosa dicha */
    HERA_RECHAZO_NO_LITERAL,      /* el dato no está en esas palabras */
    HERA_RECHAZO_DUPLICADO,       /* ya lo sabemos */
    HERA_RECHAZO_INVALIDO,        /* campos vacíos o demasiado largos */
    HERA_RECHAZO_DESCONOCIDO      /* corrige un hecho que no existe */
} hera_veredicto_t;

const char *hera_veredicto_nombre(hera_veredicto_t v);
const char *hera_estado_nombre(hera_estado_t e);

typedef struct {
    char          id[HERA_ID_MAX];
    char          clave[HERA_CLAVE_MAX];   /* identidad del hecho: qué describe */
    char          valor[HERA_VALOR_MAX];   /* el dato en sí */
    char          texto[HERA_TEXTO_MAX];   /* forma legible para el prompt */
    hera_estado_t estado;
    char          evidencia[HERA_ID_MAX];  /* id de lo que dijo la persona */
    char          origen[16];              /* "persona" | "modelo" | "legacy" */
    char          sustituido_por[HERA_ID_MAX];
    long long     ts;
} hera_hecho_t;

/* Abre (o crea) el diario del perfil apuntado por HELIOS_HOME y reconstruye
 * el estado leyéndolo entero. Devuelve false si el directorio no se puede
 * usar. Llamar dos veces recarga. */
bool hera_store_abrir(void);
void hera_store_cerrar(void);

/* Ruta del diario en uso — para informes y pruebas. */
const char *hera_store_ruta(void);

/* ------------------------------------------------------------------ */
/* Evidencia                                                          */
/* ------------------------------------------------------------------ */

/* Registra algo que la persona escribió. Es lo ÚNICO que puede servir de
 * evidencia después. Devuelve el id por `out_id` (p.ej. "u7"). Lo que dice
 * el modelo no se registra aquí a propósito: si el modelo pudiera fabricar
 * su propia evidencia, la regla 1 no valdría nada. */
bool hera_store_dijo(const char *texto, char *out_id, size_t cap);

/* ------------------------------------------------------------------ */
/* Hechos                                                             */
/* ------------------------------------------------------------------ */

/* Propone un hecho. `evidencia_id` tiene que venir de hera_store_dijo() y el
 * `valor` tiene que aparecer literalmente en ese texto. `confirmado` lo pone
 * a CONFIRMADO en vez de CANDIDATO: solo para peticiones explícitas de la
 * persona ("guarda en memoria: ..."), nunca para extracciones del modelo.
 * `out_id` puede ser NULL. */
hera_veredicto_t hera_store_proponer(const char *clave, const char *valor,
                                     const char *texto,
                                     const char *evidencia_id,
                                     bool confirmado,
                                     char *out_id, size_t cap);

/* Asciende un candidato a confirmado. La confirmación es de la persona. */
hera_veredicto_t hera_store_confirmar(const char *id);

/* Corrige el hecho vigente de `clave`: crea el nuevo (con su evidencia) y
 * marca el viejo como SUSTITUIDO apuntando al nuevo. Falla si no había nada
 * vigente que corregir — una corrección sin corregido es un hecho nuevo, y
 * llamarlo corrección esconde que la memoria no tenía lo que creías. */
hera_veredicto_t hera_store_corregir(const char *clave, const char *valor,
                                     const char *texto,
                                     const char *evidencia_id,
                                     char *out_id, size_t cap);

/* ------------------------------------------------------------------ */
/* Lectura                                                            */
/* ------------------------------------------------------------------ */

/* Hechos vigentes: CONFIRMADO y no sustituidos. Es lo único que puede entrar
 * al prompt. Devuelve cuántos ha escrito en `out`. */
size_t hera_store_confirmados(hera_hecho_t *out, size_t cap);

/* Todos los hechos en orden de diario, incluidos candidatos y sustituidos:
 * para auditar, nunca para el prompt. */
size_t hera_store_todos(hera_hecho_t *out, size_t cap);

/* Cadena de correcciones de una clave, del más viejo al vigente. Es la
 * auditoría: enseña qué se creía antes, qué lo sustituyó y con qué evidencia. */
size_t hera_store_historial(const char *clave, hera_hecho_t *out, size_t cap);

/* Texto de una evidencia por id; NULL si no existe. */
const char *hera_store_evidencia(const char *id);

/* ------------------------------------------------------------------ */
/* Compatibilidad de lectura con el almacén legacy                    */
/* ------------------------------------------------------------------ */

/* Importa `facts.md` y `candidates.md` del mismo perfil UNA sola vez (deja
 * marca en el diario). Los hechos legacy entran como CONFIRMADO con origen
 * "legacy" y SIN evidencia: nacieron antes de que existiera la regla y
 * reinventarles una cita sería falsificarla. Quedan marcados para que una
 * auditoría los distinga a simple vista. La regla 1 sigue intacta para todo
 * lo que nazca a partir de ahora: esta puerta solo lee esos dos ficheros y
 * solo se abre una vez.
 *
 * `episodic.md` NO se importa: son resúmenes de sesión, no hechos, y la
 * legacy los sigue leyendo de su fichero. Devuelve cuántos importó. */
size_t hera_store_importar_legacy(void);

#endif /* HERA_STORE_H */
