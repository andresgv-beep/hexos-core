/*
 * HERA v3.0 - Main Implementation
 * HELIOS Cognitive Ecosystem
 * 
 * "Cuando el contexto se llena, la mente no muere.
 *  La mente persiste en los recuerdos.
 *  Helios nunca olvida lo que importa."
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>
#include <pthread.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

#include "../include/hera.h"

/* Include Memory Core and HNF-EXT if available */
#ifdef MEMORY_CORE_AVAILABLE
#include "../../memory_core/include/memory_core.h"
#endif

#ifdef HNF_EXT_AVAILABLE
#include "../../hnf_ext/include/hnf_ext.h"
#endif

/* ============================================================================
 * INTERNAL STRUCTURES
 * ============================================================================ */

/* Pending proposal */
typedef struct {
    hera_proposal_t proposal;
    int64_t submitted;
    bool evaluated;
} pending_proposal_t;

/* HERA Global Context */
typedef struct {
    /* Configuration */
    hera_config_t config;
    
    /* State */
    hera_state_t state;
    hera_pressure_t pressure;
    bool initialized;
    
    /* Connections */
    bool hexos_connected;
    bool memory_core_connected;
    bool hnf_ext_connected;
    void *hexos_shm;
    
    /* Proposals */
    pending_proposal_t pending[HERA_MAX_PENDING_CANDIDATES];
    uint32_t pending_count;
    uint32_t proposals_today;
    int current_day;
    
    /* Statistics */
    hera_stats_t stats;
    
    /* Current checkpoint data */
    hera_checkpoint_t current_checkpoint;
    
    /* Locks */
    pthread_mutex_t lock;
    
} hera_context_t;

static hera_context_t g_hera = {0};

/* ============================================================================
 * UTILITIES
 * ============================================================================ */

static int64_t get_timestamp(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (int64_t)tv.tv_sec;
}

static int get_current_day(void) {
    time_t now = time(NULL);
    struct tm *tm = localtime(&now);
    return tm->tm_yday;
}

static void reset_daily_counters(void) {
    int today = get_current_day();
    if (g_hera.current_day != today) {
        g_hera.current_day = today;
        g_hera.proposals_today = 0;
        printf("[HERA] New day - counters reset\n");
    }
}

/* ============================================================================
 * LIFECYCLE
 * ============================================================================ */

hera_result_t hera_init(const hera_config_t *config) {
    if (g_hera.initialized) {
        return HERA_OK;
    }
    
    memset(&g_hera, 0, sizeof(g_hera));
    
    /* Apply configuration */
    if (config) {
        g_hera.config = *config;
    } else {
        /* Defaults */
        g_hera.config.ram_active_limit_mb = 200;
        g_hera.config.daily_episodic_limit = 10000;
        g_hera.config.daily_semantic_limit = 5000;
        g_hera.config.max_hnf_ext_size_mb = 5;
        g_hera.config.max_proposals_per_day = HERA_MAX_PROPOSALS_PER_DAY;
        g_hera.config.essential_threshold = 0.85f;
        g_hera.config.auto_consolidate = true;
        g_hera.config.consolidate_hour = 3;
        strncpy(g_hera.config.hnf_ext_path, "./helios.hnf-ext", 
                sizeof(g_hera.config.hnf_ext_path) - 1);
        strncpy(g_hera.config.memory_path, "./memory",
                sizeof(g_hera.config.memory_path) - 1);
    }
    
    pthread_mutex_init(&g_hera.lock, NULL);
    
    g_hera.state = HERA_STATE_IDLE;
    g_hera.pressure = HERA_PRESSURE_LOW;
    g_hera.current_day = get_current_day();
    g_hera.initialized = true;
    
    /* Update stats limits */
    g_hera.stats.ram_limit_mb = g_hera.config.ram_active_limit_mb;
    
    printf("[HERA] v%s initialized\n", HERA_VERSION_STRING);
    printf("[HERA] RAM limit: %lu MB\n", g_hera.config.ram_active_limit_mb);
    printf("[HERA] Max proposals/day: %u\n", g_hera.config.max_proposals_per_day);
    printf("[HERA] Essential threshold: %.2f\n", g_hera.config.essential_threshold);
    
    return HERA_OK;
}

void hera_shutdown(void) {
    if (!g_hera.initialized) return;
    
    printf("[HERA] Shutting down...\n");
    
    /* Final consolidation if needed */
    if (hera_needs_consolidation()) {
        printf("[HERA] Running final consolidation...\n");
        hera_consolidation_result_t result;
        hera_consolidate(&result);
    }
    
    /* Disconnect from subsystems */
    hera_disconnect_hexos();
    
    pthread_mutex_destroy(&g_hera.lock);
    
    memset(&g_hera, 0, sizeof(g_hera));
    
    printf("[HERA] Shutdown complete\n");
}

bool hera_is_initialized(void) {
    return g_hera.initialized;
}

hera_state_t hera_get_state(void) {
    return g_hera.state;
}

/* ============================================================================
 * HEXOS INTERFACE
 * ============================================================================ */

hera_result_t hera_connect_hexos(void) {
    if (!g_hera.initialized) return HERA_ERROR_NOT_INITIALIZED;
    
    /* Try to connect to HEXOS shared memory */
    int shm_fd = shm_open("/hexos_state", O_RDWR, 0666);
    if (shm_fd < 0) {
        printf("[HERA] HEXOS IPC not available (running standalone)\n");
        return HERA_OK;
    }
    
    void *state = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, shm_fd, 0);
    close(shm_fd);
    
    if (state == MAP_FAILED) {
        printf("[HERA] Failed to map HEXOS shared memory\n");
        return HERA_OK;
    }
    
    /* Verify magic */
    uint32_t magic = *(uint32_t *)state;
    if (magic != 0x4845584F) {  /* "HEXO" */
        munmap(state, 4096);
        printf("[HERA] Invalid HEXOS shared memory\n");
        return HERA_OK;
    }
    
    g_hera.hexos_shm = state;
    g_hera.hexos_connected = true;
    
    printf("[HERA] Connected to HEXOS IPC\n");
    
    return HERA_OK;
}

void hera_disconnect_hexos(void) {
    if (g_hera.hexos_shm) {
        munmap(g_hera.hexos_shm, 4096);
        g_hera.hexos_shm = NULL;
        g_hera.hexos_connected = false;
    }
}

hera_result_t hera_handle_hexos_signal(hexos_signal_t signal, 
                                        hera_pressure_t pressure) {
    if (!g_hera.initialized) return HERA_ERROR_NOT_INITIALIZED;
    
    pthread_mutex_lock(&g_hera.lock);
    
    switch (signal) {
        case HEXOS_SIGNAL_CHECKPOINT_REQUEST:
            printf("[HERA] HEXOS requests checkpoint\n");
            g_hera.state = HERA_STATE_CHECKPOINT;
            /* Checkpoint will be prepared by caller via hera_prepare_checkpoint */
            break;
            
        case HEXOS_SIGNAL_MEMORY_PRESSURE:
            printf("[HERA] Memory pressure: %d\n", pressure);
            g_hera.pressure = pressure;
            if (pressure >= HERA_PRESSURE_HIGH) {
                g_hera.state = HERA_STATE_DEGRADED;
            }
            break;
            
        case HEXOS_SIGNAL_SESSION_END:
            printf("[HERA] Session end - consolidating\n");
            g_hera.state = HERA_STATE_CONSOLIDATING;
            pthread_mutex_unlock(&g_hera.lock);
            hera_consolidation_result_t result;
            hera_consolidate(&result);
            return HERA_OK;
            
        case HEXOS_SIGNAL_RESUME:
            printf("[HERA] Resuming normal operation\n");
            g_hera.state = HERA_STATE_IDLE;
            g_hera.pressure = HERA_PRESSURE_LOW;
            break;
            
        default:
            break;
    }
    
    pthread_mutex_unlock(&g_hera.lock);
    return HERA_OK;
}

/* ============================================================================
 * COGNITIVE KERNEL INTERFACE
 * ============================================================================ */

hera_response_t hera_handle_ck_event(ck_event_type_t event, void *data) {
    if (!g_hera.initialized) return HERA_RESPONSE_ERROR;
    
    reset_daily_counters();
    
    switch (event) {
        case CK_EVENT_PROPOSE_CORE_MEMORY:
            if (data) {
                return hera_submit_proposal((hera_proposal_t *)data);
            }
            return HERA_RESPONSE_ERROR;
            
        case CK_EVENT_MEMORY_QUERY:
            /* Handled via hera_query_memories */
            return HERA_RESPONSE_OK;
            
        case CK_EVENT_CONTEXT_UPDATE:
            g_hera.state = HERA_STATE_ACTIVE;
            return HERA_RESPONSE_OK;
            
        case CK_EVENT_TURN_COMPLETE:
            g_hera.state = HERA_STATE_IDLE;
            return HERA_RESPONSE_OK;
            
        case CK_EVENT_LEARNING:
            /* Track learning events */
            return HERA_RESPONSE_OK;
            
        default:
            return HERA_RESPONSE_ERROR;
    }
}

hera_result_t hera_query_memories(const hera_memory_query_t *query,
                                   uint64_t *out_ids,
                                   uint32_t max_ids,
                                   uint32_t *out_count) {
    if (!g_hera.initialized || !query || !out_ids || !out_count) {
        return HERA_ERROR_INVALID;
    }
    
    /* TODO: Interface with Memory Core for actual query */
    /* For now, return empty result */
    *out_count = 0;
    
    return HERA_OK;
}

hera_response_t hera_submit_proposal(const hera_proposal_t *proposal) {
    if (!g_hera.initialized || !proposal) return HERA_RESPONSE_ERROR;
    
    reset_daily_counters();
    
    pthread_mutex_lock(&g_hera.lock);
    
    /* Check daily limit */
    if (g_hera.proposals_today >= g_hera.config.max_proposals_per_day) {
        printf("[HERA] Daily proposal limit reached (%u/%u)\n",
               g_hera.proposals_today, g_hera.config.max_proposals_per_day);
        
        /* Add to pending if space */
        if (g_hera.pending_count < HERA_MAX_PENDING_CANDIDATES) {
            g_hera.pending[g_hera.pending_count].proposal = *proposal;
            g_hera.pending[g_hera.pending_count].submitted = get_timestamp();
            g_hera.pending[g_hera.pending_count].evaluated = false;
            g_hera.pending_count++;
            g_hera.stats.pending_candidates = g_hera.pending_count;
            pthread_mutex_unlock(&g_hera.lock);
            return HERA_RESPONSE_PROPOSAL_PENDING;
        }
        
        pthread_mutex_unlock(&g_hera.lock);
        return HERA_RESPONSE_PROPOSAL_REJECTED;
    }
    
    /* Validate proposal */
    bool accepted;
    char reason[256];
    pthread_mutex_unlock(&g_hera.lock);
    
    hera_result_t res = hera_validate_proposal(proposal, &accepted, reason, sizeof(reason));
    if (res != HERA_OK) {
        return HERA_RESPONSE_ERROR;
    }
    
    pthread_mutex_lock(&g_hera.lock);
    
    if (accepted) {
        g_hera.proposals_today++;
        g_hera.stats.proposals_accepted_total++;
        printf("[HERA] Proposal ACCEPTED: %s (reason: %s)\n", 
               proposal->concept, reason);
        
        pthread_mutex_unlock(&g_hera.lock);
        
        /* Promote to HNF-EXT */
        hera_promote_to_essential(proposal);
        
        return HERA_RESPONSE_PROPOSAL_ACCEPTED;
    } else {
        g_hera.stats.proposals_rejected_total++;
        printf("[HERA] Proposal REJECTED: %s (reason: %s)\n",
               proposal->concept, reason);
        pthread_mutex_unlock(&g_hera.lock);
        return HERA_RESPONSE_PROPOSAL_REJECTED;
    }
}

uint32_t hera_get_pending_proposals(void) {
    return g_hera.pending_count;
}

/* ============================================================================
 * HHMS VALIDATION
 * ============================================================================ */

hera_result_t hera_validate_proposal(const hera_proposal_t *proposal,
                                      bool *out_accepted,
                                      char *out_reason, size_t reason_len) {
    if (!g_hera.initialized || !proposal || !out_accepted) {
        return HERA_ERROR_INVALID;
    }
    
    *out_accepted = false;
    
    /* Criterion 1: Relevance threshold */
    if (proposal->relevance < g_hera.config.essential_threshold) {
        snprintf(out_reason, reason_len, 
                 "Relevance %.2f below threshold %.2f",
                 proposal->relevance, g_hera.config.essential_threshold);
        return HERA_OK;
    }
    
    /* Criterion 2: Identity weight */
    if (proposal->identity_weight < 0.5f) {
        snprintf(out_reason, reason_len,
                 "Identity weight %.2f too low", proposal->identity_weight);
        return HERA_OK;
    }
    
    /* Criterion 3: Frequency check (must have been accessed multiple times) */
    if (proposal->frequency < 3) {
        snprintf(out_reason, reason_len,
                 "Frequency %u too low (min 3)", proposal->frequency);
        return HERA_OK;
    }
    
    /* Criterion 4: Not trivial (summary length) */
    if (strlen(proposal->summary) < 20) {
        snprintf(out_reason, reason_len, "Summary too short (trivial)");
        return HERA_OK;
    }
    
    /* Criterion 5: Category check */
    if (strcmp(proposal->category, "identity") != 0 &&
        strcmp(proposal->category, "knowledge") != 0 &&
        strcmp(proposal->category, "project") != 0 &&
        strcmp(proposal->category, "event") != 0 &&
        strcmp(proposal->category, "relationship") != 0) {
        snprintf(out_reason, reason_len, "Invalid category: %s", proposal->category);
        return HERA_OK;
    }
    
    /* All criteria passed */
    *out_accepted = true;
    snprintf(out_reason, reason_len, 
             "All criteria passed (rel=%.2f, id_w=%.2f, freq=%u)",
             proposal->relevance, proposal->identity_weight, proposal->frequency);
    
    return HERA_OK;
}

/* ============================================================================
 * HNF-EXT INTERFACE
 * ============================================================================ */

hera_result_t hera_connect_hnf_ext(void) {
    if (!g_hera.initialized) return HERA_ERROR_NOT_INITIALIZED;
    
#ifdef HNF_EXT_AVAILABLE
    if (hnf_ext_init() == HNF_OK) {
        /* Try to load existing HNF-EXT */
        if (hnf_ext_load(g_hera.config.hnf_ext_path) == HNF_OK) {
            g_hera.hnf_ext_connected = true;
            g_hera.stats.essential_count = hnf_ext_get_memory_count();
            printf("[HERA] Connected to HNF-EXT: %s\n", g_hera.config.hnf_ext_path);
            return HERA_OK;
        }
        /* Create new if doesn't exist */
        if (hnf_ext_create(g_hera.config.hnf_ext_path, "Helios") == HNF_OK) {
            g_hera.hnf_ext_connected = true;
            printf("[HERA] Created new HNF-EXT: %s\n", g_hera.config.hnf_ext_path);
            return HERA_OK;
        }
    }
#endif
    
    printf("[HERA] HNF-EXT not available (running without identity persistence)\n");
    return HERA_OK;
}

hera_result_t hera_promote_to_essential(const hera_proposal_t *proposal) {
    if (!g_hera.initialized || !proposal) return HERA_ERROR_INVALID;
    
#ifdef HNF_EXT_AVAILABLE
    if (g_hera.hnf_ext_connected) {
        hnf_strong_memory_t memory = {
            .id = proposal->source_id,
            .timestamp = proposal->first_seen,
            .promoted = get_timestamp(),
            .original_access_count = proposal->frequency,
            .original_relevance = proposal->relevance
        };
        
        /* Set type based on category */
        if (strcmp(proposal->category, "identity") == 0) {
            memory.type = HNF_MEM_IDENTITY;
        } else if (strcmp(proposal->category, "knowledge") == 0) {
            memory.type = HNF_MEM_KNOWLEDGE;
        } else if (strcmp(proposal->category, "project") == 0) {
            memory.type = HNF_MEM_PROJECT;
        } else if (strcmp(proposal->category, "event") == 0) {
            memory.type = HNF_MEM_EVENT;
        } else {
            memory.type = HNF_MEM_RELATIONSHIP;
        }
        
        strncpy(memory.summary, proposal->summary, sizeof(memory.summary) - 1);
        memory.summary_length = strlen(memory.summary);
        
        /* TODO: Set concept via helper */
        
        if (hnf_ext_add_memory(&memory) == HNF_OK) {
            g_hera.stats.essential_count++;
            printf("[HERA] Promoted to HNF-EXT: %s\n", proposal->concept);
            return HERA_OK;
        }
    }
#endif
    
    printf("[HERA] Would promote to HNF-EXT (not connected): %s\n", proposal->concept);
    return HERA_OK;
}

uint32_t hera_get_essential_count(void) {
    return g_hera.stats.essential_count;
}

uint32_t hera_get_identity_hash(void) {
#ifdef HNF_EXT_AVAILABLE
    if (g_hera.hnf_ext_connected) {
        return hnf_ext_get_identity_hash();
    }
#endif
    return 0;
}

/* ============================================================================
 * CONSOLIDATION
 * ============================================================================ */

bool hera_needs_consolidation(void) {
    if (!g_hera.initialized) return false;
    
    /* Need consolidation if:
     * - Pending proposals exist
     * - Under memory pressure
     * - Long time since last consolidation
     */
    
    if (g_hera.pending_count > 0) return true;
    if (g_hera.pressure >= HERA_PRESSURE_HIGH) return true;
    
    int64_t now = get_timestamp();
    if (g_hera.stats.last_consolidation > 0 &&
        (now - g_hera.stats.last_consolidation) > 86400) {  /* 24 hours */
        return true;
    }
    
    return false;
}

hera_result_t hera_consolidate(hera_consolidation_result_t *out_result) {
    if (!g_hera.initialized) return HERA_ERROR_NOT_INITIALIZED;
    
    pthread_mutex_lock(&g_hera.lock);
    
    hera_state_t prev_state = g_hera.state;
    g_hera.state = HERA_STATE_CONSOLIDATING;
    
    printf("[HERA] Starting consolidation...\n");
    
    int64_t start = get_timestamp();
    
    if (out_result) {
        memset(out_result, 0, sizeof(hera_consolidation_result_t));
        out_result->timestamp = start;
    }
    
    /* 1. Evaluate pending proposals */
    uint32_t promoted = 0;
    for (uint32_t i = 0; i < g_hera.pending_count; i++) {
        if (!g_hera.pending[i].evaluated) {
            bool accepted;
            char reason[256];
            
            pthread_mutex_unlock(&g_hera.lock);
            hera_validate_proposal(&g_hera.pending[i].proposal, &accepted, 
                                   reason, sizeof(reason));
            pthread_mutex_lock(&g_hera.lock);
            
            g_hera.pending[i].evaluated = true;
            
            if (accepted) {
                pthread_mutex_unlock(&g_hera.lock);
                hera_promote_to_essential(&g_hera.pending[i].proposal);
                pthread_mutex_lock(&g_hera.lock);
                promoted++;
            }
        }
    }
    
    if (out_result) {
        out_result->candidates_evaluated = g_hera.pending_count;
        out_result->candidates_promoted = promoted;
    }
    
    /* 2. Clear evaluated pending */
    g_hera.pending_count = 0;
    g_hera.stats.pending_candidates = 0;
    
    /* 3. Update stats */
    g_hera.stats.consolidations_total++;
    g_hera.stats.last_consolidation = get_timestamp();
    
    if (out_result) {
        out_result->duration_ms = (float)(get_timestamp() - start) * 1000.0f;
    }
    
    g_hera.state = prev_state == HERA_STATE_CONSOLIDATING ? HERA_STATE_IDLE : prev_state;
    
    printf("[HERA] Consolidation complete: %u candidates, %u promoted\n",
           out_result ? out_result->candidates_evaluated : 0,
           promoted);
    
    pthread_mutex_unlock(&g_hera.lock);
    
    return HERA_OK;
}

/* ============================================================================
 * CHECKPOINT
 * ============================================================================ */

hera_result_t hera_prepare_checkpoint(hera_checkpoint_t *out_checkpoint) {
    if (!g_hera.initialized || !out_checkpoint) return HERA_ERROR_INVALID;
    
    pthread_mutex_lock(&g_hera.lock);
    
    g_hera.state = HERA_STATE_CHECKPOINT;
    
    /* Copy current checkpoint data */
    *out_checkpoint = g_hera.current_checkpoint;
    out_checkpoint->timestamp = get_timestamp();
    out_checkpoint->identity_hash = hera_get_identity_hash();
    
    g_hera.stats.checkpoints_total++;
    g_hera.stats.last_checkpoint = out_checkpoint->timestamp;
    
    g_hera.state = HERA_STATE_IDLE;
    
    printf("[HERA] Checkpoint prepared: %u facts, %u tasks, %u projects\n",
           out_checkpoint->stable_fact_count,
           out_checkpoint->open_task_count,
           out_checkpoint->active_project_count);
    
    pthread_mutex_unlock(&g_hera.lock);
    
    return HERA_OK;
}

hera_result_t hera_restore_checkpoint(const hera_checkpoint_t *checkpoint) {
    if (!g_hera.initialized || !checkpoint) return HERA_ERROR_INVALID;
    
    pthread_mutex_lock(&g_hera.lock);
    
    g_hera.state = HERA_STATE_RECOVERING;
    
    g_hera.current_checkpoint = *checkpoint;
    
    printf("[HERA] Restored checkpoint from %ld\n", checkpoint->timestamp);
    
    g_hera.state = HERA_STATE_IDLE;
    
    pthread_mutex_unlock(&g_hera.lock);
    
    return HERA_OK;
}

hera_result_t hera_add_stable_fact(const char *fact) {
    if (!g_hera.initialized || !fact) return HERA_ERROR_INVALID;
    
    pthread_mutex_lock(&g_hera.lock);
    
    if (g_hera.current_checkpoint.stable_fact_count >= HERA_MAX_STABLE_FACTS) {
        pthread_mutex_unlock(&g_hera.lock);
        return HERA_ERROR_LIMIT_EXCEEDED;
    }
    
    uint32_t idx = g_hera.current_checkpoint.stable_fact_count++;
    strncpy(g_hera.current_checkpoint.stable_facts[idx], fact, 255);
    
    pthread_mutex_unlock(&g_hera.lock);
    return HERA_OK;
}

hera_result_t hera_add_open_task(const char *task) {
    if (!g_hera.initialized || !task) return HERA_ERROR_INVALID;
    
    pthread_mutex_lock(&g_hera.lock);
    
    if (g_hera.current_checkpoint.open_task_count >= HERA_MAX_OPEN_TASKS) {
        pthread_mutex_unlock(&g_hera.lock);
        return HERA_ERROR_LIMIT_EXCEEDED;
    }
    
    uint32_t idx = g_hera.current_checkpoint.open_task_count++;
    strncpy(g_hera.current_checkpoint.open_tasks[idx], task, 255);
    
    pthread_mutex_unlock(&g_hera.lock);
    return HERA_OK;
}

hera_result_t hera_set_user_intent(const char *intent) {
    if (!g_hera.initialized || !intent) return HERA_ERROR_INVALID;
    
    pthread_mutex_lock(&g_hera.lock);
    strncpy(g_hera.current_checkpoint.user_intent, intent, 
            HERA_MAX_INTENT_LEN - 1);
    pthread_mutex_unlock(&g_hera.lock);
    return HERA_OK;
}

hera_result_t hera_set_conversation_summary(const char *summary) {
    if (!g_hera.initialized || !summary) return HERA_ERROR_INVALID;
    
    pthread_mutex_lock(&g_hera.lock);
    strncpy(g_hera.current_checkpoint.conversation_summary, summary,
            HERA_MAX_SUMMARY_LEN - 1);
    pthread_mutex_unlock(&g_hera.lock);
    return HERA_OK;
}

/* ============================================================================
 * STATISTICS
 * ============================================================================ */

hera_result_t hera_get_stats(hera_stats_t *out_stats) {
    if (!g_hera.initialized || !out_stats) return HERA_ERROR_INVALID;
    
    pthread_mutex_lock(&g_hera.lock);
    
    g_hera.stats.state = g_hera.state;
    g_hera.stats.pressure = g_hera.pressure;
    g_hera.stats.proposals_today = g_hera.proposals_today;
    
    *out_stats = g_hera.stats;
    
    pthread_mutex_unlock(&g_hera.lock);
    return HERA_OK;
}

hera_pressure_t hera_get_pressure(void) {
    return g_hera.pressure;
}

/* ============================================================================
 * IDENTITY GUARDIAN
 * ============================================================================ */

const char* hera_get_name(void) {
#ifdef HNF_EXT_AVAILABLE
    if (g_hera.hnf_ext_connected) {
        return hnf_ext_get_name();
    }
#endif
    return "Helios";
}

const char* hera_get_purpose(void) {
#ifdef HNF_EXT_AVAILABLE
    if (g_hera.hnf_ext_connected) {
        return hnf_ext_get_purpose();
    }
#endif
    return "Ser un compañero cognitivo que recuerda y aprende.";
}

hera_result_t hera_get_continuity_message(char *out_message, size_t max_len) {
    if (!g_hera.initialized || !out_message) return HERA_ERROR_INVALID;
    
#ifdef HNF_EXT_AVAILABLE
    if (g_hera.hnf_ext_connected) {
        return hnf_ext_get_continuity_message(out_message, max_len) == HNF_OK 
               ? HERA_OK : HERA_ERROR;
    }
#endif
    
    snprintf(out_message, max_len,
             "Soy %s. Listo para comenzar.", hera_get_name());
    return HERA_OK;
}

/* ============================================================================
 * HHMS STATS
 * ============================================================================ */

hera_result_t hera_hhms_get_stats(uint32_t *out_level1_count,
                                   uint32_t *out_level2_count,
                                   uint64_t *out_level3_count) {
    if (!g_hera.initialized) return HERA_ERROR_NOT_INITIALIZED;
    
    if (out_level1_count) *out_level1_count = g_hera.stats.essential_count;
    if (out_level2_count) *out_level2_count = g_hera.stats.active_count;
    if (out_level3_count) *out_level3_count = g_hera.stats.archived_count;
    
    return HERA_OK;
}
