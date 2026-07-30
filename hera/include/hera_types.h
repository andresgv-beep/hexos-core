/*
 * HERA v3.0 - Types and Structures
 * HELIOS Cognitive Ecosystem
 * 
 * "HERA ES LA MENTE. HEXOS ES EL CUERPO."
 * 
 * La mente recuerda, reflexiona, evoluciona.
 * La mente no sabe de hardware.
 * La mente obedece los límites del cuerpo.
 */

#ifndef HERA_TYPES_H
#define HERA_TYPES_H

#include <stdint.h>
#include <stdbool.h>

/* ============================================================================
 * VERSION
 * ============================================================================ */

#define HERA_VERSION_MAJOR      3
#define HERA_VERSION_MINOR      0
#define HERA_VERSION_STRING     "3.0.0"

/* ============================================================================
 * LIMITS
 * ============================================================================ */

#define HERA_MAX_HOT_MEMORIES       100
#define HERA_MAX_PENDING_CANDIDATES 32
#define HERA_MAX_ACTIVE_PROJECTS    16
#define HERA_MAX_OPEN_TASKS         64
#define HERA_MAX_STABLE_FACTS       128
#define HERA_MAX_PROPOSALS_PER_DAY  3
#define HERA_MAX_SUMMARY_LEN        1024
#define HERA_MAX_INTENT_LEN         256

/* ============================================================================
 * STATES
 * ============================================================================ */

typedef enum {
    HERA_STATE_IDLE = 0,        /* No active cognitive activity */
    HERA_STATE_ACTIVE,          /* Processing queries, evaluating memory */
    HERA_STATE_CONSOLIDATING,   /* Executing sleep cycle */
    HERA_STATE_CHECKPOINT,      /* Preparing checkpoint for HEXOS */
    HERA_STATE_RECOVERING,      /* Restoring from checkpoint */
    HERA_STATE_DEGRADED         /* Operating with reduced memory due to pressure */
} hera_state_t;

/* ============================================================================
 * PRESSURE LEVELS (from HEXOS)
 * ============================================================================ */

typedef enum {
    HERA_PRESSURE_LOW = 0,      /* < 50% of limit */
    HERA_PRESSURE_MEDIUM,       /* 50-75% */
    HERA_PRESSURE_HIGH,         /* 75-90% */
    HERA_PRESSURE_CRITICAL      /* > 90% */
} hera_pressure_t;

/* ============================================================================
 * SIGNALS FROM HEXOS
 * ============================================================================ */

typedef enum {
    HEXOS_SIGNAL_NONE = 0,
    HEXOS_SIGNAL_CHECKPOINT_REQUEST,    /* HERA must prepare semantic checkpoint */
    HEXOS_SIGNAL_MEMORY_PRESSURE,       /* HERA must reduce active memory */
    HEXOS_SIGNAL_SESSION_END,           /* HERA must consolidate for shutdown */
    HEXOS_SIGNAL_THERMAL_WARNING,       /* System is hot, reduce activity */
    HEXOS_SIGNAL_RESUME                 /* Normal operation can resume */
} hexos_signal_t;

/* ============================================================================
 * EVENTS FROM COGNITIVE KERNEL
 * ============================================================================ */

typedef enum {
    CK_EVENT_NONE = 0,
    CK_EVENT_PROPOSE_CORE_MEMORY,   /* CK proposes memory as essential candidate */
    CK_EVENT_MEMORY_QUERY,          /* CK requests relevant memories */
    CK_EVENT_CONTEXT_UPDATE,        /* CK notifies context change */
    CK_EVENT_TURN_COMPLETE,         /* CK finished processing a turn */
    CK_EVENT_LEARNING               /* CK learned something new */
} ck_event_type_t;

/* ============================================================================
 * RESPONSES TO COGNITIVE KERNEL
 * ============================================================================ */

typedef enum {
    HERA_RESPONSE_OK = 0,
    HERA_RESPONSE_MEMORIES_FOUND,
    HERA_RESPONSE_NO_MEMORIES,
    HERA_RESPONSE_PROPOSAL_ACCEPTED,
    HERA_RESPONSE_PROPOSAL_REJECTED,
    HERA_RESPONSE_PROPOSAL_PENDING,
    HERA_RESPONSE_BUSY,
    HERA_RESPONSE_ERROR
} hera_response_t;

/* ============================================================================
 * RESULT CODES
 * ============================================================================ */

typedef enum {
    HERA_OK = 0,
    HERA_ERROR,
    HERA_ERROR_NOT_INITIALIZED,
    HERA_ERROR_BUSY,
    HERA_ERROR_MEMORY_FULL,
    HERA_ERROR_INVALID,
    HERA_ERROR_LIMIT_EXCEEDED
} hera_result_t;

/* ============================================================================
 * CORE MEMORY PROPOSAL (from CK)
 * ============================================================================ */

typedef struct {
    uint64_t source_id;             /* Original memory ID in Memory Core */
    char     summary[512];          /* Compact summary */
    char     concept[128];          /* Main concept */
    char     category[64];          /* identity, knowledge, project, event */
    float    relevance;             /* 0.0 - 1.0 */
    float    identity_weight;       /* Importance for identity */
    uint32_t frequency;             /* Times accessed */
    int64_t  first_seen;            /* When it first appeared */
    char     justification[256];    /* Why it should be essential */
} hera_proposal_t;

/* ============================================================================
 * MEMORY QUERY
 * ============================================================================ */

typedef struct {
    float    *embedding;            /* Query embedding vector */
    uint16_t embedding_dim;         /* Embedding dimension */
    char     text_query[256];       /* Optional text query */
    uint32_t max_results;           /* Maximum results to return */
    float    min_relevance;         /* Minimum relevance threshold */
    bool     include_archived;      /* Search archived memories too */
    int64_t  time_start;            /* Time range start (0 = no limit) */
    int64_t  time_end;              /* Time range end (0 = no limit) */
} hera_memory_query_t;

/* ============================================================================
 * CHECKPOINT STRUCTURE (for HEXOS continuity)
 * ============================================================================ */

typedef struct {
    int64_t  timestamp;
    char     conversation_summary[HERA_MAX_SUMMARY_LEN];
    
    /* Stable facts */
    char     stable_facts[HERA_MAX_STABLE_FACTS][256];
    uint32_t stable_fact_count;
    
    /* Open tasks */
    char     open_tasks[HERA_MAX_OPEN_TASKS][256];
    uint32_t open_task_count;
    
    /* Active projects */
    char     active_projects[HERA_MAX_ACTIVE_PROJECTS][128];
    uint32_t active_project_count;
    
    /* Current user intent */
    char     user_intent[HERA_MAX_INTENT_LEN];
    
    /* Identity snapshot */
    uint32_t identity_hash;
    
    /* Hot memory IDs */
    uint64_t hot_memory_ids[HERA_MAX_HOT_MEMORIES];
    uint32_t hot_memory_count;
} hera_checkpoint_t;

/* ============================================================================
 * CONSOLIDATION RESULT
 * ============================================================================ */

typedef struct {
    int64_t  timestamp;
    uint32_t memories_archived;
    uint32_t memories_degraded;
    uint32_t candidates_evaluated;
    uint32_t candidates_promoted;
    uint64_t ram_freed_mb;
    float    duration_ms;
} hera_consolidation_result_t;

/* ============================================================================
 * HHMS LEVELS (Helios Hierarchical Memory System)
 * ============================================================================ */

typedef enum {
    HHMS_LEVEL_ESSENTIAL = 1,   /* HNF-EXT: permanent, identity-critical */
    HHMS_LEVEL_ACTIVE = 2,      /* RAM: current session, working memory */
    HHMS_LEVEL_ARCHIVED = 3     /* Disk: past days, on-demand access */
} hhms_level_t;

/* ============================================================================
 * MEMORY MOVEMENT
 * ============================================================================ */

typedef enum {
    HERA_MOVE_PROMOTE,          /* Level 3→2: Archive to RAM */
    HERA_MOVE_DEGRADE,          /* Level 2→3: RAM to Archive */
    HERA_MOVE_ESSENTIALIZE      /* Level 2→1: RAM to HNF-EXT */
} hera_memory_move_t;

/* ============================================================================
 * STATISTICS
 * ============================================================================ */

typedef struct {
    /* State */
    hera_state_t state;
    hera_pressure_t pressure;
    
    /* Memory counts */
    uint32_t essential_count;       /* In HNF-EXT */
    uint32_t active_count;          /* In RAM */
    uint64_t archived_count;        /* On disk */
    
    /* Proposals */
    uint32_t proposals_today;
    uint32_t proposals_accepted_total;
    uint32_t proposals_rejected_total;
    uint32_t pending_candidates;
    
    /* Consolidation */
    uint32_t consolidations_total;
    int64_t  last_consolidation;
    
    /* Checkpoints */
    uint32_t checkpoints_total;
    int64_t  last_checkpoint;
    
    /* Limits (from HEXOS) */
    uint64_t ram_limit_mb;
    uint64_t ram_used_mb;
} hera_stats_t;

/* ============================================================================
 * CONFIGURATION
 * ============================================================================ */

typedef struct {
    /* Limits (typically set by HEXOS) */
    uint64_t ram_active_limit_mb;
    uint32_t daily_episodic_limit;
    uint32_t daily_semantic_limit;
    uint64_t max_hnf_ext_size_mb;
    
    /* Behavior */
    uint8_t  max_proposals_per_day;
    float    essential_threshold;       /* Min relevance for essential */
    bool     auto_consolidate;          /* Auto consolidate at midnight */
    uint8_t  consolidate_hour;          /* Hour to run (0-23) */
    
    /* Paths */
    char     hnf_ext_path[256];
    char     memory_path[256];
} hera_config_t;

#endif /* HERA_TYPES_H */
