/*
 * HEXOS - HELIOS Executive Operating System
 * Main Header
 * 
 * "El cuerpo que protege la mente"
 * 
 * HEXOS is a microkernel supervisor for the HELIOS cognitive ecosystem.
 * It runs EXCLUSIVELY on CPU and never allocates GPU/VRAM resources.
 * 
 * Build with: gcc (NOT nvcc)
 * Link with: libnvidia-ml (NVML) for GPU monitoring only
 */

#ifndef HEXOS_H
#define HEXOS_H

#include "hexos_types.h"
#include "hexos_log.h"
#include "hexos_hw.h"

/* ============================================================================
 * GLOBAL CONTEXT
 * ============================================================================ */

/* Get global HEXOS context (singleton) */
hexos_context_t* hexos_get_context(void);

/* ============================================================================
 * LIFECYCLE
 * ============================================================================ */

/* Initialize HEXOS (runs boot sequence) */
hexos_result_t hexos_init(const char *work_path, const char *model_path);

/* Run main loop (blocking) */
hexos_result_t hexos_run(void);

/* Request shutdown */
void hexos_shutdown(void);

/* Cleanup */
void hexos_cleanup(void);

/* ============================================================================
 * BOOT SEQUENCE
 * ============================================================================ */

/* Individual boot phases */
hexos_result_t hexos_boot_phase1_hardware(hexos_context_t *ctx);
hexos_result_t hexos_boot_phase2_contract(hexos_context_t *ctx);
hexos_result_t hexos_boot_phase3_modules(hexos_context_t *ctx);
hexos_result_t hexos_boot_phase4_resources(hexos_context_t *ctx);
hexos_result_t hexos_boot_phase5_runtime(hexos_context_t *ctx);
hexos_result_t hexos_boot_phase6_helios(hexos_context_t *ctx);

/* ============================================================================
 * STATE QUERIES
 * ============================================================================ */

/* Get current state */
hexos_state_t hexos_get_state(void);

/* Get current profile */
hexos_profile_t hexos_get_profile(void);

/* Set profile */
hexos_result_t hexos_set_profile(hexos_profile_t profile);

/* Get uptime in milliseconds */
uint64_t hexos_get_uptime_ms(void);

/* Get formatted uptime string */
void hexos_get_uptime_str(char *buf, size_t len);

/* ============================================================================
 * HARDWARE CONTRACT ACCESS (read-only after boot)
 * ============================================================================ */

/* Get hardware contract */
const hardware_contract_t* hexos_get_hardware_contract(void);

/* Quick accessors */
uint32_t hexos_get_total_vram_mb(void);
uint32_t hexos_get_usable_ram_mb(void);
uint8_t hexos_get_gpu_count(void);
const gpu_info_t* hexos_get_primary_gpu(void);

/* ============================================================================
 * DYNAMIC STATE
 * ============================================================================ */

/* Get current dynamic state */
const dynamic_state_t* hexos_get_dynamic_state(void);

/* Update dynamic state (called by telemetry) */
hexos_result_t hexos_update_dynamic_state(void);

/* ============================================================================
 * EVENTS
 * ============================================================================ */

/* Add event to log */
void hexos_add_event(log_level_t level, const char *source, const char *message);

/* Get recent events */
const hexos_event_t* hexos_get_events(uint16_t *count);

/* ============================================================================
 * TIME UTILITIES
 * ============================================================================ */

/* Get current timestamp in milliseconds */
uint64_t hexos_time_ms(void);

/* Get current time as formatted string */
void hexos_time_str(char *buf, size_t len);

/* Get date-time as formatted string */
void hexos_datetime_str(char *buf, size_t len);

#endif /* HEXOS_H */
