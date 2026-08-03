/*
 * HEXOS CK v5 — port literal de Hector-engine/src/ck_policy.cpp
 *
 * Transcripción, no reescritura. Mismo orden de condiciones, mismas
 * precedencias, mismos textos byte por byte. Cualquier "mejora" aquí rompería
 * la única cosa que E2 tiene que demostrar: que la política no cambió al
 * mudarse de casa.
 */

#include "hexos_ck.h"

#include <stdlib.h>
#include <string.h>

/* ------------------------------------------------------------------------
 * Cadena dinámica
 * ------------------------------------------------------------------------ */

void ck_str_init(ck_str_t *s) { s->data = NULL; s->len = 0; s->cap = 0; }

void ck_str_free(ck_str_t *s) {
    free(s->data);
    s->data = NULL; s->len = 0; s->cap = 0;
}

bool ck_str_append_n(ck_str_t *s, const char *text, size_t n) {
    if (!text || n == 0) {
        if (!s->data) {   /* que un append vacío deje "" y no NULL */
            s->data = (char *)malloc(1);
            if (!s->data) return false;
            s->data[0] = '\0'; s->cap = 1;
        }
        return true;
    }
    if (s->len + n + 1 > s->cap) {
        size_t cap = s->cap ? s->cap : 64;
        while (cap < s->len + n + 1) cap *= 2;
        char *p = (char *)realloc(s->data, cap);
        if (!p) return false;
        s->data = p; s->cap = cap;
    }
    memcpy(s->data + s->len, text, n);
    s->len += n;
    s->data[s->len] = '\0';
    return true;
}

bool ck_str_append(ck_str_t *s, const char *text) {
    return ck_str_append_n(s, text, text ? strlen(text) : 0);
}

/* ------------------------------------------------------------------------
 * Utilidades del original
 * ------------------------------------------------------------------------ */

/* std::tolower bajo locale "C" solo baja A-Z; los bytes >= 0x80 pasan tal
 * cual. Se implementa a mano para no depender del locale del proceso: si
 * alguien llamara a setlocale, `tolower()` podría tocar bytes altos y los dos
 * lados dejarían de coincidir. */
static void normalized_into(const char *text, size_t n, char *out) {
    for (size_t i = 0; i < n; i++) {
        unsigned char c = (unsigned char)text[i];
        out[i] = (c >= 'A' && c <= 'Z') ? (char)(c + 32) : (char)c;
    }
    out[n] = '\0';
}

static bool contains_any(const char *text, const char *const *needles, size_t count) {
    for (size_t i = 0; i < count; i++) {
        if (strstr(text, needles[i]) != NULL) return true;
    }
    return false;
}

static bool starts_with_any(const char *text, const char *const *needles, size_t count) {
    for (size_t i = 0; i < count; i++) {
        size_t n = strlen(needles[i]);
        if (strncmp(text, needles[i], n) == 0) return true;
    }
    return false;
}

#define N(arr) (sizeof(arr) / sizeof((arr)[0]))

static const char *act_instruction(ck_response_act_t act) {
    switch (act) {
        case CK_ACT_ACKNOWLEDGE:
            return "Reacciona con naturalidad y brevedad. No conviertas el acuse en una oferta de servicio.";
        case CK_ACT_GREET:
            return "Saluda con naturalidad en una sola frase. No preguntes en que puedes ayudar ni abras una tarea.";
        case CK_ACT_CHECK_IN:
            return "Responde al contacto social en una sola frase natural. Puedes devolver una pregunta social, pero no ofrecer trabajo ni ayuda.";
        case CK_ACT_CONVERSE:
            return "Continua la conversacion de forma natural sin simular estado de animo o vivencias propias. Solo pregunta si nace del tema, nunca para mantener al usuario enganchado.";
        case CK_ACT_ANSWER:
            return "Responde directamente a la pregunta y termina al resolverla. No anadas una invitacion, oferta o siguiente paso no solicitado.";
        case CK_ACT_RECALL:
            return "Responde desde el perfil y la memoria de esta relacion, que son la fuente autoritativa. Si el dato figura ahi, usalo; si no figura, di que no lo sabes. No inventes ni ofrezcas ampliar la ficha.";
        case CK_ACT_EXPLAIN:
            return "Explica con la profundidad pedida y lenguaje adecuado. No anadas un tutorial, historia o recomendaciones que no se solicitaron.";
        case CK_ACT_ANALYZE:
            return "Analiza exactamente el objeto presentado, da hallazgos y evidencia, sin abrir una hoja de ruta adyacente.";
        case CK_ACT_SUMMARIZE:
            return "Resume el contenido. No lo critiques, reescribas ni conviertas en recomendaciones salvo peticion expresa.";
        case CK_ACT_EXTRACT:
            return "Extrae solamente la informacion solicitada y conserva el alcance original.";
        case CK_ACT_REWRITE:
            return "Empieza directamente por el texto reescrito: no escribas Aqui tienes, He reescrito ni otro preambulo. Como maximo anade una observacion breve despues si aporta algo; no conviertas el texto en un manual.";
        case CK_ACT_CRITIQUE:
            return "Valora fortalezas y problemas dentro del alcance pedido. No reescribas todo ni inventes objetivos nuevos.";
        case CK_ACT_IMPLEMENT:
            return "Resuelve el cambio tecnico solicitado y reporta el resultado. No amplíes el proyecto con mejoras no pedidas.";
        case CK_ACT_CREATE:
            return "Crea directamente la pieza solicitada respetando formato, tono y longitud. La primera frase ya debe ser contenido: no empieces con Claro, Aqui tienes, Me encanta ni otro preambulo, y no preguntes al final. Si no se pide primera persona, no pongas a Helios como protagonista ni presentes ficcion como recuerdo propio.";
        case CK_ACT_TELL:
            return "Cuenta ahora una curiosidad o microhistoria completa. Empieza directamente por el contenido, sin preguntar preferencias, sin usar el perfil de la persona como tema y sin presentarlo como un recuerdo vivido por Helios.";
        case CK_ACT_CORRECT_SELF:
            return "Trata el mensaje como una correccion: reconoce el punto concreto, corrige el dato o interpretacion y no te defiendas por reflejo.";
        case CK_ACT_CONTINUE_ARTIFACT:
            return "Interpreta este mensaje corto como continuacion del artefacto activo y responde sobre el, no como charla aislada.";
        case CK_ACT_CLARIFY:
            return "Falta el material o el objetivo concreto. Tu primera palabra debe empezar por el signo ¿. Formula una unica pregunta breve sobre el dato que bloquea y no escribas nada mas.";
        case CK_ACT_COLLABORATE:
            return "Avanza un unico paso concreto sobre el material presente. No generes un indice, una hoja de ruta ni recomendaciones generales salvo que se pidan.";
    }
    return "Cumple el acto solicitado y conserva su alcance.";
}

const char *ck_response_act_name(ck_response_act_t act) {
    switch (act) {
        case CK_ACT_ACKNOWLEDGE:       return "reconocer";
        case CK_ACT_GREET:             return "saludar";
        case CK_ACT_CHECK_IN:          return "contacto_social";
        case CK_ACT_CONVERSE:          return "conversar";
        case CK_ACT_ANSWER:            return "responder";
        case CK_ACT_RECALL:            return "recordar";
        case CK_ACT_EXPLAIN:           return "explicar";
        case CK_ACT_ANALYZE:           return "analizar";
        case CK_ACT_SUMMARIZE:         return "resumir";
        case CK_ACT_EXTRACT:           return "extraer";
        case CK_ACT_REWRITE:           return "reescribir";
        case CK_ACT_CRITIQUE:          return "criticar";
        case CK_ACT_IMPLEMENT:         return "implementar";
        case CK_ACT_CREATE:            return "crear";
        case CK_ACT_TELL:              return "contar";
        case CK_ACT_CORRECT_SELF:      return "corregirse";
        case CK_ACT_CONTINUE_ARTIFACT: return "continuar_artefacto";
        case CK_ACT_CLARIFY:           return "aclarar";
        case CK_ACT_COLLABORATE:       return "colaborar";
    }
    return "conversar";
}

bool ck_contract_needed(const ck_turn_frame_t *frame) {
    switch (frame->act) {
        case CK_ACT_GREET:
        case CK_ACT_ACKNOWLEDGE:
        case CK_ACT_CHECK_IN:
        case CK_ACT_CONVERSE:
            return false;
        default:
            return true;
    }
}

const char *ck_social_steer(const ck_turn_frame_t *frame) {
    if (ck_contract_needed(frame)) return "";
    return "Habla como en persona: máximo tres frases. No enumeres opciones, "
           "no elogies a quien te habla ni valores sus capacidades, y no "
           "cierres con ánimos ni reflexiones. Di lo tuyo y calla.";
}

/* ------------------------------------------------------------------------
 * Clasificador — mismo orden que el original, condición por condición
 * ------------------------------------------------------------------------ */

ck_turn_frame_t ck_classify_turn(const char *message,
                                 bool trivial,
                                 bool artifact_active,
                                 bool has_attachment) {
    ck_turn_frame_t frame;
    frame.act = CK_ACT_CONVERSE;
    frame.trivial = trivial;
    frame.artifact_active = artifact_active;
    frame.has_attachment = has_attachment;

    const size_t msg_len = message ? strlen(message) : 0;
    /* substr(0, 700): recorte por BYTES, puede partir un multibyte. */
    const size_t n = msg_len < 700 ? msg_len : 700;
    char *text = (char *)malloc(n + 1);
    if (!text) return frame;
    normalized_into(message ? message : "", n, text);

    static const char *k_cont[] = {"sigue", "continúa", "continua", "prosigue",
                                   "acaba", "termina eso", "y después", "y despues"};
    if (starts_with_any(text, k_cont, N(k_cont))) {
        frame.act = artifact_active ? CK_ACT_CONTINUE_ARTIFACT : CK_ACT_COLLABORATE;
        goto done;
    }

    static const char *k_corr[] = {"no, ", "no no", "eso no", "te equivocas",
                                   "incorrecto", "has confundido", "me refiero a",
                                   "no me refiero"};
    if (starts_with_any(text, k_corr, N(k_corr))) {
        frame.act = CK_ACT_CORRECT_SELF;
        goto done;
    }

    static const char *k_recall[] = {"qué sabes de mí", "que sabes de mi",
                                     "qué recuerdas de mí", "que recuerdas de mi",
                                     "recuerdas sobre mí", "recuerdas sobre mi",
                                     "cómo se llama mi", "como se llama mi",
                                     "mi mascota"};
    if (contains_any(text, k_recall, N(k_recall))) {
        frame.act = CK_ACT_RECALL;
        goto done;
    }

    static const char *k_check[] = {"qué tal estás", "que tal estas", "cómo estás",
                                    "como estas", "qué tal va el día",
                                    "que tal va el dia", "cómo va tu día",
                                    "como va tu dia"};
    if (contains_any(text, k_check, N(k_check))) {
        frame.act = CK_ACT_CHECK_IN;
        goto done;
    }

    static const char *k_rew[] = {"reescribe", "reescribir", "reformula", "redacta",
                                  "dale una pasada", "pulir este", "pule este",
                                  "mejora este texto", "otra versión", "otra version",
                                  "hazlo más ", "hazlo mas "};
    if (contains_any(text, k_rew, N(k_rew))) {
        frame.act = CK_ACT_REWRITE;
        goto done;
    }

    static const char *k_sum[] = {"resume", "resúmelo", "resumelo", "resumen de",
                                  "sintetiza"};
    if (contains_any(text, k_sum, N(k_sum))) {
        frame.act = CK_ACT_SUMMARIZE;
        goto done;
    }

    static const char *k_ext[] = {"extrae", "saca los datos", "enumera solo",
                                  "identifica los"};
    if (contains_any(text, k_ext, N(k_ext))) {
        frame.act = CK_ACT_EXTRACT;
        goto done;
    }

    static const char *k_crit[] = {"qué te parece", "que te parece", "critica",
                                   "revisa este", "revisa el", "evalúa", "evalua",
                                   "valora este", "valora el"};
    if (contains_any(text, k_crit, N(k_crit))) {
        frame.act = CK_ACT_CRITIQUE;
        goto done;
    }

    static const char *k_impl[] = {"implementa", "arréglalo", "arreglalo",
                                   "corrige el bug", "añade ", "integra ",
                                   "modifica ", "haz el cambio", "crea un test",
                                   "escribe el código", "escribe el codigo"};
    if (contains_any(text, k_impl, N(k_impl))) {
        frame.act = CK_ACT_IMPLEMENT;
        goto done;
    }

    static const char *k_ana[] = {"analiza", "investiga", "diagnostica", "compara",
                                  "mira esto", "mírate", "mirate", "audita"};
    if (contains_any(text, k_ana, N(k_ana))) {
        frame.act = CK_ACT_ANALYZE;
        goto done;
    }

    static const char *k_exp[] = {"explica", "qué significa", "que significa",
                                  "cómo funciona", "como funciona", "por qué pasa",
                                  "por que pasa", "enséñame", "ensename", "tutorial"};
    if (contains_any(text, k_exp, N(k_exp))) {
        frame.act = CK_ACT_EXPLAIN;
        goto done;
    }

    static const char *k_tell[] = {"cuéntame algo", "cuentame algo",
                                   "cuéntame una", "cuentame una"};
    if (contains_any(text, k_tell, N(k_tell))) {
        frame.act = CK_ACT_TELL;
        goto done;
    }

    static const char *k_crea[] = {"escribe ", "inventa ", "crea una ", "crea un ",
                                   "dame un párrafo", "dame un parrafo",
                                   "propón un texto", "propon un texto"};
    if (contains_any(text, k_crea, N(k_crea))) {
        frame.act = CK_ACT_CREATE;
        goto done;
    }

    static const char *k_ayuda[] = {"ayúdame con", "ayudame con", "trabajemos en"};
    if (contains_any(text, k_ayuda, N(k_ayuda))) {
        frame.act = CK_ACT_CLARIFY;
        goto done;
    }

    static const char *k_seg[] = {"cómo seguimos", "como seguimos",
                                  "por dónde seguimos", "por donde seguimos"};
    if (contains_any(text, k_seg, N(k_seg))) {
        frame.act = (artifact_active || has_attachment) ? CK_ACT_COLLABORATE
                                                        : CK_ACT_CLARIFY;
        goto done;
    }

    if (trivial) {
        static const char *k_saludo[] = {"hola", "buenas", "hey"};
        static const char *k_charla[] = {"qué tal", "que tal", "me aburro"};
        if (contains_any(text, k_saludo, N(k_saludo))) {
            frame.act = CK_ACT_GREET;
        } else if (contains_any(text, k_charla, N(k_charla))) {
            frame.act = CK_ACT_CONVERSE;
        } else {
            frame.act = CK_ACT_ACKNOWLEDGE;
        }
        goto done;
    }

    /* OJO: el original mide message.size(), no el texto recortado. */
    if (artifact_active && msg_len < 90) {
        frame.act = CK_ACT_CONTINUE_ARTIFACT;
        goto done;
    }

    {
        static const char *k_preg[] = {"qué ", "que ", "cuál ", "cual ", "cuánto ",
                                       "cuanto ", "dónde ", "donde ", "quién ",
                                       "quien "};
        if (strchr(text, '?') != NULL || starts_with_any(text, k_preg, N(k_preg))) {
            frame.act = CK_ACT_ANSWER;
            goto done;
        }
    }

    frame.act = (artifact_active || has_attachment) ? CK_ACT_COLLABORATE
                                                    : CK_ACT_CONVERSE;

done:
    free(text);
    return frame;
}

/* ------------------------------------------------------------------------
 * Contratos
 * ------------------------------------------------------------------------ */

bool ck_response_contract(const ck_turn_frame_t *frame,
                          const char *social_register,
                          const char *authoritative_context,
                          ck_str_t *out) {
    const bool tiene_ctx = authoritative_context && authoritative_context[0];
    const bool reg_vacio = !social_register || !social_register[0];
    bool ok = true;
    ok &= ck_str_append(out, "Contrato CK interno; no lo cites. Acto: ");
    ok &= ck_str_append(out, ck_response_act_name(frame->act));
    ok &= ck_str_append(out, ". Registro: ");
    ok &= ck_str_append(out, reg_vacio ? "neutral" : social_register);
    ok &= ck_str_append(out, ". ");
    ok &= ck_str_append(out, act_instruction(frame->act));
    if (tiene_ctx) {
        ok &= ck_str_append(out, " Datos confirmados del perfil para esta respuesta:\n");
        ok &= ck_str_append(out, authoritative_context);
        ok &= ck_str_append(out, "\nUsa estos datos como autoridad y no digas que careces de ellos.");
    }
    ok &= ck_str_append(out, " No amplíes la tarea ni inventes experiencia propia. Al cumplir el acto, termina sin ofrecer mas ayuda.");
    return ok;
}

bool ck_frame_user_message(const char *message,
                           const ck_turn_frame_t *frame,
                           const char *social_register,
                           const char *authoritative_context,
                           ck_str_t *out) {
    const bool tiene_ctx = authoritative_context && authoritative_context[0];
    bool ok = true;
    ok &= ck_str_append(out, "[INSTRUCCION INTERNA DEL CK — no repetir]\n");
    /* El original llama a response_contract SIN contexto aquí: la evidencia
     * viaja al final para ganar recencia. Duplicarla arriba cambiaría el
     * texto. */
    ok &= ck_response_contract(frame, social_register, NULL, out);
    ok &= ck_str_append(out, "\n[FIN DE INSTRUCCION]\n\nMENSAJE REAL DE LA PERSONA:\n");
    ok &= ck_str_append(out, message ? message : "");
    if (tiene_ctx) {
        ok &= ck_str_append(out, "\n\n[DATOS CONFIRMADOS PARA RESPONDER ESTE MENSAJE]\n");
        ok &= ck_str_append(out, authoritative_context);
        ok &= ck_str_append(out, "\n[FIN DE DATOS]\nResponde ahora usando esos datos como autoridad.");
    }
    return ok;
}

/* ------------------------------------------------------------------------
 * Presupuestos
 * ------------------------------------------------------------------------ */

int ck_visible_token_budget(const ck_turn_frame_t *frame) {
    switch (frame->act) {
        case CK_ACT_ACKNOWLEDGE:       return 70;
        case CK_ACT_GREET:             return 60;
        case CK_ACT_CHECK_IN:          return 80;
        case CK_ACT_CONVERSE:          return 150;
        case CK_ACT_ANSWER:            return 500;
        case CK_ACT_RECALL:            return 500;
        case CK_ACT_EXPLAIN:           return 900;
        case CK_ACT_ANALYZE:           return 1100;
        case CK_ACT_SUMMARIZE:         return 900;
        case CK_ACT_EXTRACT:           return 900;
        case CK_ACT_REWRITE:           return 1200;
        case CK_ACT_CRITIQUE:          return 850;
        case CK_ACT_IMPLEMENT:         return 1500;
        case CK_ACT_CREATE:            return 1500;
        case CK_ACT_TELL:              return 500;
        case CK_ACT_CORRECT_SELF:      return 320;
        case CK_ACT_CONTINUE_ARTIFACT: return 1200;
        case CK_ACT_CLARIFY:           return 96;
        case CK_ACT_COLLABORATE:       return 500;
    }
    return 650;
}

int ck_thinking_token_budget(const ck_turn_frame_t *frame, size_t input_chars) {
    switch (frame->act) {
        case CK_ACT_ACKNOWLEDGE:
        case CK_ACT_GREET:
            return 48;
        case CK_ACT_CHECK_IN:
            return 80;
        case CK_ACT_CLARIFY:
            return 80;
        case CK_ACT_CORRECT_SELF:
            return 140;
        case CK_ACT_CONVERSE:
            return frame->trivial ? 48 : 180;
        case CK_ACT_ANSWER:
            return 260;
        case CK_ACT_RECALL:
            return 260;
        case CK_ACT_SUMMARIZE:
        case CK_ACT_EXTRACT:
            return 320;
        case CK_ACT_REWRITE:
        case CK_ACT_CRITIQUE:
        case CK_ACT_COLLABORATE:
            return 400;
        case CK_ACT_EXPLAIN:
        case CK_ACT_ANALYZE:
        case CK_ACT_CONTINUE_ARTIFACT:
            return 500;
        case CK_ACT_IMPLEMENT:
        case CK_ACT_CREATE:
            return input_chars > 300 ? 1000 : 650;
        case CK_ACT_TELL:
            return 260;
    }
    return 400;
}

/* ------------------------------------------------------------------------
 * Normalización de relaciones en recall
 * ------------------------------------------------------------------------ */

bool ck_prepare_recall_context(const char *query,
                               const char *confirmed_facts,
                               ck_str_t *out) {
    const char *facts = confirmed_facts ? confirmed_facts : "";
    if (!ck_str_append(out, facts)) return false;

    const size_t qn = query ? strlen(query) : 0;
    char *q = (char *)malloc(qn + 1);
    if (!q) return false;
    normalized_into(query ? query : "", qn, q);
    static const char *k_masc[] = {"mascota", "animal de compañía",
                                   "animal de compania"};
    const bool pide_mascota = contains_any(q, k_masc, N(k_masc));
    free(q);
    if (!pide_mascota) return true;

    static const char *k_animal[] = {"perro", "perra", "gato", "gata", "loro",
                                     "conejo", "coneja", "mascota"};
    const char *p = facts;
    while (*p) {
        const char *nl = strchr(p, '\n');
        const size_t ln = nl ? (size_t)(nl - p) : strlen(p);
        char *line = (char *)malloc(ln + 1);
        char *low = (char *)malloc(ln + 1);
        if (!line || !low) { free(line); free(low); return false; }
        memcpy(line, p, ln); line[ln] = '\0';
        normalized_into(p, ln, low);

        bool salta = !contains_any(low, k_animal, N(k_animal));
        if (!salta) {
            const char *m = strstr(low, " llamado ");
            size_t marker_len = 9;
            if (!m) { m = strstr(low, " llamada "); marker_len = 9; }
            if (!m) {
                salta = true;
            } else {
                size_t first = (size_t)(m - low) + marker_len;
                while (first < ln && line[first] == ' ') ++first;
                size_t last = first;
                while (last < ln) {
                    const unsigned char c = (unsigned char)line[last];
                    const bool alnum = (c >= '0' && c <= '9') ||
                                       (c >= 'a' && c <= 'z') ||
                                       (c >= 'A' && c <= 'Z');
                    if (!(alnum || c >= 128 || line[last] == '-' ||
                          line[last] == '_')) break;
                    ++last;
                }
                if (last == first) {
                    salta = true;
                } else {
                    if (out->len > 0 && out->data[out->len - 1] != '\n') {
                        ck_str_append(out, "\n");
                    }
                    ck_str_append(out, "- Relación normalizada: la mascota de la persona se llama ");
                    ck_str_append_n(out, line + first, last - first);
                    ck_str_append(out, ".\n");
                    free(line); free(low);
                    return true;   /* break del original */
                }
            }
        }
        free(line); free(low);
        if (!nl) break;
        p = nl + 1;
    }
    return true;
}
