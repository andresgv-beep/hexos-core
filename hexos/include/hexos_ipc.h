/*
 * HEXOS - HELIOS Executive Operating System
 * IPC Bus - Inter-Process Communication
 * 
 * Provides shared memory and message passing between HEXOS and modules
 * (Cognitive Kernel, Memory Core, etc.)
 */

#ifndef HEXOS_IPC_H
#define HEXOS_IPC_H

#include <stdint.h>
#include <stdbool.h>
#include <pthread.h>

/* ============================================================================
 * SHARED MEMORY PATHS
 * ============================================================================ */

#define HEXOS_SHM_STATE     "/hexos_state"      /* Runtime state */
#define HEXOS_SHM_METRICS   "/hexos_metrics"    /* Performance metrics */

/* ============================================================================
 * MODULE IDs
 * ============================================================================ */

typedef enum {
    HEXOS_MODULE_NONE = 0,
    HEXOS_MODULE_HEXOS,           /* HEXOS itself */
    HEXOS_MODULE_COGNITIVE,       /* Cognitive Kernel */
    HEXOS_MODULE_MEMORY,          /* Memory Core */
    HEXOS_MODULE_INFERENCE,       /* Inference Engine */
    HEXOS_MODULE_MAX
} hexos_module_id_t;

/* ============================================================================
 * SHARED STATE STRUCTURE
 * Lives in /dev/shm/hexos_state
 * ============================================================================ */

typedef struct {
    /* Header */
    uint32_t magic;               /* HEXOS_SHM_MAGIC */
    uint32_t version;             /* Structure version */
    uint64_t last_update_ns;      /* Nanosecond timestamp */
    
    /* HEXOS state */
    uint8_t hexos_running;        /* HEXOS is alive */
    uint8_t hexos_state;          /* RUNNING, DEGRADED, etc */
    uint8_t profile;              /* BALANCED, PERFORMANCE, etc */
    uint8_t reserved1;
    
    /* Module presence (bitmask) */
    uint32_t modules_connected;   /* Bit per module */
    
    /* Cognitive Kernel state */
    struct {
        uint8_t  running;         /* Engine is processing */
        uint8_t  state;           /* IDLE, RUNNING, ERROR */
        uint8_t  reserved[2];
        float    tokens_per_sec;  /* Current throughput */
        uint32_t queue_depth;     /* Pending requests */
        uint32_t active_ctx_id;   /* Current context ID */
        uint64_t total_tokens;    /* Lifetime token count */
    } cognitive;
    
    /* Memory Core state */
    struct {
        uint8_t  initialized;
        uint8_t  spillover_active;
        uint8_t  reserved[2];
        uint32_t episodic_count;  /* Episodic memories loaded */
        uint32_t identity_hash;   /* Quick identity check */
        char     continuity_text[256]; /* Current CONTINUITY message */
    } memory;
    
    /* Resource pressure */
    struct {
        uint8_t  vram_pressure;   /* 0-100 */
        uint8_t  ram_pressure;    /* 0-100 */
        uint8_t  thermal_state;   /* 0=OK, 1=WARM, 2=HOT, 3=CRITICAL */
        uint8_t  reserved;
        uint32_t vram_budget_model_mb;
        uint32_t vram_budget_kv_mb;
        uint32_t vram_budget_workspace_mb;
    } resources;
    
    /* Predictive memory state */
    struct {
        uint8_t  armed;           /* Ready to predict */
        uint8_t  active;          /* Currently predicting */
        uint8_t  reserved[2];
        uint32_t predictions_queued;
        float    hit_rate;        /* Cache hit rate 0.0-1.0 */
    } predictive;
    
} hexos_shared_state_t;

#define HEXOS_SHM_MAGIC   0x4845584F  /* "HEXO" */
#define HEXOS_SHM_VERSION 1

/* ============================================================================
 * MESSAGE TYPES
 * ============================================================================ */

typedef enum {
    /* HEXOS -> Modules */
    HEXOS_MSG_SHUTDOWN = 1,       /* Graceful shutdown request */
    HEXOS_MSG_PAUSE,              /* Pause processing */
    HEXOS_MSG_RESUME,             /* Resume processing */
    HEXOS_MSG_PROFILE_CHANGE,     /* Power profile changed */
    HEXOS_MSG_VRAM_PRESSURE,      /* VRAM getting low */
    
    /* Modules -> HEXOS */
    HEXOS_MSG_MODULE_READY,       /* Module initialized */
    HEXOS_MSG_MODULE_ERROR,       /* Module error */
    HEXOS_MSG_METRICS_UPDATE,     /* Metrics batch update */
    
    /* Cognitive Kernel specific */
    HEXOS_MSG_INFERENCE_START,    /* Starting inference */
    HEXOS_MSG_INFERENCE_DONE,     /* Inference complete */
    HEXOS_MSG_CONTEXT_SWITCH,     /* Context changed */
    
} hexos_msg_type_t;

typedef struct {
    hexos_msg_type_t type;
    hexos_module_id_t source;
    hexos_module_id_t target;     /* HEXOS_MODULE_NONE = broadcast */
    uint32_t payload_size;
    uint64_t timestamp_ns;
    uint8_t payload[256];         /* Message-specific data */
} hexos_message_t;

/* ============================================================================
 * IPC CONTEXT
 * ============================================================================ */

typedef struct {
    /* Shared memory */
    int shm_fd;
    hexos_shared_state_t *state;
    
    /* Message queue */
    int msg_queue_id;
    
    /* Local info */
    hexos_module_id_t my_id;
    bool is_owner;                /* Did we create the SHM? */
    
    /* Thread safety */
    pthread_mutex_t lock;
    
} hexos_ipc_ctx_t;

/* ============================================================================
 * API
 * ============================================================================ */

/* Initialize IPC (call from HEXOS - creates shared memory) */
int hexos_ipc_init(hexos_ipc_ctx_t *ctx);

/* Connect to existing IPC (call from modules) */
int hexos_ipc_connect(hexos_ipc_ctx_t *ctx, hexos_module_id_t module_id);

/* Disconnect and cleanup */
void hexos_ipc_shutdown(hexos_ipc_ctx_t *ctx);

/* Update shared state (thread-safe) */
void hexos_ipc_lock(hexos_ipc_ctx_t *ctx);
void hexos_ipc_unlock(hexos_ipc_ctx_t *ctx);

/* Get read-only snapshot of state */
void hexos_ipc_get_state(hexos_ipc_ctx_t *ctx, hexos_shared_state_t *out);

/* Convenience updaters for Cognitive Kernel */
void hexos_ipc_update_cognitive(hexos_ipc_ctx_t *ctx, 
                                 bool running, 
                                 float tokens_per_sec,
                                 uint32_t queue_depth);

/* Convenience updaters for Memory Core */
void hexos_ipc_update_memory(hexos_ipc_ctx_t *ctx,
                              bool spillover_active,
                              const char *continuity_text);

/* Convenience updater for predictive state */
void hexos_ipc_update_predictive(hexos_ipc_ctx_t *ctx,
                                  bool armed,
                                  bool active,
                                  float hit_rate);

/* Send message */
int hexos_ipc_send(hexos_ipc_ctx_t *ctx, const hexos_message_t *msg);

/* Receive message (non-blocking, returns 0 if no message) */
int hexos_ipc_recv(hexos_ipc_ctx_t *ctx, hexos_message_t *msg);

/* Check if module is connected */
bool hexos_ipc_module_connected(hexos_ipc_ctx_t *ctx, hexos_module_id_t module);

#endif /* HEXOS_IPC_H */
