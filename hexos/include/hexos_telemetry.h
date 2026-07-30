/*
 * HEXOS - HELIOS Executive Operating System
 * Telemetry System
 */

#ifndef HEXOS_TELEMETRY_H
#define HEXOS_TELEMETRY_H

#include <stdint.h>
#include <stdbool.h>
#include <pthread.h>

/* ============================================================================
 * TELEMETRY DATA STRUCTURES
 * ============================================================================ */

typedef struct {
    /* GPU metrics */
    uint32_t gpu_temp_c;
    uint32_t gpu_power_w;
    uint32_t gpu_util_pct;
    uint32_t vram_used_mb;
    uint32_t vram_total_mb;
    
    /* RAM metrics */
    uint32_t ram_used_mb;
    uint32_t ram_total_mb;
    uint32_t ram_available_mb;
    
    /* CPU metrics */
    float cpu_util_pct;
    
    /* Timing */
    uint64_t uptime_ms;
    uint64_t last_update_ms;
    
    /* Status flags */
    bool gpu_healthy;
    bool thermal_throttle;
    
    /* Runtime state (for Cognitive Kernel integration) */
    bool engine_running;
    float tokens_per_sec;
    uint32_t queue_depth;
    bool predictive_armed;
    bool spillover_active;
} telemetry_snapshot_t;

typedef struct {
    /* Thread control */
    pthread_t thread;
    pthread_mutex_t mutex;
    volatile bool running;
    uint32_t interval_ms;
    
    /* Start time for uptime calculation */
    uint64_t start_time_ms;
    
    /* Latest snapshot */
    telemetry_snapshot_t current;
    
    /* History (ring buffer for graphs) */
    #define TELEMETRY_HISTORY_SIZE 60
    telemetry_snapshot_t history[TELEMETRY_HISTORY_SIZE];
    int history_idx;
    
} telemetry_state_t;

/* ============================================================================
 * API
 * ============================================================================ */

/* Initialize and start telemetry thread */
int hexos_telemetry_init(uint32_t interval_ms);

/* Stop telemetry thread */
void hexos_telemetry_shutdown(void);

/* Get current snapshot (thread-safe copy) */
void hexos_telemetry_get_snapshot(telemetry_snapshot_t *out);

/* Get formatted uptime string */
void hexos_telemetry_format_uptime(uint64_t uptime_ms, char *buf, size_t len);

/* Print dashboard to terminal */
void hexos_telemetry_print_dashboard(void);

/* One-shot update (for systems without thread) */
void hexos_telemetry_update_once(void);

#endif /* HEXOS_TELEMETRY_H */
