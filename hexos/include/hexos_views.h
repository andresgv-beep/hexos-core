/*
 * HEXOS Views Header
 * Structures and functions for panel-based views
 */

#ifndef HEXOS_VIEWS_H
#define HEXOS_VIEWS_H

#include <stdint.h>
#include <stdbool.h>
#include "hexos_ui.h"

/* ============================================================================
 * BOOT PHASE STATUS
 * ============================================================================ */

typedef enum {
    PHASE_PENDING = 0,
    PHASE_RUNNING,
    PHASE_OK,
    PHASE_WARN,
    PHASE_FAIL
} phase_status_t;

/* ============================================================================
 * BOOT PHASE INFO
 * ============================================================================ */

typedef struct {
    phase_status_t status;
    float progress;          /* 0-100 */
    uint64_t start_ms;
    uint64_t time_ms;        /* Duration when complete */
} boot_phase_t;

/* ============================================================================
 * BOOT STATE (shared between views and boot sequence)
 * ============================================================================ */

typedef struct {
    /* Version info */
    int version_major;
    int version_minor;
    int build_number;
    int hnf_version;
    
    /* Session info */
    char session_id[32];
    char hostname[64];
    char profile[32];
    
    /* Boot phases */
    boot_phase_t phases[6];
    int current_phase;
    
    /* Timing */
    uint64_t boot_start_ms;
    uint64_t total_time_ms;
    uint64_t uptime_ms;
    
    /* Status */
    bool boot_complete;
    bool abort_requested;
    bool quit_requested;
    
    /* Alerts */
    char alert_text[64];
    int alert_count;
    
    /* Details panel */
    char detail_line1[80];
    char detail_line2[80];
    
    /* Module status */
    bool hnf_ext_found;
    char gpu_name[64];
    
    /* Continuity message */
    char continuity_message[256];
    
} boot_state_t;

/* ============================================================================
 * BOOT STATE ACCESS
 * ============================================================================ */

/*
 * Get pointer to boot state (singleton)
 */
boot_state_t* hexos_boot_state(void);

/*
 * Initialize boot state with defaults
 */
void boot_state_init(void);

/*
 * Update boot phase status
 */
void boot_phase_start(int phase, const char *detail);
void boot_phase_progress(int phase, float progress);
void boot_phase_detail(const char *line2);
void boot_phase_end(int phase, phase_status_t status);

/*
 * Set alert in telemetry panel
 */
void boot_set_alert(const char *text, int count);

/*
 * Mark boot as complete
 */
void boot_set_complete(void);

/* ============================================================================
 * VIEW FUNCTIONS
 * ============================================================================ */

/*
 * Initialize all views
 */
void hexos_views_init(void);

/* Log ring buffer - call this to add logs visible in VIEW_LOGS */
void hexos_log_to_ring(const char *msg);

/*
 * VIEW_BOOT callbacks
 */
void view_boot_draw(void);
void view_boot_input(ui_key_t key);

/*
 * VIEW_MAIN callbacks
 */
void view_main_draw(void);
void view_main_input(ui_key_t key);

/*
 * VIEW_IDENTITY callbacks
 */
void view_identity_draw(void);
void view_identity_input(ui_key_t key);

/*
 * VIEW_MEMORY callbacks
 */
void view_memory_draw(void);
void view_memory_input(ui_key_t key);

/*
 * VIEW_GPU callbacks
 */
void view_gpu_draw(void);
void view_gpu_input(ui_key_t key);

/*
 * VIEW_LOGS callbacks
 */
void view_logs_draw(void);
void view_logs_input(ui_key_t key);

/*
 * VIEW_ADVANCED callbacks
 */
void view_advanced_draw(void);
void view_advanced_input(ui_key_t key);

#endif /* HEXOS_VIEWS_H */
