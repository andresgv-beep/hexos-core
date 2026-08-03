/*
 * HERA — almacén de memoria (E3 del plan de evacuación cognitiva)
 *
 * Sustituye a `append_fact` / `append_candidate` / `memory_is_duplicate` de
 * `helios_chat.cpp`, que sabían añadir líneas pero no sustituirlas.
 *
 * CUATRO REGLAS QUE EL TIPO HACE CUMPLIR, no la buena voluntad de quien llama:
 *
 * 1. NINGÚN RECUERDO NACE SIN EVIDENCIA, Y LA EVIDENCIA CUBRE LA FRASE ENTERA.
 *    Un hecho solo se crea citando el id de algo que la persona escribió, y en
 *    UNA MISMA FRASE de ese texto tienen que aparecer el sujeto, el valor y la
 *    misma polaridad. No basta con que el dato ande suelto por ahí: de "Luis
 *    vive en Bilbao" no sale `ana/ciudad = Bilbao`, porque "ana" no está en esa
 *    frase; y de "me gusta el café" no sale "no me gusta el café", porque la
 *    negación no está. Por eso "Ana vive en Bilbao" es imposible de escribir si
 *    nadie lo ha dicho: no hay camino.
 *
 * 2. PROPONER Y CONFIRMAR SON COSAS DISTINTAS. `hera_store_proponer()` solo
 *    crea CANDIDATOS y no acepta ascender nada. Confirmar exige el id de una
 *    intervención registrada de la persona, y esa cita queda guardada: sin
 *    ella no hay ascenso. Un llamante descuidado no puede colar una extracción
 *    del modelo como hecho porque no existe el parámetro para hacerlo.
 *
 * 3. CORREGIR SUSTITUYE, EN UN SOLO EVENTO. La corrección es UNA línea del
 *    diario que crea el hecho nuevo y jubila el viejo a la vez. Si el proceso
 *    muere a medias, esa línea queda incompleta, la relectura la descarta
 *    entera y el estado sigue siendo el de antes. Nunca dos confirmados
 *    contradiciéndose.
 *
 * 4. LOS CANDIDATOS NO SON HECHOS. `hera_store_confirmados()` no los devuelve
 *    nunca — y ahí entra también todo lo importado del almacén legacy, que
 *    llega en cuarentena.
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

/* Sujeto reservado para la propia persona que habla. Es el único que no
 * necesita aparecer literalmente en la frase: quien escribe "vivo en Sevilla"
 * no se nombra a sí mismo, pero es indudablemente el sujeto — lo acredita el
 * ser el autor del texto. Cualquier otro sujeto ("ana", "perro") sí tiene que
 * estar escrito, que es lo que impide atribuirle a uno lo que se dijo de otro. */
#define HERA_SUJETO_YO   "yo"

typedef enum {
    HERA_CANDIDATO = 0,   /* propuesto o importado; NO entra al prompt */
    HERA_CONFIRMADO,      /* la persona lo confirmó, y consta con qué palabras */
    HERA_SUSTITUIDO       /* lo corrigió un hecho posterior */
} hera_estado_t;

typedef enum {
    HERA_OK = 0,
    HERA_RECHAZO_SIN_EVIDENCIA,     /* no cita ninguna cosa dicha */
    HERA_RECHAZO_NO_LITERAL,        /* el dato no está en esas palabras */
    HERA_RECHAZO_SUJETO_AJENO,      /* el dato está, pero se dijo de otro */
    HERA_RECHAZO_POLARIDAD,         /* se dijo, pero negado (o al revés) */
    HERA_RECHAZO_SIN_CONFIRMACION,  /* nadie registró que la persona lo pidiera */
    HERA_RECHAZO_DUPLICADO,         /* ya lo sabemos */
    HERA_RECHAZO_INVALIDO,          /* campos vacíos, mal formados o llenos */
    HERA_RECHAZO_DESCONOCIDO        /* corrige o asciende algo que no existe */
} hera_veredicto_t;

const char *hera_veredicto_nombre(hera_veredicto_t v);
const char *hera_estado_nombre(hera_estado_t e);

typedef struct {
    char          id[HERA_ID_MAX];
    char          clave[HERA_CLAVE_MAX];   /* "sujeto/predicado" */
    char          valor[HERA_VALOR_MAX];   /* el dato en sí */
    char          texto[HERA_TEXTO_MAX];   /* forma legible para el prompt */
    hera_estado_t estado;
    char          evidencia[HERA_ID_MAX];   /* qué dijo que respalda el dato */
    char          confirmacion[HERA_ID_MAX];/* qué dijo al confirmarlo */
    char          origen[16];               /* "persona" | "modelo" | "legacy" */
    char          sustituido_por[HERA_ID_MAX];
    long long     ts;
} hera_hecho_t;

/* Abre (o crea) el diario del perfil apuntado por HELIOS_HOME y reconstruye
 * el estado leyéndolo entero. Devuelve false si el perfil no es escribible.
 * Llamar dos veces recarga. */
bool hera_store_abrir(void);
void hera_store_cerrar(void);

/* Ruta del diario en uso — para informes y pruebas. */
const char *hera_store_ruta(void);

/* ------------------------------------------------------------------ */
/* Evidencia                                                          */
/* ------------------------------------------------------------------ */

/* Registra algo que la persona escribió. Es lo ÚNICO que puede servir de
 * evidencia o de confirmación. Devuelve el id por `out_id` (p.ej. "u7").
 * Lo que dice el modelo no se registra aquí a propósito: si el modelo pudiera
 * fabricar su propia evidencia, la regla 1 no valdría nada. */
bool hera_store_dijo(const char *texto, char *out_id, size_t cap);

/* Texto de una evidencia por id; NULL si no existe. */
const char *hera_store_evidencia(const char *id);

/* ------------------------------------------------------------------ */
/* Hechos                                                             */
/* ------------------------------------------------------------------ */

/* Propone un hecho a partir de una extracción. SIEMPRE entra como CANDIDATO:
 * no hay forma de pedir por esta puerta que nazca confirmado. `clave` es
 * "sujeto/predicado"; usa HERA_SUJETO_YO cuando el sujeto es quien habla. */
hera_veredicto_t hera_store_proponer(const char *clave, const char *valor,
                                     const char *texto,
                                     const char *evidencia_id,
                                     char *out_id, size_t cap);

/* Registra un hecho ya confirmado en un paso: para peticiones explícitas
 * ("guarda en memoria: ..."), donde la misma frase es la evidencia y la
 * confirmación. `confirmacion_id` es obligatorio y puede coincidir con
 * `evidencia_id`, pero hay que nombrarlo: así queda escrito de quién salió. */
hera_veredicto_t hera_store_registrar(const char *clave, const char *valor,
                                      const char *texto,
                                      const char *evidencia_id,
                                      const char *confirmacion_id,
                                      char *out_id, size_t cap);

/* Asciende un candidato. `confirmacion_id` tiene que ser una intervención
 * registrada de la persona, DISTINTA y POSTERIOR a la que originó el
 * candidato; si no, se rechaza. Aceptar la misma frase sería contarse a sí
 * mismo: de "creo que me mudo a Girona" saldrían el candidato Y su
 * confirmación, y una extracción del modelo se quedaría confirmada sin que
 * nadie hubiera asentido. Que un "sí, guárdalo" signifique de verdad
 * asentimiento es cosa del CK; aquí solo se exige que exista un turno
 * posterior al que señalar.
 *
 * La cita queda en el hecho: después se puede preguntar "¿por qué crees esto?"
 * y contestar con sus palabras exactas. */
hera_veredicto_t hera_store_confirmar(const char *id,
                                      const char *confirmacion_id);

/* Corrige el hecho vigente de `clave`. Es UN SOLO evento: o entra el nuevo y
 * cae el viejo, o no pasa nada. Falla si no había nada vigente que corregir —
 * una corrección sin corregido es un hecho nuevo, y llamarlo corrección
 * esconde que la memoria no tenía lo que creías. */
hera_veredicto_t hera_store_corregir(const char *clave, const char *valor,
                                     const char *texto,
                                     const char *evidencia_id,
                                     const char *confirmacion_id,
                                     char *out_id, size_t cap);

/* ------------------------------------------------------------------ */
/* Ensayo — el mismo veredicto sin escribir nada                      */
/* ------------------------------------------------------------------ */
/* Recorren EXACTAMENTE las mismas comprobaciones que sus gemelas y se paran
 * justo antes de tocar el disco. Comparten camino a propósito: una validación
 * escrita aparte acabaría divergiendo de la de verdad, y un ensayo que dice
 * que sí a algo que el almacén rechaza no sirve para nada.
 *
 * Es lo que permite que la reflexión posterior al turno se valide entera
 * ANTES de decidir si se aplica — y de momento no se aplica. */

hera_veredicto_t hera_store_ensayar_proponer(const char *clave,
                                             const char *valor,
                                             const char *evidencia_id);
hera_veredicto_t hera_store_ensayar_confirmar(const char *id,
                                              const char *confirmacion_id);
hera_veredicto_t hera_store_ensayar_corregir(const char *clave,
                                             const char *valor,
                                             const char *evidencia_id,
                                             const char *confirmacion_id);

/* ------------------------------------------------------------------ */
/* Lectura                                                            */
/* ------------------------------------------------------------------ */

/* Hechos vigentes: CONFIRMADO y no sustituidos. Es lo único que puede entrar
 * al prompt. Devuelve cuántos ha escrito en `out`. */
size_t hera_store_confirmados(hera_hecho_t *out, size_t cap);

/* Todos los hechos en orden de diario, incluidos candidatos y sustituidos:
 * para auditar, nunca para el prompt. */
size_t hera_store_todos(hera_hecho_t *out, size_t cap);

/* Cadena de una clave, del más viejo al vigente. Es la auditoría: enseña qué
 * se creía antes, qué lo sustituyó y con qué palabras. */
size_t hera_store_historial(const char *clave, hera_hecho_t *out, size_t cap);

/* ------------------------------------------------------------------ */
/* Compatibilidad de lectura con el almacén legacy                    */
/* ------------------------------------------------------------------ */

/* Importa `facts.md` y `candidates.md` del perfil UNA sola vez (deja marca en
 * el diario, así que ni reiniciando duplica).
 *
 * TODO ENTRA EN CUARENTENA, como CANDIDATO con origen "legacy" y sin cita.
 * `facts.md` contiene hechos falsos e identidades inventadas — es memoria
 * envenenada conocida. Importarla como autoridad confirmada mudaría la
 * contaminación vieja al almacén nuevo y dejaría la regla 1 en un adorno:
 * bastaría con haber ensuciado el fichero antes. La legacy puede seguir
 * leyéndolos como siempre; aquí no gobiernan nada hasta que la persona los
 * confirme uno a uno, y entonces ya tendrán su cita.
 *
 * `episodic.md` NO se importa: son resúmenes de sesión, no hechos.
 * Devuelve cuántos importó. */
size_t hera_store_importar_legacy(void);

#endif /* HERA_STORE_H */
