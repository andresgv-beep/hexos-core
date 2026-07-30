/*
 * COGNITIVE KERNEL v3.0 - Stub Implementation
 * HELIOS Cognitive Ecosystem
 * 
 * STUB for testing the ecosystem without a real LLM.
 * Simulates cognitive processing with deterministic outputs.
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <sys/time.h>
#include <math.h>

#include "../include/cognitive_kernel.h"

/* ============================================================================
 * GLOBAL STATE
 * ============================================================================ */

typedef struct {
    ck_config_t config;
    ck_state_t state;
    ck_style_t current_style;
    ck_stats_t stats;
    bool initialized;
    bool hera_connected;
    bool hexos_connected;
} ck_global_t;

static ck_global_t g_ck = {0};

/* ============================================================================
 * UTILITIES
 * ============================================================================ */

static int64_t get_timestamp_ms(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (int64_t)tv.tv_sec * 1000 + tv.tv_usec / 1000;
}

static int64_t get_timestamp(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (int64_t)tv.tv_sec;
}

/* Simple hash for pseudo-random but deterministic behavior */
static uint32_t simple_hash(const char *str) {
    uint32_t hash = 5381;
    while (*str) {
        hash = ((hash << 5) + hash) + *str++;
    }
    return hash;
}

/* ============================================================================
 * LIFECYCLE
 * ============================================================================ */

ck_result_t ck_init(const ck_config_t *config) {
    if (g_ck.initialized) return CK_OK;
    
    memset(&g_ck, 0, sizeof(g_ck));
    
    if (config) {
        g_ck.config = *config;
    } else {
        /* Defaults */
        g_ck.config.default_style.formality = 0.5f;
        g_ck.config.default_style.verbosity = 0.6f;
        g_ck.config.default_style.technicality = 0.7f;
        g_ck.config.default_style.warmth = 0.7f;
        g_ck.config.default_style.humor = 0.3f;
        g_ck.config.enable_reasoning = true;
        g_ck.config.enable_reflection = true;
        g_ck.config.enable_proposals = true;
        g_ck.config.max_reasoning_steps = 4;
        g_ck.config.max_context_tokens = 4096;
        g_ck.config.max_response_tokens = 2048;
        g_ck.config.embedding_dim = CK_DEFAULT_EMBEDDING_DIM;
    }
    
    g_ck.current_style = g_ck.config.default_style;
    g_ck.state = CK_STATE_IDLE;
    g_ck.initialized = true;
    
    printf("[CK] Cognitive Kernel v%s initialized (STUB MODE)\n", CK_VERSION_STRING);
    
    return CK_OK;
}

void ck_shutdown(void) {
    if (!g_ck.initialized) return;
    
    printf("[CK] Shutting down...\n");
    printf("[CK] Turns processed: %lu\n", g_ck.stats.turns_processed);
    
    memset(&g_ck, 0, sizeof(g_ck));
    
    printf("[CK] Shutdown complete\n");
}

bool ck_is_initialized(void) {
    return g_ck.initialized;
}

ck_state_t ck_get_state(void) {
    return g_ck.state;
}

/* ============================================================================
 * CONNECTIONS
 * ============================================================================ */

ck_result_t ck_connect_hera(void) {
    if (!g_ck.initialized) return CK_ERROR_NOT_INITIALIZED;
    g_ck.hera_connected = true;
    printf("[CK] Connected to HERA (simulated)\n");
    return CK_OK;
}

ck_result_t ck_connect_hexos(void) {
    if (!g_ck.initialized) return CK_ERROR_NOT_INITIALIZED;
    g_ck.hexos_connected = true;
    printf("[CK] Connected to HEXOS (simulated)\n");
    return CK_OK;
}

/* ============================================================================
 * CK_PERCEIVE
 * ============================================================================ */

ck_result_t ck_parse_input(const char *text, ck_parsed_input_t *out_parsed) {
    if (!g_ck.initialized || !text || !out_parsed) return CK_ERROR;
    
    memset(out_parsed, 0, sizeof(ck_parsed_input_t));
    
    /* Copy raw text */
    strncpy(out_parsed->raw_text, text, CK_MAX_INPUT_LEN - 1);
    
    /* Simulate token count (rough approximation) */
    out_parsed->token_count = strlen(text) / 4 + 1;
    
    /* Generate pseudo-embedding based on text hash */
    uint32_t hash = simple_hash(text);
    out_parsed->embedding_dim = CK_DEFAULT_EMBEDDING_DIM;
    for (int i = 0; i < CK_DEFAULT_EMBEDDING_DIM; i++) {
        out_parsed->embedding[i] = ((float)((hash + i * 7) % 1000) / 1000.0f) - 0.5f;
    }
    
    /* Detect language (simplified) */
    strcpy(out_parsed->language, "es");  /* Default Spanish */
    
    /* Extract simple entities (words starting with uppercase) */
    out_parsed->entity_count = 0;
    char *copy = strdup(text);
    char *word = strtok(copy, " .,;:!?");
    while (word && out_parsed->entity_count < CK_MAX_ENTITIES) {
        if (isupper(word[0]) && strlen(word) > 2) {
            strncpy(out_parsed->entities[out_parsed->entity_count].text, word, 127);
            strcpy(out_parsed->entities[out_parsed->entity_count].type, "ENTITY");
            out_parsed->entities[out_parsed->entity_count].confidence = 0.8f;
            out_parsed->entity_count++;
        }
        word = strtok(NULL, " .,;:!?");
    }
    free(copy);
    
    out_parsed->timestamp = get_timestamp();
    
    return CK_OK;
}

ck_result_t ck_classify_intent(const ck_parsed_input_t *input, ck_intent_t *out_intent) {
    if (!g_ck.initialized || !input || !out_intent) return CK_ERROR;
    
    memset(out_intent, 0, sizeof(ck_intent_t));
    
    const char *text = input->raw_text;
    
    /* Simple keyword-based classification */
    if (strchr(text, '?') != NULL || 
        strstr(text, "qué") || strstr(text, "cómo") || 
        strstr(text, "what") || strstr(text, "how")) {
        out_intent->primary = CK_INTENT_QUESTION;
        out_intent->requires_memory = true;
    } else if (strstr(text, "recuerd") || strstr(text, "memory") || strstr(text, "remember")) {
        out_intent->primary = CK_INTENT_MEMORY;
        out_intent->requires_memory = true;
    } else if (strstr(text, "proyecto") || strstr(text, "project") || strstr(text, "HELIOS")) {
        out_intent->primary = CK_INTENT_PROJECT;
        out_intent->requires_reasoning = true;
    } else if (strstr(text, "crea") || strstr(text, "genera") || strstr(text, "escribe")) {
        out_intent->primary = CK_INTENT_CREATIVE;
        out_intent->requires_reasoning = true;
    } else if (strstr(text, "hola") || strstr(text, "hello") || strstr(text, "hi")) {
        out_intent->primary = CK_INTENT_CONVERSATION;
    } else {
        out_intent->primary = CK_INTENT_INSTRUCTION;
        out_intent->requires_reasoning = true;
    }
    
    out_intent->confidence = 0.75f;
    out_intent->urgency = 0.5f;
    
    return CK_OK;
}

ck_result_t ck_extract_tags(const ck_parsed_input_t *input,
                             const ck_intent_t *intent,
                             ck_semantic_tags_t *out_tags) {
    if (!g_ck.initialized || !input || !intent || !out_tags) return CK_ERROR;
    
    memset(out_tags, 0, sizeof(ck_semantic_tags_t));
    
    /* Extract concepts from entities */
    for (uint8_t i = 0; i < input->entity_count && out_tags->concept_count < CK_MAX_CONCEPTS; i++) {
        strncpy(out_tags->concepts[out_tags->concept_count++], 
                input->entities[i].text, 63);
    }
    
    /* Add topics based on keywords */
    const char *text = input->raw_text;
    if (strstr(text, "HELIOS") || strstr(text, "helios")) {
        strcpy(out_tags->topics[out_tags->topic_count++], "HELIOS");
    }
    if (strstr(text, "memor")) {
        strcpy(out_tags->topics[out_tags->topic_count++], "memoria");
    }
    if (strstr(text, "código") || strstr(text, "code")) {
        strcpy(out_tags->topics[out_tags->topic_count++], "programación");
    }
    
    /* Sentiment analysis (very simplified) */
    if (strstr(text, "bien") || strstr(text, "bueno") || strstr(text, "great")) {
        out_tags->sentiment = 0.7f;
    } else if (strstr(text, "mal") || strstr(text, "error") || strstr(text, "bad")) {
        out_tags->sentiment = -0.5f;
    } else {
        out_tags->sentiment = 0.0f;
    }
    
    /* Complexity based on length */
    out_tags->complexity = fminf(1.0f, (float)input->token_count / 100.0f);
    
    /* Importance */
    out_tags->importance = intent->requires_memory ? 0.8f : 0.5f;
    
    return CK_OK;
}

/* ============================================================================
 * CK_REMEMBER
 * ============================================================================ */

ck_result_t ck_query_memories(const float *embedding,
                               uint16_t dim,
                               ck_memory_ref_t *out_memories,
                               uint8_t max_memories,
                               uint8_t *out_count) {
    (void)embedding;
    (void)dim;
    
    if (!g_ck.initialized || !out_memories || !out_count) return CK_ERROR;
    
    /* Stub: return simulated memories */
    *out_count = 0;
    
    if (max_memories >= 1) {
        out_memories[0].id = 1001;
        strcpy(out_memories[0].summary, "HELIOS es un sistema cognitivo con memoria persistente");
        out_memories[0].relevance = 0.9f;
        out_memories[0].timestamp = get_timestamp() - 86400;
        (*out_count)++;
    }
    
    if (max_memories >= 2) {
        out_memories[1].id = 1002;
        strcpy(out_memories[1].summary, "El usuario prefiere respuestas técnicas detalladas");
        out_memories[1].relevance = 0.85f;
        out_memories[1].timestamp = get_timestamp() - 3600;
        (*out_count)++;
    }
    
    return CK_OK;
}

ck_result_t ck_build_context(const ck_memory_ref_t *memories,
                              uint8_t memory_count,
                              ck_context_t *out_context) {
    if (!g_ck.initialized || !out_context) return CK_ERROR;
    
    memset(out_context, 0, sizeof(ck_context_t));
    
    /* Copy memories */
    out_context->memory_count = memory_count;
    for (uint8_t i = 0; i < memory_count && i < CK_MAX_MEMORIES; i++) {
        out_context->memories[i] = memories[i];
    }
    
    /* Build identity summary */
    snprintf(out_context->identity_summary, sizeof(out_context->identity_summary),
             "Soy Helios, un sistema cognitivo que recuerda y aprende. "
             "Mi propósito es ser un compañero que mantiene continuidad.");
    
    /* Build recent context from memories */
    if (memory_count > 0) {
        snprintf(out_context->recent_context, sizeof(out_context->recent_context),
                 "Contexto reciente: %s", memories[0].summary);
    }
    
    out_context->total_tokens = 200;  /* Estimate */
    
    return CK_OK;
}

/* ============================================================================
 * CK_THINK
 * ============================================================================ */

ck_result_t ck_reason(const ck_parsed_input_t *input,
                       const ck_context_t *context,
                       ck_reasoning_step_t *out_steps,
                       uint8_t max_steps,
                       uint8_t *out_count) {
    (void)context;
    
    if (!g_ck.initialized || !input || !out_steps || !out_count) return CK_ERROR;
    
    *out_count = 0;
    
    if (!g_ck.config.enable_reasoning) return CK_OK;
    
    /* Generate simple reasoning steps */
    if (max_steps >= 1) {
        snprintf(out_steps[0].thought, sizeof(out_steps[0].thought),
                 "El usuario ha dicho: '%.100s...'", input->raw_text);
        strcpy(out_steps[0].conclusion, "Entendido el input");
        out_steps[0].confidence = 0.9f;
        (*out_count)++;
    }
    
    if (max_steps >= 2) {
        strcpy(out_steps[1].thought, "Verificando contexto y memorias relevantes");
        strcpy(out_steps[1].conclusion, "Contexto integrado");
        out_steps[1].confidence = 0.85f;
        (*out_count)++;
    }
    
    if (max_steps >= 3) {
        strcpy(out_steps[2].thought, "Formulando respuesta coherente con identidad");
        strcpy(out_steps[2].conclusion, "Respuesta preparada");
        out_steps[2].confidence = 0.88f;
        (*out_count)++;
    }
    
    return CK_OK;
}

/* ============================================================================
 * CK_EXPRESS
 * ============================================================================ */

ck_result_t ck_generate_response(const ck_turn_t *turn, ck_response_t *out_response) {
    if (!g_ck.initialized || !turn || !out_response) return CK_ERROR;
    
    int64_t start = get_timestamp_ms();
    
    memset(out_response, 0, sizeof(ck_response_t));
    
    /* Generate response based on intent */
    switch (turn->intent.primary) {
        case CK_INTENT_QUESTION:
            snprintf(out_response->text, sizeof(out_response->text),
                     "Según mi comprensión y los recuerdos disponibles: "
                     "Esta es una respuesta simulada a tu pregunta sobre '%s'. "
                     "En un sistema completo, aquí consultaría mis memorias y "
                     "generaría una respuesta basada en el LLM.",
                     turn->tags.topic_count > 0 ? turn->tags.topics[0] : "el tema");
            break;
            
        case CK_INTENT_PROJECT:
            snprintf(out_response->text, sizeof(out_response->text),
                     "Sobre el proyecto: Recuerdo que estamos trabajando en HELIOS, "
                     "un sistema cognitivo con memoria persistente. Los módulos "
                     "actuales incluyen HEXOS, Memory Core, HNF-EXT, HERA, y el "
                     "Cognitive Kernel (este stub). ¿En qué aspecto puedo ayudarte?");
            break;
            
        case CK_INTENT_MEMORY:
            snprintf(out_response->text, sizeof(out_response->text),
                     "Mis recuerdos indican: %s. "
                     "Este es un sistema de memoria jerárquica (HHMS) con tres niveles: "
                     "esencial (HNF-EXT), activa (RAM), y archivada (disco).",
                     turn->context.memory_count > 0 ? 
                     turn->context.memories[0].summary : "sin memorias específicas");
            break;
            
        case CK_INTENT_CONVERSATION:
            snprintf(out_response->text, sizeof(out_response->text),
                     "¡Hola! Soy Helios, un sistema cognitivo que recuerda y aprende. "
                     "Actualmente estoy funcionando en modo stub (sin LLM real), pero "
                     "puedo demostrar el flujo cognitivo completo: percepción, memoria, "
                     "razonamiento, expresión y reflexión.");
            break;
            
        case CK_INTENT_CREATIVE:
            snprintf(out_response->text, sizeof(out_response->text),
                     "Para una solicitud creativa, en un sistema completo usaría el LLM "
                     "para generar contenido original. En este stub, demuestro que el "
                     "flujo cognitivo está funcionando correctamente a través de todos "
                     "los módulos del ecosistema HELIOS.");
            break;
            
        default:
            snprintf(out_response->text, sizeof(out_response->text),
                     "Entendido. Procesé tu mensaje a través del flujo cognitivo completo: "
                     "percepción → memoria → razonamiento → expresión. Esta es una "
                     "respuesta simulada del Cognitive Kernel stub.");
            break;
    }
    
    out_response->token_count = strlen(out_response->text) / 4;
    out_response->style_used = g_ck.current_style;
    out_response->coherence_score = 0.85f;
    out_response->confidence = 0.80f;
    out_response->generation_time_ms = get_timestamp_ms() - start;
    
    return CK_OK;
}

ck_result_t ck_adapt_style(const ck_semantic_tags_t *tags, ck_style_t *out_style) {
    if (!g_ck.initialized || !tags || !out_style) return CK_ERROR;
    
    *out_style = g_ck.current_style;
    
    /* Adjust based on complexity */
    if (tags->complexity > 0.7f) {
        out_style->technicality = fminf(1.0f, out_style->technicality + 0.2f);
        out_style->verbosity = fminf(1.0f, out_style->verbosity + 0.1f);
    }
    
    /* Adjust based on sentiment */
    if (tags->sentiment > 0.5f) {
        out_style->warmth = fminf(1.0f, out_style->warmth + 0.1f);
    }
    
    return CK_OK;
}

/* ============================================================================
 * CK_REFLECT
 * ============================================================================ */

ck_result_t ck_analyze_turn(const ck_turn_t *turn,
                             ck_learning_t *out_learnings,
                             uint8_t max_learnings,
                             uint8_t *out_count) {
    if (!g_ck.initialized || !turn || !out_learnings || !out_count) return CK_ERROR;
    
    *out_count = 0;
    
    if (!g_ck.config.enable_reflection) return CK_OK;
    
    /* Generate learning if importance is high */
    if (turn->tags.importance > 0.7f && max_learnings >= 1) {
        snprintf(out_learnings[0].insight, sizeof(out_learnings[0].insight),
                 "Interacción sobre %s con importancia %.2f",
                 turn->tags.topic_count > 0 ? turn->tags.topics[0] : "tema general",
                 turn->tags.importance);
        strcpy(out_learnings[0].category, "interaction");
        out_learnings[0].importance = turn->tags.importance;
        out_learnings[0].propose_as_essential = (turn->tags.importance > 0.9f);
        (*out_count)++;
        
        g_ck.stats.learnings_recorded++;
    }
    
    return CK_OK;
}

ck_result_t ck_generate_proposal(const ck_turn_t *turn,
                                  ck_proposal_t *out_proposal,
                                  bool *out_has_proposal) {
    if (!g_ck.initialized || !turn || !out_proposal || !out_has_proposal) return CK_ERROR;
    
    *out_has_proposal = false;
    
    if (!g_ck.config.enable_proposals) return CK_OK;
    
    /* Generate proposal if importance and relevance are high */
    if (turn->tags.importance > 0.85f && turn->learning_count > 0) {
        out_proposal->source_id = simple_hash(turn->input.raw_text);
        snprintf(out_proposal->summary, sizeof(out_proposal->summary),
                 "%.500s", turn->input.raw_text);
        strcpy(out_proposal->concept, turn->tags.topic_count > 0 ? 
               turn->tags.topics[0] : "interaction");
        strcpy(out_proposal->category, "event");
        out_proposal->relevance = turn->tags.importance;
        out_proposal->identity_weight = 0.7f;
        strcpy(out_proposal->justification, "High importance interaction");
        
        *out_has_proposal = true;
        g_ck.stats.proposals_generated++;
    }
    
    return CK_OK;
}

/* ============================================================================
 * MAIN PROCESSING
 * ============================================================================ */

ck_result_t ck_process_turn(const char *input, ck_turn_t *out_turn) {
    if (!g_ck.initialized || !input || !out_turn) return CK_ERROR;
    
    memset(out_turn, 0, sizeof(ck_turn_t));
    out_turn->start_time = get_timestamp_ms();
    
    /* 1. PERCEIVE */
    g_ck.state = CK_STATE_PERCEIVING;
    ck_parse_input(input, &out_turn->input);
    ck_classify_intent(&out_turn->input, &out_turn->intent);
    ck_extract_tags(&out_turn->input, &out_turn->intent, &out_turn->tags);
    
    /* 2. REMEMBER */
    g_ck.state = CK_STATE_REMEMBERING;
    ck_memory_ref_t memories[CK_MAX_MEMORIES];
    uint8_t memory_count;
    ck_query_memories(out_turn->input.embedding, out_turn->input.embedding_dim,
                      memories, CK_MAX_MEMORIES, &memory_count);
    ck_build_context(memories, memory_count, &out_turn->context);
    
    /* 3. THINK */
    g_ck.state = CK_STATE_THINKING;
    ck_reason(&out_turn->input, &out_turn->context,
              out_turn->reasoning, 8, &out_turn->reasoning_step_count);
    
    /* 4. EXPRESS */
    g_ck.state = CK_STATE_EXPRESSING;
    ck_generate_response(out_turn, &out_turn->response);
    
    /* 5. REFLECT */
    g_ck.state = CK_STATE_REFLECTING;
    ck_analyze_turn(out_turn, out_turn->learnings, 4, &out_turn->learning_count);
    ck_generate_proposal(out_turn, &out_turn->proposal, &out_turn->has_proposal);
    
    /* Done */
    g_ck.state = CK_STATE_IDLE;
    out_turn->end_time = get_timestamp_ms();
    
    /* Update stats */
    g_ck.stats.turns_processed++;
    g_ck.stats.total_input_tokens += out_turn->input.token_count;
    g_ck.stats.total_output_tokens += out_turn->response.token_count;
    
    float turn_time = (float)(out_turn->end_time - out_turn->start_time);
    g_ck.stats.avg_response_time_ms = 
        (g_ck.stats.avg_response_time_ms * (g_ck.stats.turns_processed - 1) + turn_time) /
        g_ck.stats.turns_processed;
    g_ck.stats.avg_coherence_score =
        (g_ck.stats.avg_coherence_score * (g_ck.stats.turns_processed - 1) + 
         out_turn->response.coherence_score) / g_ck.stats.turns_processed;
    
    return CK_OK;
}

/* ============================================================================
 * IDENTITY
 * ============================================================================ */

const char* ck_get_name(void) {
    return "Helios";
}

const char* ck_get_purpose(void) {
    return "Ser un compañero cognitivo que recuerda, aprende y crece.";
}

ck_result_t ck_get_style(ck_style_t *out_style) {
    if (!g_ck.initialized || !out_style) return CK_ERROR;
    *out_style = g_ck.current_style;
    return CK_OK;
}

ck_result_t ck_set_style(const ck_style_t *style) {
    if (!g_ck.initialized || !style) return CK_ERROR;
    g_ck.current_style = *style;
    return CK_OK;
}

/* ============================================================================
 * STATISTICS
 * ============================================================================ */

ck_result_t ck_get_stats(ck_stats_t *out_stats) {
    if (!g_ck.initialized || !out_stats) return CK_ERROR;
    g_ck.stats.state = g_ck.state;
    *out_stats = g_ck.stats;
    return CK_OK;
}

/* ============================================================================
 * UTILITY
 * ============================================================================ */

const char* ck_intent_name(ck_intent_type_t intent) {
    const char *names[] = {
        "QUESTION", "INSTRUCTION", "CONVERSATION", "CONTEXT",
        "PROJECT", "MEMORY", "META", "SYSTEM", "EMOTIONAL", "CREATIVE"
    };
    if (intent < sizeof(names)/sizeof(names[0])) {
        return names[intent];
    }
    return "UNKNOWN";
}

const char* ck_state_name(ck_state_t state) {
    const char *names[] = {
        "IDLE", "PERCEIVING", "REMEMBERING", "THINKING",
        "EXPRESSING", "REFLECTING", "CONSOLIDATING"
    };
    if (state < sizeof(names)/sizeof(names[0])) {
        return names[state];
    }
    return "UNKNOWN";
}
