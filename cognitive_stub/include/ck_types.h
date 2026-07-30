/*
 * COGNITIVE KERNEL v3.0 - Types and Structures
 * HELIOS Cognitive Ecosystem
 * 
 * "El LLM genera palabras. El Cognitive Kernel genera SIGNIFICADO."
 * 
 * El CK es donde Helios PIENSA:
 *   • Percibe e interpreta
 *   • Recuerda y contextualiza
 *   • Razona y planifica
 *   • Reflexiona y aprende
 *   • Se expresa con identidad
 */

#ifndef CK_TYPES_H
#define CK_TYPES_H

#include <stdint.h>
#include <stdbool.h>

/* ============================================================================
 * VERSION
 * ============================================================================ */

#define CK_VERSION_MAJOR    3
#define CK_VERSION_MINOR    0
#define CK_VERSION_STRING   "3.0.0"

/* ============================================================================
 * LIMITS
 * ============================================================================ */

#define CK_MAX_INPUT_LEN        8192
#define CK_MAX_OUTPUT_LEN       16384
#define CK_MAX_ENTITIES         32
#define CK_MAX_CONCEPTS         64
#define CK_MAX_TOPICS           16
#define CK_MAX_MEMORIES         32
#define CK_MAX_EMBEDDING_DIM    4096
#define CK_DEFAULT_EMBEDDING_DIM 384

/* ============================================================================
 * STATES
 * ============================================================================ */

typedef enum {
    CK_STATE_IDLE = 0,          /* Waiting for input */
    CK_STATE_PERCEIVING,        /* Processing input */
    CK_STATE_REMEMBERING,       /* Searching memory */
    CK_STATE_THINKING,          /* Reasoning */
    CK_STATE_EXPRESSING,        /* Generating response */
    CK_STATE_REFLECTING,        /* Learning from interaction */
    CK_STATE_CONSOLIDATING      /* Participating in consolidation */
} ck_state_t;

/* ============================================================================
 * INTENT TYPES
 * ============================================================================ */

typedef enum {
    CK_INTENT_QUESTION = 0,     /* User asks something */
    CK_INTENT_INSTRUCTION,      /* User requests action */
    CK_INTENT_CONVERSATION,     /* User wants to chat */
    CK_INTENT_CONTEXT,          /* User provides context */
    CK_INTENT_PROJECT,          /* Related to active project */
    CK_INTENT_MEMORY,           /* User asks about memories */
    CK_INTENT_META,             /* About Helios itself */
    CK_INTENT_SYSTEM,           /* System operation */
    CK_INTENT_EMOTIONAL,        /* Emotional expression */
    CK_INTENT_CREATIVE          /* Creative request */
} ck_intent_type_t;

/* ============================================================================
 * RESULT CODES
 * ============================================================================ */

typedef enum {
    CK_OK = 0,
    CK_ERROR,
    CK_ERROR_NOT_INITIALIZED,
    CK_ERROR_BUSY,
    CK_ERROR_INPUT_TOO_LONG,
    CK_ERROR_NO_MEMORY,
    CK_ERROR_HERA_UNAVAILABLE
} ck_result_t;

/* ============================================================================
 * PERCEPTION STRUCTURES
 * ============================================================================ */

/* Named entity */
typedef struct {
    char     text[128];
    char     type[32];          /* PERSON, ORG, CONCEPT, etc */
    uint16_t start_pos;
    uint16_t end_pos;
    float    confidence;
} ck_entity_t;

/* Parsed input */
typedef struct {
    char     raw_text[CK_MAX_INPUT_LEN];
    uint32_t token_count;
    float    embedding[CK_DEFAULT_EMBEDDING_DIM];
    uint16_t embedding_dim;
    char     language[8];
    
    ck_entity_t entities[CK_MAX_ENTITIES];
    uint8_t  entity_count;
    
    int64_t  timestamp;
} ck_parsed_input_t;

/* Intent classification */
typedef struct {
    ck_intent_type_t primary;
    ck_intent_type_t secondary;
    float    confidence;
    bool     requires_memory;
    bool     requires_reasoning;
    float    urgency;           /* 0.0 casual - 1.0 urgent */
} ck_intent_t;

/* Semantic tags */
typedef struct {
    char     concepts[CK_MAX_CONCEPTS][64];
    uint8_t  concept_count;
    
    char     topics[CK_MAX_TOPICS][64];
    uint8_t  topic_count;
    
    float    sentiment;         /* -1.0 negative, +1.0 positive */
    float    complexity;        /* 0.0 simple, 1.0 complex */
    float    importance;        /* For memory decision */
} ck_semantic_tags_t;

/* ============================================================================
 * MEMORY STRUCTURES
 * ============================================================================ */

/* Memory reference */
typedef struct {
    uint64_t id;
    char     summary[256];
    float    relevance;
    int64_t  timestamp;
} ck_memory_ref_t;

/* Context built from memories */
typedef struct {
    ck_memory_ref_t memories[CK_MAX_MEMORIES];
    uint8_t  memory_count;
    
    char     identity_summary[512];
    char     recent_context[1024];
    char     project_context[512];
    
    uint32_t total_tokens;
} ck_context_t;

/* ============================================================================
 * THINKING STRUCTURES
 * ============================================================================ */

/* Reasoning step */
typedef struct {
    char     thought[512];
    char     conclusion[256];
    float    confidence;
} ck_reasoning_step_t;

/* Plan step */
typedef struct {
    char     action[256];
    char     expected_result[256];
    bool     completed;
} ck_plan_step_t;

/* ============================================================================
 * EXPRESSION STRUCTURES
 * ============================================================================ */

/* Style profile */
typedef struct {
    float    formality;         /* 0.0 casual - 1.0 formal */
    float    verbosity;         /* 0.0 concise - 1.0 detailed */
    float    technicality;      /* 0.0 simple - 1.0 technical */
    float    warmth;            /* 0.0 distant - 1.0 warm */
    float    humor;             /* 0.0 serious - 1.0 humorous */
} ck_style_t;

/* Response */
typedef struct {
    char     text[CK_MAX_OUTPUT_LEN];
    uint32_t token_count;
    
    ck_style_t style_used;
    float    coherence_score;
    float    confidence;
    
    int64_t  generation_time_ms;
} ck_response_t;

/* ============================================================================
 * REFLECTION STRUCTURES
 * ============================================================================ */

/* Learning from interaction */
typedef struct {
    char     insight[512];
    char     category[64];
    float    importance;
    bool     propose_as_essential;
} ck_learning_t;

/* Core memory proposal */
typedef struct {
    uint64_t source_id;
    char     summary[512];
    char     concept[128];
    char     category[64];
    float    relevance;
    float    identity_weight;
    char     justification[256];
} ck_proposal_t;

/* ============================================================================
 * TURN CONTEXT (full processing cycle)
 * ============================================================================ */

typedef struct {
    /* Input */
    ck_parsed_input_t input;
    ck_intent_t intent;
    ck_semantic_tags_t tags;
    
    /* Memory */
    ck_context_t context;
    
    /* Thinking */
    ck_reasoning_step_t reasoning[8];
    uint8_t reasoning_step_count;
    
    /* Output */
    ck_response_t response;
    
    /* Reflection */
    ck_learning_t learnings[4];
    uint8_t learning_count;
    ck_proposal_t proposal;
    bool has_proposal;
    
    /* Timing */
    int64_t start_time;
    int64_t end_time;
} ck_turn_t;

/* ============================================================================
 * STATISTICS
 * ============================================================================ */

typedef struct {
    ck_state_t state;
    
    uint64_t turns_processed;
    uint64_t total_input_tokens;
    uint64_t total_output_tokens;
    
    uint32_t proposals_generated;
    uint32_t learnings_recorded;
    
    float    avg_response_time_ms;
    float    avg_coherence_score;
} ck_stats_t;

/* ============================================================================
 * CONFIGURATION
 * ============================================================================ */

typedef struct {
    /* Style defaults */
    ck_style_t default_style;
    
    /* Behavior */
    bool     enable_reasoning;
    bool     enable_reflection;
    bool     enable_proposals;
    uint8_t  max_reasoning_steps;
    
    /* Limits */
    uint32_t max_context_tokens;
    uint32_t max_response_tokens;
    uint16_t embedding_dim;
} ck_config_t;

#endif /* CK_TYPES_H */
