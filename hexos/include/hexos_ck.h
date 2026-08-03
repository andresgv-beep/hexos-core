/*
 * HEXOS - Cognitive Kernel v5: tipos y política de turno
 *
 * E2 del plan de evacuación cognitiva. Port LITERAL de
 * Hector-engine/src/ck_policy.{hpp,cpp} — mismo orden de condiciones, mismas
 * precedencias y los mismos textos byte por byte. Nada se hace "más
 * idiomático" durante el traslado: E2 mueve la política, no la mejora.
 *
 * La equivalencia no se afirma, se demuestra: `tools/ck_diff.py` compara este
 * port con la referencia congelada del original sobre los 51 casos del corpus
 * y exige igualdad exacta.
 *
 * Notas de traducción C++ -> C que importan para la equivalencia:
 *   - `std::tolower` corre bajo locale "C" y solo afecta a A-Z. Aquí se
 *     implementa a mano por bytes para no depender del locale del proceso:
 *     con UTF-8, "QUÉ" baja a "quÉ" en ambos lados, y eso es lo que hay que
 *     reproducir, no lo que sería correcto.
 *   - `char` puede ser con signo: todo se compara como `unsigned char`.
 *   - Los recortes son por BYTES, igual que `substr`, y pueden partir un
 *     carácter multibyte. Replicarlo es obligatorio.
 */

#ifndef HEXOS_CK_H
#define HEXOS_CK_H

#include <stdbool.h>
#include <stddef.h>

/* El registro describe COMO se habla. El acto describe QUE debe hacer la
 * respuesta. Mantenerlos separados evita que "colega" se convierta en una
 * licencia para ampliar la tarea o que "tecnico" vuelva seco cualquier turno. */
typedef enum {
    CK_ACT_ACKNOWLEDGE = 0,
    CK_ACT_GREET,
    CK_ACT_CHECK_IN,
    CK_ACT_CONVERSE,
    CK_ACT_ANSWER,
    CK_ACT_RECALL,
    CK_ACT_EXPLAIN,
    CK_ACT_ANALYZE,
    CK_ACT_SUMMARIZE,
    CK_ACT_EXTRACT,
    CK_ACT_REWRITE,
    CK_ACT_CRITIQUE,
    CK_ACT_IMPLEMENT,
    CK_ACT_CREATE,
    CK_ACT_TELL,
    CK_ACT_CORRECT_SELF,
    CK_ACT_CONTINUE_ARTIFACT,
    CK_ACT_CLARIFY,
    CK_ACT_COLLABORATE
} ck_response_act_t;

typedef struct {
    ck_response_act_t act;
    bool artifact_active;
    bool has_attachment;
    bool trivial;
} ck_turn_frame_t;

/* Cadena que crece sola: el original usa std::string y truncar en un buffer
 * fijo produciría contratos distintos justo en los casos largos. */
typedef struct {
    char  *data;
    size_t len;
    size_t cap;
} ck_str_t;

void ck_str_init(ck_str_t *s);
void ck_str_free(ck_str_t *s);
bool ck_str_append(ck_str_t *s, const char *text);
bool ck_str_append_n(ck_str_t *s, const char *text, size_t n);

const char *ck_response_act_name(ck_response_act_t act);

/* Clasificador deliberadamente conservador y determinista. No pretende
 * entender toda la lengua: fija el acto cuando hay una señal clara y deja el
 * resto como conversación/colaboración acotada. */
ck_turn_frame_t ck_classify_turn(const char *message,
                                 bool trivial,
                                 bool artifact_active,
                                 bool has_attachment);

/* Los actos sociales NO llevan contrato inyectado: los gobiernan el registro
 * y los ejemplos de voz del prefijo. */
bool ck_contract_needed(const ck_turn_frame_t *frame);

/* Freno corto e imperativo para los actos sociales; vacío para el resto. */
const char *ck_social_steer(const ck_turn_frame_t *frame);

/* Contrato efímero. Nunca se guarda en memoria ni en transcripción. */
bool ck_response_contract(const ck_turn_frame_t *frame,
                          const char *social_register,
                          const char *authoritative_context,
                          ck_str_t *out);

/* Fallback para plantillas que solo permiten `system` al inicio. */
bool ck_frame_user_message(const char *message,
                           const ck_turn_frame_t *frame,
                           const char *social_register,
                           const char *authoritative_context,
                           ck_str_t *out);

int ck_visible_token_budget(const ck_turn_frame_t *frame);
int ck_thinking_token_budget(const ck_turn_frame_t *frame, size_t input_chars);

/* Normaliza relaciones obvias que un modelo pequeño puede no enlazar aunque
 * tenga el hecho delante (p.ej. "loro llamado Byteazul" -> mascota=Byteazul). */
bool ck_prepare_recall_context(const char *query,
                               const char *confirmed_facts,
                               ck_str_t *out);

#endif /* HEXOS_CK_H */
