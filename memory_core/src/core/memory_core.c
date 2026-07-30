/*
 * MEMORY CORE v3.0 - Main Implementation
 * HELIOS Cognitive Ecosystem
 * 
 * "Los recuerdos viven aquí. Pero la memoria vive en HERA."
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <dirent.h>
#include <errno.h>
#include <pthread.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>

#include "../include/memory_core.h"

/* Try to include HEXOS IPC if available */
#ifdef HEXOS_IPC_AVAILABLE
#include "../../hexos/include/hexos_ipc.h"
#endif

/* ============================================================================
 * INTERNAL STRUCTURES
 * ============================================================================ */

/* Episodic store - simple array-based for now */
typedef struct {
    mc_episodic_event_t *events;
    uint32_t count;
    uint32_t capacity;
    pthread_mutex_t lock;
} episodic_store_t;

/* Semantic store */
typedef struct {
    mc_concept_t *concepts;
    uint32_t count;
    uint32_t capacity;
    
    mc_relation_t *relations;
    uint32_t relation_count;
    uint32_t relation_capacity;
    
    pthread_mutex_t lock;
} semantic_store_t;

/* Embedding store */
typedef struct {
    mc_embedding_t *embeddings;
    uint32_t count;
    uint32_t capacity;
    pthread_mutex_t lock;
} embedding_store_t;

/* Memory index */
typedef struct {
    mc_item_t *items;
    uint64_t count;
    uint64_t capacity;
    pthread_mutex_t lock;
} memory_index_t;

/* Global Memory Core context */
typedef struct {
    /* Configuration */
    mc_config_t config;
    
    /* Stores */
    episodic_store_t episodic;
    semantic_store_t semantic;
    embedding_store_t embeddings;
    memory_index_t index;
    
    /* Statistics */
    mc_stats_t stats;
    
    /* State */
    bool initialized;
    bool hexos_connected;
    int64_t start_time;
    
    /* HEXOS IPC (optional) */
    void *hexos_ipc_ctx;
    
} mc_context_t;

static mc_context_t g_ctx = {0};

/* ============================================================================
 * TIME UTILITIES
 * ============================================================================ */

int64_t mc_timestamp(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (int64_t)tv.tv_sec;
}

static uint64_t mc_timestamp_ms(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (uint64_t)tv.tv_sec * 1000 + tv.tv_usec / 1000;
}

void mc_format_timestamp(int64_t ts, char *buf, size_t len) {
    time_t t = (time_t)ts;
    struct tm *tm_info = localtime(&t);
    strftime(buf, len, "%Y-%m-%d %H:%M:%S", tm_info);
}

/* ============================================================================
 * HASH UTILITIES
 * ============================================================================ */

/* FNV-1a 64-bit hash */
uint64_t mc_generate_id(const void *content, size_t size) {
    const uint8_t *data = (const uint8_t *)content;
    uint64_t hash = 14695981039346656037ULL;
    
    for (size_t i = 0; i < size; i++) {
        hash ^= data[i];
        hash *= 1099511628211ULL;
    }
    
    /* Mix in timestamp for uniqueness */
    hash ^= mc_timestamp_ms();
    hash *= 1099511628211ULL;
    
    return hash;
}

/* ============================================================================
 * DIRECTORY UTILITIES
 * ============================================================================ */

static mc_result_t ensure_directory(const char *path) {
    struct stat st;
    
    if (stat(path, &st) == 0) {
        if (S_ISDIR(st.st_mode)) return MC_OK;
        return MC_ERROR_IO;
    }
    
    /* Create directory recursively */
    char tmp[512];
    snprintf(tmp, sizeof(tmp), "%s", path);
    
    for (char *p = tmp + 1; *p; p++) {
        if (*p == '/') {
            *p = '\0';
            mkdir(tmp, 0755);
            *p = '/';
        }
    }
    
    if (mkdir(tmp, 0755) != 0 && errno != EEXIST) {
        return MC_ERROR_IO;
    }
    
    return MC_OK;
}

/* ============================================================================
 * LIFECYCLE
 * ============================================================================ */

mc_result_t mc_init(const mc_config_t *config) {
    if (g_ctx.initialized) {
        return MC_OK;  /* Already initialized */
    }
    
    memset(&g_ctx, 0, sizeof(g_ctx));
    
    /* Apply configuration */
    if (config) {
        g_ctx.config = *config;
    } else {
        /* Defaults */
        strncpy(g_ctx.config.base_path, ".", sizeof(g_ctx.config.base_path) - 1);
        strncpy(g_ctx.config.memory_path, "./memory", sizeof(g_ctx.config.memory_path) - 1);
        g_ctx.config.ram_active_limit_mb = 200;
        g_ctx.config.daily_episodic_limit = 10000;
        g_ctx.config.daily_semantic_limit = 5000;
        g_ctx.config.max_query_results = MC_MAX_QUERY_RESULTS;
        g_ctx.config.embedding_dimension = MC_DEFAULT_EMBEDDING_DIM;
        g_ctx.config.auto_archive = true;
        g_ctx.config.enable_embeddings = false;  /* Disabled by default */
        g_ctx.config.archive_hour = 3;  /* 3 AM */
    }
    
    /* Ensure directories exist */
    mc_result_t res = ensure_directory(g_ctx.config.memory_path);
    if (res != MC_OK) {
        fprintf(stderr, "[MC] Failed to create memory directory: %s\n", 
                g_ctx.config.memory_path);
        return res;
    }
    
    /* Initialize episodic store */
    g_ctx.episodic.capacity = 1000;
    g_ctx.episodic.events = calloc(g_ctx.episodic.capacity, sizeof(mc_episodic_event_t));
    if (!g_ctx.episodic.events) return MC_ERROR_NO_MEMORY;
    pthread_mutex_init(&g_ctx.episodic.lock, NULL);
    
    /* Initialize semantic store */
    g_ctx.semantic.capacity = 500;
    g_ctx.semantic.concepts = calloc(g_ctx.semantic.capacity, sizeof(mc_concept_t));
    if (!g_ctx.semantic.concepts) return MC_ERROR_NO_MEMORY;
    
    g_ctx.semantic.relation_capacity = 1000;
    g_ctx.semantic.relations = calloc(g_ctx.semantic.relation_capacity, sizeof(mc_relation_t));
    if (!g_ctx.semantic.relations) return MC_ERROR_NO_MEMORY;
    pthread_mutex_init(&g_ctx.semantic.lock, NULL);
    
    /* Initialize embedding store */
    g_ctx.embeddings.capacity = 500;
    g_ctx.embeddings.embeddings = calloc(g_ctx.embeddings.capacity, sizeof(mc_embedding_t));
    if (!g_ctx.embeddings.embeddings) return MC_ERROR_NO_MEMORY;
    pthread_mutex_init(&g_ctx.embeddings.lock, NULL);
    
    /* Initialize index */
    g_ctx.index.capacity = 5000;
    g_ctx.index.items = calloc(g_ctx.index.capacity, sizeof(mc_item_t));
    if (!g_ctx.index.items) return MC_ERROR_NO_MEMORY;
    pthread_mutex_init(&g_ctx.index.lock, NULL);
    
    /* Initialize stats */
    g_ctx.stats.active_limit_mb = g_ctx.config.ram_active_limit_mb;
    
    g_ctx.start_time = mc_timestamp();
    g_ctx.initialized = true;
    
    printf("[MC] Memory Core v%s initialized\n", MC_VERSION_STRING);
    printf("[MC] Base path: %s\n", g_ctx.config.base_path);
    printf("[MC] Memory path: %s\n", g_ctx.config.memory_path);
    printf("[MC] RAM limit: %lu MB\n", g_ctx.config.ram_active_limit_mb);
    
    return MC_OK;
}

void mc_shutdown(void) {
    if (!g_ctx.initialized) return;
    
    printf("[MC] Shutting down Memory Core...\n");
    
    /* Archive if needed */
    if (g_ctx.config.auto_archive && g_ctx.episodic.count > 0) {
        mc_archive_day();
    }
    
    /* Free episodic store */
    pthread_mutex_destroy(&g_ctx.episodic.lock);
    free(g_ctx.episodic.events);
    
    /* Free semantic store */
    pthread_mutex_destroy(&g_ctx.semantic.lock);
    free(g_ctx.semantic.concepts);
    free(g_ctx.semantic.relations);
    
    /* Free embedding store (including vectors) */
    pthread_mutex_destroy(&g_ctx.embeddings.lock);
    for (uint32_t i = 0; i < g_ctx.embeddings.count; i++) {
        free(g_ctx.embeddings.embeddings[i].vector);
    }
    free(g_ctx.embeddings.embeddings);
    
    /* Free index */
    pthread_mutex_destroy(&g_ctx.index.lock);
    free(g_ctx.index.items);
    
    memset(&g_ctx, 0, sizeof(g_ctx));
    
    printf("[MC] Memory Core shutdown complete\n");
}

bool mc_is_initialized(void) {
    return g_ctx.initialized;
}

/* ============================================================================
 * HEXOS IPC CONNECTION
 * ============================================================================ */

mc_result_t mc_connect_hexos(void) {
    if (!g_ctx.initialized) return MC_ERROR;
    
    /* Try to connect to HEXOS shared memory */
    int shm_fd = shm_open("/hexos_state", O_RDWR, 0666);
    if (shm_fd < 0) {
        printf("[MC] HEXOS IPC not available (running standalone)\n");
        return MC_OK;  /* Not an error - can run standalone */
    }
    
    /* Map shared memory */
    void *state = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, shm_fd, 0);
    close(shm_fd);
    
    if (state == MAP_FAILED) {
        printf("[MC] Failed to map HEXOS shared memory\n");
        return MC_OK;
    }
    
    /* Verify magic */
    uint32_t magic = *(uint32_t *)state;
    if (magic != 0x4845584F) {  /* "HEXO" */
        munmap(state, 4096);
        printf("[MC] Invalid HEXOS shared memory\n");
        return MC_OK;
    }
    
    g_ctx.hexos_ipc_ctx = state;
    g_ctx.hexos_connected = true;
    
    /* Update our state in HEXOS shared memory */
    /* Memory Core state is at offset for memory struct */
    /* This matches hexos_shared_state_t.memory */
    
    printf("[MC] Connected to HEXOS IPC\n");
    
    return MC_OK;
}

void mc_disconnect_hexos(void) {
    if (g_ctx.hexos_ipc_ctx) {
        munmap(g_ctx.hexos_ipc_ctx, 4096);
        g_ctx.hexos_ipc_ctx = NULL;
        g_ctx.hexos_connected = false;
        printf("[MC] Disconnected from HEXOS IPC\n");
    }
}

/* ============================================================================
 * INDEX OPERATIONS
 * ============================================================================ */

static mc_result_t index_add(mc_item_t *item) {
    pthread_mutex_lock(&g_ctx.index.lock);
    
    /* Check capacity */
    if (g_ctx.index.count >= g_ctx.index.capacity) {
        uint64_t new_cap = g_ctx.index.capacity * 2;
        mc_item_t *new_items = realloc(g_ctx.index.items, new_cap * sizeof(mc_item_t));
        if (!new_items) {
            pthread_mutex_unlock(&g_ctx.index.lock);
            return MC_ERROR_NO_MEMORY;
        }
        g_ctx.index.items = new_items;
        g_ctx.index.capacity = new_cap;
    }
    
    g_ctx.index.items[g_ctx.index.count++] = *item;
    g_ctx.stats.index_items = g_ctx.index.count;
    
    pthread_mutex_unlock(&g_ctx.index.lock);
    return MC_OK;
}

static mc_item_t* index_find(uint64_t id) {
    for (uint64_t i = 0; i < g_ctx.index.count; i++) {
        if (g_ctx.index.items[i].id == id) {
            return &g_ctx.index.items[i];
        }
    }
    return NULL;
}

mc_result_t mc_index_get(uint64_t id, mc_item_t *out_item) {
    if (!out_item) return MC_ERROR_INVALID;
    
    pthread_mutex_lock(&g_ctx.index.lock);
    mc_item_t *item = index_find(id);
    if (!item) {
        pthread_mutex_unlock(&g_ctx.index.lock);
        return MC_ERROR_NOT_FOUND;
    }
    *out_item = *item;
    pthread_mutex_unlock(&g_ctx.index.lock);
    return MC_OK;
}

mc_result_t mc_index_touch(uint64_t id) {
    pthread_mutex_lock(&g_ctx.index.lock);
    mc_item_t *item = index_find(id);
    if (!item) {
        pthread_mutex_unlock(&g_ctx.index.lock);
        return MC_ERROR_NOT_FOUND;
    }
    item->last_access = mc_timestamp();
    item->access_count++;
    pthread_mutex_unlock(&g_ctx.index.lock);
    return MC_OK;
}

mc_result_t mc_index_mark_candidate(uint64_t id) {
    pthread_mutex_lock(&g_ctx.index.lock);
    mc_item_t *item = index_find(id);
    if (!item) {
        pthread_mutex_unlock(&g_ctx.index.lock);
        return MC_ERROR_NOT_FOUND;
    }
    item->flags |= MC_FLAG_CANDIDATE;
    g_ctx.stats.candidates_pending++;
    pthread_mutex_unlock(&g_ctx.index.lock);
    return MC_OK;
}

mc_result_t mc_get_candidates(mc_item_t *out_items, uint32_t max_items, uint32_t *out_count) {
    if (!out_items || !out_count) return MC_ERROR_INVALID;
    
    pthread_mutex_lock(&g_ctx.index.lock);
    
    *out_count = 0;
    for (uint64_t i = 0; i < g_ctx.index.count && *out_count < max_items; i++) {
        if (g_ctx.index.items[i].flags & MC_FLAG_CANDIDATE) {
            out_items[(*out_count)++] = g_ctx.index.items[i];
        }
    }
    
    pthread_mutex_unlock(&g_ctx.index.lock);
    return MC_OK;
}

/* ============================================================================
 * EPISODIC STORE
 * ============================================================================ */

mc_result_t mc_store_episodic(const mc_episodic_event_t *event, uint64_t *out_id) {
    if (!g_ctx.initialized || !event) return MC_ERROR;
    
    pthread_mutex_lock(&g_ctx.episodic.lock);
    
    /* Check capacity */
    if (g_ctx.episodic.count >= g_ctx.episodic.capacity) {
        uint32_t new_cap = g_ctx.episodic.capacity * 2;
        mc_episodic_event_t *new_events = realloc(g_ctx.episodic.events, 
                                                   new_cap * sizeof(mc_episodic_event_t));
        if (!new_events) {
            pthread_mutex_unlock(&g_ctx.episodic.lock);
            return MC_ERROR_NO_MEMORY;
        }
        g_ctx.episodic.events = new_events;
        g_ctx.episodic.capacity = new_cap;
    }
    
    /* Copy event */
    mc_episodic_event_t *stored = &g_ctx.episodic.events[g_ctx.episodic.count];
    *stored = *event;
    
    /* Generate ID if not set */
    if (stored->id == 0) {
        stored->id = mc_generate_id(event->text, strlen(event->text));
    }
    
    /* Set timestamp if not set */
    if (stored->timestamp == 0) {
        stored->timestamp = mc_timestamp();
    }
    
    if (out_id) *out_id = stored->id;
    
    g_ctx.episodic.count++;
    g_ctx.stats.active_items++;
    
    pthread_mutex_unlock(&g_ctx.episodic.lock);
    
    /* Add to index */
    mc_item_t item = {
        .id = stored->id,
        .type = MC_TYPE_EPISODIC,
        .timestamp = stored->timestamp,
        .last_access = stored->timestamp,
        .access_count = 0,
        .relevance = stored->relevance,
        .content_hash = mc_generate_id(stored->text, strlen(stored->text)),
        .embedding_id = 0,
        .flags = MC_FLAG_ACTIVE
    };
    
    return index_add(&item);
}

mc_result_t mc_get_episodic(uint64_t id, mc_episodic_event_t *out_event) {
    if (!g_ctx.initialized || !out_event) return MC_ERROR;
    
    pthread_mutex_lock(&g_ctx.episodic.lock);
    
    for (uint32_t i = 0; i < g_ctx.episodic.count; i++) {
        if (g_ctx.episodic.events[i].id == id) {
            *out_event = g_ctx.episodic.events[i];
            pthread_mutex_unlock(&g_ctx.episodic.lock);
            mc_index_touch(id);
            return MC_OK;
        }
    }
    
    pthread_mutex_unlock(&g_ctx.episodic.lock);
    return MC_ERROR_NOT_FOUND;
}

mc_result_t mc_get_recent_episodic(uint32_t count, 
                                    mc_episodic_event_t *out_events, 
                                    uint32_t *out_count) {
    if (!g_ctx.initialized || !out_events || !out_count) return MC_ERROR;
    
    pthread_mutex_lock(&g_ctx.episodic.lock);
    
    uint32_t start = 0;
    if (g_ctx.episodic.count > count) {
        start = g_ctx.episodic.count - count;
    }
    
    *out_count = 0;
    for (uint32_t i = start; i < g_ctx.episodic.count; i++) {
        out_events[(*out_count)++] = g_ctx.episodic.events[i];
    }
    
    pthread_mutex_unlock(&g_ctx.episodic.lock);
    return MC_OK;
}

/* ============================================================================
 * SEMANTIC STORE
 * ============================================================================ */

mc_result_t mc_store_concept(const mc_concept_t *concept, uint64_t *out_id) {
    if (!g_ctx.initialized || !concept) return MC_ERROR;
    
    pthread_mutex_lock(&g_ctx.semantic.lock);
    
    /* Check if concept already exists (by name) */
    for (uint32_t i = 0; i < g_ctx.semantic.count; i++) {
        if (strcmp(g_ctx.semantic.concepts[i].name, concept->name) == 0) {
            /* Update existing */
            g_ctx.semantic.concepts[i].last_seen = mc_timestamp();
            g_ctx.semantic.concepts[i].frequency++;
            if (concept->importance > g_ctx.semantic.concepts[i].importance) {
                g_ctx.semantic.concepts[i].importance = concept->importance;
            }
            if (out_id) *out_id = g_ctx.semantic.concepts[i].id;
            pthread_mutex_unlock(&g_ctx.semantic.lock);
            return MC_OK;
        }
    }
    
    /* Check capacity */
    if (g_ctx.semantic.count >= g_ctx.semantic.capacity) {
        uint32_t new_cap = g_ctx.semantic.capacity * 2;
        mc_concept_t *new_concepts = realloc(g_ctx.semantic.concepts, 
                                              new_cap * sizeof(mc_concept_t));
        if (!new_concepts) {
            pthread_mutex_unlock(&g_ctx.semantic.lock);
            return MC_ERROR_NO_MEMORY;
        }
        g_ctx.semantic.concepts = new_concepts;
        g_ctx.semantic.capacity = new_cap;
    }
    
    /* Add new concept */
    mc_concept_t *stored = &g_ctx.semantic.concepts[g_ctx.semantic.count];
    *stored = *concept;
    
    if (stored->id == 0) {
        stored->id = mc_generate_id(concept->name, strlen(concept->name));
    }
    if (stored->first_seen == 0) {
        stored->first_seen = mc_timestamp();
    }
    stored->last_seen = stored->first_seen;
    stored->frequency = 1;
    
    if (out_id) *out_id = stored->id;
    
    g_ctx.semantic.count++;
    
    pthread_mutex_unlock(&g_ctx.semantic.lock);
    
    /* Add to index */
    mc_item_t item = {
        .id = stored->id,
        .type = MC_TYPE_SEMANTIC,
        .timestamp = stored->first_seen,
        .last_access = stored->last_seen,
        .access_count = 1,
        .relevance = stored->importance,
        .content_hash = mc_generate_id(stored->name, strlen(stored->name)),
        .embedding_id = 0,
        .flags = MC_FLAG_ACTIVE
    };
    
    return index_add(&item);
}

mc_result_t mc_get_concept(uint64_t id, mc_concept_t *out_concept) {
    if (!g_ctx.initialized || !out_concept) return MC_ERROR;
    
    pthread_mutex_lock(&g_ctx.semantic.lock);
    
    for (uint32_t i = 0; i < g_ctx.semantic.count; i++) {
        if (g_ctx.semantic.concepts[i].id == id) {
            *out_concept = g_ctx.semantic.concepts[i];
            pthread_mutex_unlock(&g_ctx.semantic.lock);
            mc_index_touch(id);
            return MC_OK;
        }
    }
    
    pthread_mutex_unlock(&g_ctx.semantic.lock);
    return MC_ERROR_NOT_FOUND;
}

mc_result_t mc_find_concept(const char *name, mc_concept_t *out_concept) {
    if (!g_ctx.initialized || !name || !out_concept) return MC_ERROR;
    
    pthread_mutex_lock(&g_ctx.semantic.lock);
    
    for (uint32_t i = 0; i < g_ctx.semantic.count; i++) {
        if (strcmp(g_ctx.semantic.concepts[i].name, name) == 0) {
            *out_concept = g_ctx.semantic.concepts[i];
            pthread_mutex_unlock(&g_ctx.semantic.lock);
            mc_index_touch(g_ctx.semantic.concepts[i].id);
            return MC_OK;
        }
    }
    
    pthread_mutex_unlock(&g_ctx.semantic.lock);
    return MC_ERROR_NOT_FOUND;
}

mc_result_t mc_store_relation(const mc_relation_t *relation) {
    if (!g_ctx.initialized || !relation) return MC_ERROR;
    
    pthread_mutex_lock(&g_ctx.semantic.lock);
    
    /* Check capacity */
    if (g_ctx.semantic.relation_count >= g_ctx.semantic.relation_capacity) {
        uint32_t new_cap = g_ctx.semantic.relation_capacity * 2;
        mc_relation_t *new_rels = realloc(g_ctx.semantic.relations, 
                                           new_cap * sizeof(mc_relation_t));
        if (!new_rels) {
            pthread_mutex_unlock(&g_ctx.semantic.lock);
            return MC_ERROR_NO_MEMORY;
        }
        g_ctx.semantic.relations = new_rels;
        g_ctx.semantic.relation_capacity = new_cap;
    }
    
    g_ctx.semantic.relations[g_ctx.semantic.relation_count++] = *relation;
    
    pthread_mutex_unlock(&g_ctx.semantic.lock);
    return MC_OK;
}

mc_result_t mc_get_relations(uint64_t concept_id,
                              mc_relation_t *out_relations,
                              uint32_t max_relations,
                              uint32_t *out_count) {
    if (!g_ctx.initialized || !out_relations || !out_count) return MC_ERROR;
    
    pthread_mutex_lock(&g_ctx.semantic.lock);
    
    *out_count = 0;
    for (uint32_t i = 0; i < g_ctx.semantic.relation_count && *out_count < max_relations; i++) {
        if (g_ctx.semantic.relations[i].source_id == concept_id ||
            g_ctx.semantic.relations[i].target_id == concept_id) {
            out_relations[(*out_count)++] = g_ctx.semantic.relations[i];
        }
    }
    
    pthread_mutex_unlock(&g_ctx.semantic.lock);
    return MC_OK;
}

/* ============================================================================
 * STATISTICS AND MONITORING
 * ============================================================================ */

mc_result_t mc_get_stats(mc_stats_t *out_stats) {
    if (!g_ctx.initialized || !out_stats) return MC_ERROR;
    
    /* Update stats */
    g_ctx.stats.active_items = g_ctx.episodic.count + g_ctx.semantic.count;
    g_ctx.stats.index_items = g_ctx.index.count;
    
    /* Estimate size */
    g_ctx.stats.active_size_mb = 
        (g_ctx.episodic.count * sizeof(mc_episodic_event_t) +
         g_ctx.semantic.count * sizeof(mc_concept_t) +
         g_ctx.index.count * sizeof(mc_item_t)) / (1024 * 1024);
    
    /* Calculate pressure */
    if (g_ctx.stats.active_limit_mb > 0) {
        float usage = (float)g_ctx.stats.active_size_mb / g_ctx.stats.active_limit_mb;
        if (usage > 0.9f) g_ctx.stats.pressure_level = MC_PRESSURE_CRITICAL;
        else if (usage > 0.75f) g_ctx.stats.pressure_level = MC_PRESSURE_HIGH;
        else if (usage > 0.5f) g_ctx.stats.pressure_level = MC_PRESSURE_MEDIUM;
        else g_ctx.stats.pressure_level = MC_PRESSURE_LOW;
    }
    
    *out_stats = g_ctx.stats;
    return MC_OK;
}

mc_pressure_t mc_get_pressure(void) {
    mc_stats_t stats;
    mc_get_stats(&stats);
    return stats.pressure_level;
}

/* ============================================================================
 * ARCHIVAL (simplified for now)
 * ============================================================================ */

mc_result_t mc_archive_day(void) {
    if (!g_ctx.initialized) return MC_ERROR;
    
    /* Get current date */
    time_t now = time(NULL);
    struct tm *tm_info = localtime(&now);
    
    char path[512];
    snprintf(path, sizeof(path), "%s/%04d/%02d/%02d",
             g_ctx.config.memory_path,
             tm_info->tm_year + 1900,
             tm_info->tm_mon + 1,
             tm_info->tm_mday);
    
    mc_result_t res = ensure_directory(path);
    if (res != MC_OK) return res;
    
    /* Write episodic events to JSON */
    char filepath[576];
    snprintf(filepath, sizeof(filepath), "%s/episodic.json", path);
    
    FILE *f = fopen(filepath, "w");
    if (!f) return MC_ERROR_IO;
    
    fprintf(f, "{\n");
    fprintf(f, "  \"version\": \"%s\",\n", MC_VERSION_STRING);
    fprintf(f, "  \"date\": \"%04d-%02d-%02d\",\n",
            tm_info->tm_year + 1900, tm_info->tm_mon + 1, tm_info->tm_mday);
    fprintf(f, "  \"event_count\": %u,\n", g_ctx.episodic.count);
    fprintf(f, "  \"events\": [\n");
    
    pthread_mutex_lock(&g_ctx.episodic.lock);
    for (uint32_t i = 0; i < g_ctx.episodic.count; i++) {
        mc_episodic_event_t *e = &g_ctx.episodic.events[i];
        fprintf(f, "    {\n");
        fprintf(f, "      \"id\": %lu,\n", e->id);
        fprintf(f, "      \"timestamp\": %ld,\n", e->timestamp);
        fprintf(f, "      \"type\": \"%s\",\n", e->type);
        fprintf(f, "      \"text\": \"%s\",\n", e->text);  /* TODO: escape JSON */
        fprintf(f, "      \"relevance\": %.3f\n", e->relevance);
        fprintf(f, "    }%s\n", i < g_ctx.episodic.count - 1 ? "," : "");
    }
    pthread_mutex_unlock(&g_ctx.episodic.lock);
    
    fprintf(f, "  ]\n");
    fprintf(f, "}\n");
    fclose(f);
    
    g_ctx.stats.last_archive = mc_timestamp();
    g_ctx.stats.archived_days++;
    
    printf("[MC] Archived %u events to %s\n", g_ctx.episodic.count, filepath);
    
    return MC_OK;
}

/* ============================================================================
 * CHECKPOINT (for HEXOS continuity)
 * ============================================================================ */

mc_result_t mc_prepare_checkpoint(mc_checkpoint_t *out_checkpoint) {
    if (!g_ctx.initialized || !out_checkpoint) return MC_ERROR;
    
    memset(out_checkpoint, 0, sizeof(mc_checkpoint_t));
    out_checkpoint->timestamp = mc_timestamp();
    
    /* Collect hot items (recently accessed) */
    pthread_mutex_lock(&g_ctx.index.lock);
    
    int64_t now = mc_timestamp();
    int64_t hot_threshold = now - 3600;  /* Last hour */
    
    /* Count hot items first */
    uint64_t hot_count = 0;
    for (uint64_t i = 0; i < g_ctx.index.count; i++) {
        if (g_ctx.index.items[i].last_access >= hot_threshold) {
            hot_count++;
        }
    }
    
    if (hot_count > 0) {
        out_checkpoint->hot_item_ids = malloc(hot_count * sizeof(uint64_t));
        if (out_checkpoint->hot_item_ids) {
            uint64_t idx = 0;
            for (uint64_t i = 0; i < g_ctx.index.count && idx < hot_count; i++) {
                if (g_ctx.index.items[i].last_access >= hot_threshold) {
                    out_checkpoint->hot_item_ids[idx++] = g_ctx.index.items[i].id;
                }
            }
            out_checkpoint->hot_item_count = hot_count;
        }
    }
    
    /* Collect pending candidates */
    uint32_t cand_count = 0;
    for (uint64_t i = 0; i < g_ctx.index.count; i++) {
        if (g_ctx.index.items[i].flags & MC_FLAG_CANDIDATE) {
            cand_count++;
        }
    }
    
    if (cand_count > 0) {
        out_checkpoint->pending_candidates = malloc(cand_count * sizeof(uint64_t));
        if (out_checkpoint->pending_candidates) {
            uint32_t idx = 0;
            for (uint64_t i = 0; i < g_ctx.index.count && idx < cand_count; i++) {
                if (g_ctx.index.items[i].flags & MC_FLAG_CANDIDATE) {
                    out_checkpoint->pending_candidates[idx++] = g_ctx.index.items[i].id;
                }
            }
            out_checkpoint->pending_candidate_count = cand_count;
        }
    }
    
    pthread_mutex_unlock(&g_ctx.index.lock);
    
    /* Copy stats */
    mc_get_stats(&out_checkpoint->stats);
    
    return MC_OK;
}

void mc_free_checkpoint(mc_checkpoint_t *checkpoint) {
    if (!checkpoint) return;
    free(checkpoint->hot_item_ids);
    free(checkpoint->pending_candidates);
    memset(checkpoint, 0, sizeof(mc_checkpoint_t));
}

/* ============================================================================
 * QUERY ENGINE (simplified text search)
 * ============================================================================ */

mc_result_t mc_query(const mc_query_t *query, mc_query_result_t *result) {
    if (!g_ctx.initialized || !query || !result) return MC_ERROR;
    
    uint64_t start_ms = mc_timestamp_ms();
    
    result->items = calloc(query->max_results, sizeof(mc_item_t));
    if (!result->items) return MC_ERROR_NO_MEMORY;
    result->count = 0;
    
    pthread_mutex_lock(&g_ctx.index.lock);
    
    for (uint64_t i = 0; i < g_ctx.index.count && result->count < query->max_results; i++) {
        mc_item_t *item = &g_ctx.index.items[i];
        
        /* Apply filters */
        if (query->type_filter >= 0 && item->type != (uint8_t)query->type_filter) continue;
        if (query->min_relevance > 0 && item->relevance < query->min_relevance) continue;
        if (query->time_start > 0 && item->timestamp < query->time_start) continue;
        if (query->time_end > 0 && item->timestamp > query->time_end) continue;
        
        /* Text search in episodic events */
        if (query->text[0] != '\0' && item->type == MC_TYPE_EPISODIC) {
            bool found = false;
            pthread_mutex_lock(&g_ctx.episodic.lock);
            for (uint32_t j = 0; j < g_ctx.episodic.count; j++) {
                if (g_ctx.episodic.events[j].id == item->id) {
                    if (strstr(g_ctx.episodic.events[j].text, query->text)) {
                        found = true;
                    }
                    break;
                }
            }
            pthread_mutex_unlock(&g_ctx.episodic.lock);
            if (!found) continue;
        }
        
        result->items[result->count++] = *item;
    }
    
    pthread_mutex_unlock(&g_ctx.index.lock);
    
    result->query_time_ms = (float)(mc_timestamp_ms() - start_ms);
    g_ctx.stats.avg_query_ms = (g_ctx.stats.avg_query_ms + result->query_time_ms) / 2;
    
    return MC_OK;
}

void mc_free_query_result(mc_query_result_t *result) {
    if (!result) return;
    free(result->items);
    memset(result, 0, sizeof(mc_query_result_t));
}

/* ============================================================================
 * HNF-EXT CANDIDATE PREPARATION
 * ============================================================================ */

mc_result_t mc_prepare_proposal(uint64_t item_id, mc_core_proposal_t *out_proposal) {
    if (!g_ctx.initialized || !out_proposal) return MC_ERROR;
    
    memset(out_proposal, 0, sizeof(mc_core_proposal_t));
    out_proposal->source_id = item_id;
    
    /* Find item in index */
    mc_item_t item;
    mc_result_t res = mc_index_get(item_id, &item);
    if (res != MC_OK) return res;
    
    out_proposal->relevance_absolute = item.relevance;
    out_proposal->frequency = item.access_count;
    out_proposal->first_seen = item.timestamp;
    
    /* Get content based on type */
    if (item.type == MC_TYPE_EPISODIC) {
        mc_episodic_event_t event;
        res = mc_get_episodic(item_id, &event);
        if (res == MC_OK) {
            snprintf(out_proposal->summary, sizeof(out_proposal->summary),
                     "%.500s", event.text);
            strncpy(out_proposal->category, "event", sizeof(out_proposal->category) - 1);
        }
    } else if (item.type == MC_TYPE_SEMANTIC) {
        mc_concept_t concept;
        res = mc_get_concept(item_id, &concept);
        if (res == MC_OK) {
            snprintf(out_proposal->summary, sizeof(out_proposal->summary),
                     "Concept: %s (Category: %s)", concept.name, concept.category);
            strncpy(out_proposal->concept, concept.name, sizeof(out_proposal->concept) - 1);
            strncpy(out_proposal->category, "knowledge", sizeof(out_proposal->category) - 1);
        }
    }
    
    /* Calculate identity weight (simplified) */
    out_proposal->identity_weight = item.relevance * 
        (1.0f + (float)item.access_count / 100.0f);
    if (out_proposal->identity_weight > 1.0f) {
        out_proposal->identity_weight = 1.0f;
    }
    
    snprintf(out_proposal->justification, sizeof(out_proposal->justification),
             "Accessed %u times, relevance %.2f, identity weight %.2f",
             item.access_count, item.relevance, out_proposal->identity_weight);
    
    return MC_OK;
}

mc_result_t mc_mark_essential(uint64_t item_id) {
    pthread_mutex_lock(&g_ctx.index.lock);
    mc_item_t *item = index_find(item_id);
    if (!item) {
        pthread_mutex_unlock(&g_ctx.index.lock);
        return MC_ERROR_NOT_FOUND;
    }
    item->flags &= ~MC_FLAG_CANDIDATE;
    item->flags |= MC_FLAG_ESSENTIAL;
    if (g_ctx.stats.candidates_pending > 0) {
        g_ctx.stats.candidates_pending--;
    }
    pthread_mutex_unlock(&g_ctx.index.lock);
    return MC_OK;
}

/* ============================================================================
 * DEGRADATION
 * ============================================================================ */

mc_result_t mc_degrade(uint64_t target_mb, uint32_t *out_degraded) {
    if (!g_ctx.initialized || !out_degraded) return MC_ERROR;
    
    /* For now, just archive and clear old events */
    mc_archive_day();
    
    /* Clear episodic events older than 24 hours */
    int64_t threshold = mc_timestamp() - 86400;
    
    pthread_mutex_lock(&g_ctx.episodic.lock);
    
    uint32_t degraded = 0;
    uint32_t new_count = 0;
    for (uint32_t i = 0; i < g_ctx.episodic.count; i++) {
        if (g_ctx.episodic.events[i].timestamp >= threshold) {
            if (new_count != i) {
                g_ctx.episodic.events[new_count] = g_ctx.episodic.events[i];
            }
            new_count++;
        } else {
            degraded++;
        }
    }
    g_ctx.episodic.count = new_count;
    
    pthread_mutex_unlock(&g_ctx.episodic.lock);
    
    *out_degraded = degraded;
    
    printf("[MC] Degraded %u items\n", degraded);
    
    return MC_OK;
}

/* ============================================================================
 * INTEGRITY
 * ============================================================================ */

mc_result_t mc_verify_integrity(bool repair, uint32_t *out_errors) {
    if (!g_ctx.initialized || !out_errors) return MC_ERROR;
    
    *out_errors = 0;
    
    /* Verify index references */
    pthread_mutex_lock(&g_ctx.index.lock);
    
    for (uint64_t i = 0; i < g_ctx.index.count; i++) {
        mc_item_t *item = &g_ctx.index.items[i];
        
        if (item->type == MC_TYPE_EPISODIC) {
            bool found = false;
            pthread_mutex_lock(&g_ctx.episodic.lock);
            for (uint32_t j = 0; j < g_ctx.episodic.count; j++) {
                if (g_ctx.episodic.events[j].id == item->id) {
                    found = true;
                    break;
                }
            }
            pthread_mutex_unlock(&g_ctx.episodic.lock);
            
            if (!found) {
                (*out_errors)++;
                if (repair) {
                    item->flags |= MC_FLAG_ARCHIVED;  /* Mark as archived */
                }
            }
        }
    }
    
    pthread_mutex_unlock(&g_ctx.index.lock);
    
    return MC_OK;
}
