/*
 * HEXOS - HELIOS Executive Operating System
 * IPC Bus Implementation
 * 
 * Uses POSIX shared memory (/dev/shm) for zero-copy state sharing
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE   /* el Makefile ya lo define; guardas para no redefinir */
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <errno.h>

#include "../include/hexos_ipc.h"
#include "../include/hexos_log.h"

/* ============================================================================
 * TIME UTILITIES
 * ============================================================================ */

static uint64_t get_time_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + ts.tv_nsec;
}

/* ============================================================================
 * SHARED MEMORY
 * ============================================================================ */

static int create_shared_memory(hexos_ipc_ctx_t *ctx) {
    /* Remove any stale shared memory */
    shm_unlink(HEXOS_SHM_STATE);
    
    /* Create new shared memory */
    ctx->shm_fd = shm_open(HEXOS_SHM_STATE, O_CREAT | O_RDWR, 0666);
    if (ctx->shm_fd < 0) {
        LOG_ERROR("IPC", "Failed to create shared memory: %s", strerror(errno));
        return -1;
    }
    
    /* Set size */
    if (ftruncate(ctx->shm_fd, sizeof(hexos_shared_state_t)) < 0) {
        LOG_ERROR("IPC", "Failed to set shared memory size: %s", strerror(errno));
        close(ctx->shm_fd);
        shm_unlink(HEXOS_SHM_STATE);
        return -1;
    }
    
    /* Map into our address space */
    ctx->state = mmap(NULL, sizeof(hexos_shared_state_t),
                      PROT_READ | PROT_WRITE, MAP_SHARED,
                      ctx->shm_fd, 0);
    if (ctx->state == MAP_FAILED) {
        LOG_ERROR("IPC", "Failed to map shared memory: %s", strerror(errno));
        close(ctx->shm_fd);
        shm_unlink(HEXOS_SHM_STATE);
        return -1;
    }
    
    /* Initialize structure */
    memset(ctx->state, 0, sizeof(hexos_shared_state_t));
    ctx->state->magic = HEXOS_SHM_MAGIC;
    ctx->state->version = HEXOS_SHM_VERSION;
    ctx->state->last_update_ns = get_time_ns();
    ctx->state->hexos_running = 1;
    ctx->state->hexos_state = 1;  /* RUNNING */
    ctx->state->modules_connected = (1 << HEXOS_MODULE_HEXOS);
    
    /* Default CONTINUITY message */
    strncpy(ctx->state->memory.continuity_text,
            "Initializing... awaiting Memory Core connection.",
            sizeof(ctx->state->memory.continuity_text) - 1);
    
    /* Default predictive state */
    ctx->state->predictive.armed = 1;
    
    ctx->is_owner = true;
    
    return 0;
}

static int open_shared_memory(hexos_ipc_ctx_t *ctx) {
    /* Open existing shared memory */
    ctx->shm_fd = shm_open(HEXOS_SHM_STATE, O_RDWR, 0666);
    if (ctx->shm_fd < 0) {
        LOG_ERROR("IPC", "Failed to open shared memory: %s", strerror(errno));
        return -1;
    }
    
    /* Map into our address space */
    ctx->state = mmap(NULL, sizeof(hexos_shared_state_t),
                      PROT_READ | PROT_WRITE, MAP_SHARED,
                      ctx->shm_fd, 0);
    if (ctx->state == MAP_FAILED) {
        LOG_ERROR("IPC", "Failed to map shared memory: %s", strerror(errno));
        close(ctx->shm_fd);
        return -1;
    }
    
    /* Verify magic */
    if (ctx->state->magic != HEXOS_SHM_MAGIC) {
        LOG_ERROR("IPC", "Invalid shared memory magic: 0x%08X", ctx->state->magic);
        munmap(ctx->state, sizeof(hexos_shared_state_t));
        close(ctx->shm_fd);
        return -1;
    }
    
    ctx->is_owner = false;
    
    return 0;
}

/* ============================================================================
 * PUBLIC API
 * ============================================================================ */

int hexos_ipc_init(hexos_ipc_ctx_t *ctx) {
    if (!ctx) return -1;
    
    memset(ctx, 0, sizeof(hexos_ipc_ctx_t));
    ctx->my_id = HEXOS_MODULE_HEXOS;
    ctx->shm_fd = -1;
    
    pthread_mutex_init(&ctx->lock, NULL);
    
    /* Create shared memory */
    if (create_shared_memory(ctx) < 0) {
        return -1;
    }
    
    LOG_INFO("IPC", "Shared memory created at %s", HEXOS_SHM_STATE);
    
    return 0;
}

int hexos_ipc_connect(hexos_ipc_ctx_t *ctx, hexos_module_id_t module_id) {
    if (!ctx || module_id <= HEXOS_MODULE_NONE || module_id >= HEXOS_MODULE_MAX) {
        return -1;
    }
    
    memset(ctx, 0, sizeof(hexos_ipc_ctx_t));
    ctx->my_id = module_id;
    ctx->shm_fd = -1;
    
    pthread_mutex_init(&ctx->lock, NULL);
    
    /* Connect to existing shared memory */
    if (open_shared_memory(ctx) < 0) {
        return -1;
    }
    
    /* Register as connected */
    pthread_mutex_lock(&ctx->lock);
    ctx->state->modules_connected |= (1 << module_id);
    ctx->state->last_update_ns = get_time_ns();
    pthread_mutex_unlock(&ctx->lock);
    
    LOG_INFO("IPC", "Module %d connected to shared memory", module_id);
    
    return 0;
}

void hexos_ipc_shutdown(hexos_ipc_ctx_t *ctx) {
    if (!ctx) return;
    
    if (ctx->state) {
        if (ctx->is_owner) {
            /* Mark HEXOS as not running */
            ctx->state->hexos_running = 0;
            ctx->state->last_update_ns = get_time_ns();
        } else {
            /* Unregister module */
            pthread_mutex_lock(&ctx->lock);
            ctx->state->modules_connected &= ~(1 << ctx->my_id);
            pthread_mutex_unlock(&ctx->lock);
        }
        
        munmap(ctx->state, sizeof(hexos_shared_state_t));
        ctx->state = NULL;
    }
    
    if (ctx->shm_fd >= 0) {
        close(ctx->shm_fd);
        ctx->shm_fd = -1;
    }
    
    if (ctx->is_owner) {
        shm_unlink(HEXOS_SHM_STATE);
        LOG_INFO("IPC", "Shared memory destroyed");
    }
    
    pthread_mutex_destroy(&ctx->lock);
}

void hexos_ipc_lock(hexos_ipc_ctx_t *ctx) {
    if (ctx) pthread_mutex_lock(&ctx->lock);
}

void hexos_ipc_unlock(hexos_ipc_ctx_t *ctx) {
    if (ctx) pthread_mutex_unlock(&ctx->lock);
}

void hexos_ipc_get_state(hexos_ipc_ctx_t *ctx, hexos_shared_state_t *out) {
    if (!ctx || !ctx->state || !out) return;
    
    pthread_mutex_lock(&ctx->lock);
    memcpy(out, ctx->state, sizeof(hexos_shared_state_t));
    pthread_mutex_unlock(&ctx->lock);
}

void hexos_ipc_update_cognitive(hexos_ipc_ctx_t *ctx, 
                                 bool running, 
                                 float tokens_per_sec,
                                 uint32_t queue_depth) {
    if (!ctx || !ctx->state) return;
    
    pthread_mutex_lock(&ctx->lock);
    ctx->state->cognitive.running = running ? 1 : 0;
    ctx->state->cognitive.state = running ? 1 : 0;  /* 0=IDLE, 1=RUNNING */
    ctx->state->cognitive.tokens_per_sec = tokens_per_sec;
    ctx->state->cognitive.queue_depth = queue_depth;
    ctx->state->last_update_ns = get_time_ns();
    pthread_mutex_unlock(&ctx->lock);
}

void hexos_ipc_update_memory(hexos_ipc_ctx_t *ctx,
                              bool spillover_active,
                              const char *continuity_text) {
    if (!ctx || !ctx->state) return;
    
    pthread_mutex_lock(&ctx->lock);
    ctx->state->memory.spillover_active = spillover_active ? 1 : 0;
    if (continuity_text) {
        strncpy(ctx->state->memory.continuity_text, continuity_text,
                sizeof(ctx->state->memory.continuity_text) - 1);
        ctx->state->memory.continuity_text[sizeof(ctx->state->memory.continuity_text) - 1] = '\0';
    }
    ctx->state->memory.initialized = 1;
    ctx->state->last_update_ns = get_time_ns();
    pthread_mutex_unlock(&ctx->lock);
}

void hexos_ipc_update_predictive(hexos_ipc_ctx_t *ctx,
                                  bool armed,
                                  bool active,
                                  float hit_rate) {
    if (!ctx || !ctx->state) return;
    
    pthread_mutex_lock(&ctx->lock);
    ctx->state->predictive.armed = armed ? 1 : 0;
    ctx->state->predictive.active = active ? 1 : 0;
    ctx->state->predictive.hit_rate = hit_rate;
    ctx->state->last_update_ns = get_time_ns();
    pthread_mutex_unlock(&ctx->lock);
}

bool hexos_ipc_module_connected(hexos_ipc_ctx_t *ctx, hexos_module_id_t module) {
    if (!ctx || !ctx->state) return false;
    return (ctx->state->modules_connected & (1 << module)) != 0;
}

/* ============================================================================
 * MESSAGE QUEUE (simplified - can expand later with POSIX mq or Unix sockets)
 * ============================================================================ */

int hexos_ipc_send(hexos_ipc_ctx_t *ctx, const hexos_message_t *msg) {
    /* TODO: Implement with POSIX message queues or Unix domain sockets */
    /* For now, this is a placeholder */
    (void)ctx;
    (void)msg;
    return 0;
}

int hexos_ipc_recv(hexos_ipc_ctx_t *ctx, hexos_message_t *msg) {
    /* TODO: Implement with POSIX message queues or Unix domain sockets */
    /* For now, this is a placeholder - returns 0 (no message) */
    (void)ctx;
    (void)msg;
    return 0;
}
