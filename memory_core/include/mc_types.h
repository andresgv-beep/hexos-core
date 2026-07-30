/*
 * MEMORY CORE v3.0 - Types and Structures
 * HELIOS Cognitive Ecosystem
 * 
 * "Los recuerdos viven aquí. Pero la memoria vive en HERA."
 */

#ifndef MC_TYPES_H
#define MC_TYPES_H

#include <stdint.h>
#include <stdbool.h>
#include <time.h>

/* ============================================================================
 * VERSION
 * ============================================================================ */

#define MC_VERSION_MAJOR    3
#define MC_VERSION_MINOR    0
#define MC_VERSION_PATCH    0
#define MC_VERSION_STRING   "3.0.0"

/* ============================================================================
 * LIMITS
 * ============================================================================ */

#define MC_MAX_STRING           256
#define MC_MAX_TEXT             4096
#define MC_MAX_TAGS             16
#define MC_MAX_ENTITIES         32
#define MC_MAX_QUERY_RESULTS    100
#define MC_MAX_EMBEDDING_DIM    4096
#define MC_DEFAULT_EMBEDDING_DIM 384

#define MC_INDEX_MAGIC          0x4D494458  /* "MIDX" */
#define MC_INDEX_VERSION        0x0300

/* ============================================================================
 * ENUMS
 * ============================================================================ */

/* Memory item type */
typedef enum {
    MC_TYPE_EPISODIC = 0,       /* Event memory (what happened) */
    MC_TYPE_SEMANTIC = 1,       /* Concept memory (what it means) */
    MC_TYPE_PROJECT = 2,        /* Project/task memory */
    MC_TYPE_IDENTITY = 3        /* Identity-related memory */
} mc_item_type_t;

/* Memory item flags */
typedef enum {
    MC_FLAG_ACTIVE      = 0x0001,   /* In active RAM */
    MC_FLAG_ARCHIVED    = 0x0002,   /* On disk */
    MC_FLAG_CANDIDATE   = 0x0004,   /* Candidate for HNF-EXT */
    MC_FLAG_ESSENTIAL   = 0x0008,   /* Already in HNF-EXT (reference only) */
    MC_FLAG_PINNED      = 0x0010,   /* Don't auto-degrade */
    MC_FLAG_DIRTY       = 0x0020    /* Modified, pending sync */
} mc_item_flags_t;

/* Storage pressure level */
typedef enum {
    MC_PRESSURE_LOW = 0,        /* < 50% of limit */
    MC_PRESSURE_MEDIUM,         /* 50-75% of limit */
    MC_PRESSURE_HIGH,           /* 75-90% of limit */
    MC_PRESSURE_CRITICAL        /* > 90% of limit */
} mc_pressure_t;

/* Event types (Memory Core -> HERA) */
typedef enum {
    MC_EVT_STORAGE_PRESSURE = 1,
    MC_EVT_ITEM_ACCESSED,
    MC_EVT_ARCHIVE_COMPLETE,
    MC_EVT_CANDIDATE_READY,
    MC_EVT_INTEGRITY_ERROR
} mc_event_type_t;

/* Command types (HERA -> Memory Core) */
typedef enum {
    MC_CMD_STORE = 1,
    MC_CMD_RETRIEVE,
    MC_CMD_SEARCH,
    MC_CMD_ARCHIVE,
    MC_CMD_DEGRADE,
    MC_CMD_PREPARE_CHECKPOINT,
    MC_CMD_RESTORE_CHECKPOINT,
    MC_CMD_VERIFY_INTEGRITY,
    MC_CMD_GET_STATS
} mc_command_type_t;

/* Result codes */
typedef enum {
    MC_OK = 0,
    MC_ERROR,
    MC_ERROR_NOT_FOUND,
    MC_ERROR_NO_MEMORY,
    MC_ERROR_IO,
    MC_ERROR_INTEGRITY,
    MC_ERROR_FULL,
    MC_ERROR_INVALID
} mc_result_t;

/* ============================================================================
 * CORE STRUCTURES
 * ============================================================================ */

/* Memory Item - 48 bytes aligned */
typedef struct {
    uint64_t id;                /* Unique ID (hash) */
    uint8_t  type;              /* mc_item_type_t */
    uint8_t  reserved1[3];
    int64_t  timestamp;         /* Unix timestamp (creation) */
    int64_t  last_access;       /* Unix timestamp (last access) */
    uint32_t access_count;      /* Times accessed */
    float    relevance;         /* 0.0 - 1.0 */
    uint64_t content_hash;      /* Hash of content */
    uint64_t embedding_id;      /* Reference to embedding (if exists) */
    uint16_t flags;             /* mc_item_flags_t */
    uint16_t reserved2;
} mc_item_t;

/* Episodic Event */
typedef struct {
    uint64_t id;
    int64_t  timestamp;
    char     type[32];                      /* "conversation", "observation", etc */
    char     text[MC_MAX_TEXT];             /* Event description */
    char     tags[MC_MAX_TAGS][64];         /* Tags */
    uint8_t  tag_count;
    char     entities[MC_MAX_ENTITIES][64]; /* Named entities */
    uint8_t  entity_count;
    float    relevance;
    char     context_id[64];                /* Session/context ID */
} mc_episodic_event_t;

/* Semantic Concept */
typedef struct {
    uint64_t id;
    char     name[MC_MAX_STRING];
    char     category[64];
    int64_t  first_seen;
    int64_t  last_seen;
    uint32_t frequency;
    float    importance;
} mc_concept_t;

/* Embedding */
typedef struct {
    uint64_t id;
    uint64_t source_id;         /* Reference to MemoryItem */
    uint16_t dimension;
    char     model[64];         /* Model used to generate */
    float    *vector;           /* Dynamically allocated */
} mc_embedding_t;

/* Relation between concepts */
typedef struct {
    uint64_t source_id;
    uint64_t target_id;
    char     relation_type[64];
    float    strength;
} mc_relation_t;

/* ============================================================================
 * INDEX STRUCTURES
 * ============================================================================ */

/* Index header - 64 bytes */
typedef struct {
    uint32_t magic;             /* MC_INDEX_MAGIC */
    uint16_t version;           /* MC_INDEX_VERSION */
    uint16_t flags;
    uint64_t item_count;
    int64_t  created;
    int64_t  modified;
    uint64_t checksum;          /* CRC64 of content */
    uint8_t  reserved[24];
} mc_index_header_t;

/* ============================================================================
 * PROPOSAL AND STATS
 * ============================================================================ */

/* Core Memory Proposal (for HNF-EXT candidates) */
typedef struct {
    uint64_t source_id;
    char     summary[512];
    char     concept[128];
    char     category[64];          /* identity, knowledge, project, event */
    float    relevance_absolute;
    float    identity_weight;
    uint32_t frequency;
    int64_t  first_seen;
    char     justification[512];
} mc_core_proposal_t;

/* Memory Core Statistics */
typedef struct {
    /* RAM */
    uint64_t active_items;
    uint64_t active_size_mb;
    uint64_t active_limit_mb;
    
    /* Disk */
    uint32_t archived_days;
    uint64_t archived_items;
    uint64_t archived_size_mb;
    
    /* Indices */
    uint64_t index_items;
    uint32_t candidates_pending;
    
    /* Performance */
    float    avg_query_ms;
    int64_t  last_archive;
    int64_t  last_compact;
    
    /* Pressure */
    mc_pressure_t pressure_level;
} mc_stats_t;

/* ============================================================================
 * CHECKPOINT STRUCTURES
 * ============================================================================ */

typedef struct {
    int64_t  timestamp;
    uint64_t hot_item_count;
    uint64_t *hot_item_ids;         /* Dynamically allocated */
    uint32_t pending_candidate_count;
    uint64_t *pending_candidates;   /* Dynamically allocated */
    mc_stats_t stats;
} mc_checkpoint_t;

/* ============================================================================
 * QUERY STRUCTURES
 * ============================================================================ */

typedef struct {
    char     text[MC_MAX_TEXT];     /* Query text */
    mc_item_type_t type_filter;     /* Filter by type (-1 for all) */
    int64_t  time_start;            /* Time range start (0 for no limit) */
    int64_t  time_end;              /* Time range end (0 for no limit) */
    float    min_relevance;         /* Minimum relevance (0.0 for all) */
    uint32_t max_results;           /* Maximum results to return */
    bool     semantic_search;       /* Use embeddings for search */
} mc_query_t;

typedef struct {
    mc_item_t *items;               /* Results array */
    uint32_t count;                 /* Number of results */
    float    query_time_ms;         /* Time taken */
} mc_query_result_t;

/* ============================================================================
 * CONFIGURATION
 * ============================================================================ */

typedef struct {
    /* Paths */
    char     base_path[256];        /* Base storage path */
    char     memory_path[256];      /* /memory/ directory */
    
    /* Limits (set by HEXOS via HERA) */
    uint64_t ram_active_limit_mb;
    uint32_t daily_episodic_limit;
    uint32_t daily_semantic_limit;
    uint32_t max_query_results;
    uint16_t embedding_dimension;
    
    /* Behavior */
    bool     auto_archive;          /* Auto-archive at end of day */
    bool     enable_embeddings;     /* Generate embeddings */
    uint32_t archive_hour;          /* Hour to run archive (0-23) */
} mc_config_t;

#endif /* MC_TYPES_H */
