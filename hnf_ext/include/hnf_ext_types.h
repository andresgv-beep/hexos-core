/*
 * HNF-EXT v1.0 - Types and Structures
 * HELIOS Cognitive Ecosystem
 * 
 * "HNF-EXT es donde Helios guarda su ALMA"
 * 
 * Aquí vive:
 *   • Quién es (identidad)
 *   • Qué valora (valores)
 *   • Qué recuerda para siempre (strong memories)
 *   • Por qué existe (propósito)
 */

#ifndef HNF_EXT_TYPES_H
#define HNF_EXT_TYPES_H

#include <stdint.h>
#include <stdbool.h>

/* ============================================================================
 * VERSION AND MAGIC
 * ============================================================================ */

#define HNF_EXT_MAGIC           0x48455854  /* "HEXT" */
#define HNF_EXT_VERSION         0x0100      /* v1.0 */

/* ============================================================================
 * LIMITS
 * ============================================================================ */

#define HNF_EXT_MAX_NAME        64
#define HNF_EXT_MAX_PURPOSE     512
#define HNF_EXT_MAX_ORIGIN      1024
#define HNF_EXT_MAX_TRAITS      16
#define HNF_EXT_MAX_VALUES      8
#define HNF_EXT_MAX_MEMORIES    256
#define HNF_EXT_MAX_MEMORY_TEXT 2048

/* ============================================================================
 * FLAGS
 * ============================================================================ */

typedef enum {
    HNF_EXT_FLAG_INITIALIZED = 0x0001,  /* Block initialized */
    HNF_EXT_FLAG_LOCKED      = 0x0002,  /* Identity locked (don't modify) */
    HNF_EXT_FLAG_COMPRESSED  = 0x0004,  /* Content compressed */
    HNF_EXT_FLAG_ENCRYPTED   = 0x0008   /* Content encrypted (future) */
} hnf_ext_flags_t;

/* ============================================================================
 * MEMORY TYPES
 * ============================================================================ */

typedef enum {
    HNF_MEM_KNOWLEDGE = 0,      /* Facts, skills, understanding */
    HNF_MEM_IDENTITY = 1,       /* Self-related memories */
    HNF_MEM_PROJECT = 2,        /* Ongoing work, goals */
    HNF_MEM_EVENT = 3,          /* Important moments */
    HNF_MEM_RELATIONSHIP = 4    /* User-related memories */
} hnf_memory_type_t;

/* ============================================================================
 * RESULT CODES
 * ============================================================================ */

typedef enum {
    HNF_OK = 0,
    HNF_ERROR,
    HNF_ERROR_NOT_FOUND,
    HNF_ERROR_NO_MEMORY,
    HNF_ERROR_IO,
    HNF_ERROR_CORRUPT,
    HNF_ERROR_LOCKED,
    HNF_ERROR_FULL,
    HNF_ERROR_INVALID,
    HNF_ERROR_CHECKSUM
} hnf_result_t;

/* ============================================================================
 * STRING TYPES (fixed size, packed)
 * ============================================================================ */

/* 64-byte string */
typedef struct {
    uint8_t length;
    char    data[63];
} hnf_string64_t;

/* 512-byte string */
typedef struct {
    uint16_t length;
    char     data[510];
} hnf_string512_t;

/* 1024-byte string */
typedef struct {
    uint16_t length;
    char     data[1022];
} hnf_string1024_t;

/* ============================================================================
 * IDENTITY STRUCTURES
 * ============================================================================ */

/* Personality trait */
typedef struct {
    hnf_string64_t name;        /* e.g., "curioso", "paciente" */
    float          strength;    /* 0.0 - 1.0 */
} hnf_trait_t;

/* Core value */
typedef struct {
    hnf_string64_t  name;           /* e.g., "honestidad" */
    uint8_t         priority;       /* 1 = highest priority */
    uint8_t         reserved[3];
    hnf_string512_t description;    /* Why it's important */
} hnf_value_t;

/* Style profile */
typedef struct {
    float formality;        /* 0.0 casual - 1.0 formal */
    float verbosity;        /* 0.0 concise - 1.0 detailed */
    float technicality;     /* 0.0 simple - 1.0 technical */
    float warmth;           /* 0.0 distant - 1.0 warm */
    float humor;            /* 0.0 serious - 1.0 humorous */
} hnf_style_t;

/* Identity Core - who Helios is */
typedef struct {
    /* Essence (required) */
    hnf_string64_t  name;           /* Name of Helios */
    hnf_string512_t purpose;        /* Why it exists */
    int64_t         creation_date;  /* When it was "born" */
    
    /* Personality */
    uint8_t         trait_count;
    uint8_t         reserved1[7];
    hnf_trait_t     traits[HNF_EXT_MAX_TRAITS];
    
    /* Values */
    uint8_t         value_count;
    uint8_t         reserved2[7];
    hnf_value_t     values[HNF_EXT_MAX_VALUES];
    
    /* Style */
    hnf_style_t     style;
    
    /* History */
    hnf_string1024_t origin_story;   /* How it started (optional) */
} hnf_identity_t;

/* ============================================================================
 * STRONG MEMORY STRUCTURES
 * ============================================================================ */

/* Strong Memory - permanent memory approved by HERA */
typedef struct {
    uint64_t        id;                 /* Unique ID */
    uint8_t         type;               /* hnf_memory_type_t */
    uint8_t         reserved[3];
    int64_t         timestamp;          /* When it happened */
    int64_t         promoted;           /* When it became strong */
    uint32_t        original_access_count;  /* Access count when promoted */
    float           original_relevance;     /* Relevance when promoted */
    hnf_string64_t  concept;            /* Main concept */
    char            summary[HNF_EXT_MAX_MEMORY_TEXT];  /* Memory content */
    uint16_t        summary_length;
    uint16_t        reserved2;
} hnf_strong_memory_t;

/* ============================================================================
 * HNF-EXT HEADER (64 bytes, aligned)
 * ============================================================================ */

typedef struct {
    uint32_t magic;             /* HNF_EXT_MAGIC ("HEXT") */          /* 0-3 */
    uint16_t version;           /* HNF_EXT_VERSION */                 /* 4-5 */
    uint16_t flags;             /* hnf_ext_flags_t */                 /* 6-7 */
    
    uint64_t total_size;        /* Total block size */                /* 8-15 */
    uint32_t identity_offset;   /* Offset to IdentityCore */          /* 16-19 */
    uint32_t identity_size;     /* Size of IdentityCore */            /* 20-23 */
    uint32_t memories_offset;   /* Offset to StrongMemoryArray */     /* 24-27 */
    uint32_t memories_size;     /* Size of StrongMemoryArray */       /* 28-31 */
    uint32_t memories_count;    /* Number of strong memories */       /* 32-35 */
    uint32_t metadata_offset;   /* Offset to ExtMetadata */           /* 36-39 */
    uint32_t metadata_size;     /* Size of ExtMetadata */             /* 40-43 */
    uint32_t reserved1;         /* Padding for 8-byte alignment */    /* 44-47 */
    
    int64_t  created;           /* Creation timestamp */              /* 48-55 */
    int64_t  modified;          /* Last modification timestamp */     /* 56-63 */
} hnf_ext_header_t;

/* Static assert for header size */
_Static_assert(sizeof(hnf_ext_header_t) == 64, "Header must be 64 bytes");

/* ============================================================================
 * METADATA
 * ============================================================================ */

typedef struct {
    uint32_t backups_created;
    int64_t  last_backup;
    int64_t  last_verification;
    uint32_t verification_errors;
    char     last_hera_version[32];
    char     last_model_hash[64];
} hnf_metadata_t;

/* ============================================================================
 * COMPLETE HNF-EXT BLOCK (in-memory representation)
 * ============================================================================ */

typedef struct {
    hnf_ext_header_t    header;
    hnf_identity_t      identity;
    hnf_strong_memory_t memories[HNF_EXT_MAX_MEMORIES];
    uint32_t            memory_count;
    hnf_metadata_t      metadata;
    uint64_t            checksum;       /* CRC64 of content */
    
    /* Runtime state (not persisted) */
    bool                loaded;
    bool                dirty;
    char                filepath[256];
} hnf_ext_block_t;

/* ============================================================================
 * INTEGRITY RESULT
 * ============================================================================ */

typedef struct {
    bool     valid;
    uint32_t errors;
    char     error_message[256];
    uint64_t expected_checksum;
    uint64_t actual_checksum;
} hnf_integrity_result_t;

#endif /* HNF_EXT_TYPES_H */
