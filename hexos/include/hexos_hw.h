/*
 * HEXOS - HELIOS Executive Operating System
 * Hardware Detection
 * 
 * NOTE: All detection runs on CPU only.
 * GPU info is read via NVML (from CPU), never executed on GPU.
 */

#ifndef HEXOS_HW_H
#define HEXOS_HW_H

#include "hexos_types.h"

/* ============================================================================
 * MINIMUM REQUIREMENTS
 * ============================================================================ */

#define HEXOS_MIN_GPU_COMPUTE_MAJOR    7     /* Volta or newer */
#define HEXOS_MIN_VRAM_MB              4096  /* 4 GB */
#define HEXOS_MIN_RAM_MB               8192  /* 8 GB */
#define HEXOS_MIN_STORAGE_MB           5120  /* 5 GB */

/* Recommended (for warnings) */
#define HEXOS_REC_VRAM_MB              8192  /* 8 GB */
#define HEXOS_REC_RAM_MB               16384 /* 16 GB */

/* ============================================================================
 * HARDWARE DETECTION API
 * ============================================================================ */

/* Main detection entry point - fills hardware_contract */
hexos_result_t hexos_hw_detect(hardware_contract_t *hw);

/* Individual detectors */
hexos_result_t hexos_hw_detect_cpu(cpu_info_t *cpu);
hexos_result_t hexos_hw_detect_ram(ram_info_t *ram);
hexos_result_t hexos_hw_detect_gpus(gpu_info_t *gpus, uint8_t *count);
hexos_result_t hexos_hw_detect_storage(storage_info_t *storage, const char *work_path);
hexos_result_t hexos_hw_detect_network(network_info_t *network);

/* Validation */
hexos_result_t hexos_hw_validate(const hardware_contract_t *hw);

/* Generate contract ID */
void hexos_hw_generate_contract_id(hardware_contract_t *hw);

/* Seal contract (make immutable) */
void hexos_hw_seal_contract(hardware_contract_t *hw);

/* ============================================================================
 * DYNAMIC STATE READING (runtime)
 * ============================================================================ */

/* Update dynamic GPU state (call periodically) */
hexos_result_t hexos_hw_update_gpu_state(dynamic_state_t *state, uint8_t gpu_count);

/* Update dynamic RAM state */
hexos_result_t hexos_hw_update_ram_state(dynamic_state_t *state);

/* ============================================================================
 * VRAM BUDGET CALCULATION
 * ============================================================================ */

/* Calculate VRAM budget based on profile */
void hexos_hw_calculate_budget(
    vram_budget_t *budget,
    uint32_t total_vram_mb,
    hexos_profile_t profile
);

/* Profile-specific percentages */
typedef struct {
    uint8_t model_pct;
    uint8_t kv_pct;
    uint8_t workspace_pct;
    uint8_t reserve_pct;
} budget_profile_t;

/* Get budget profile */
const budget_profile_t* hexos_hw_get_budget_profile(hexos_profile_t profile);

/* ============================================================================
 * UTILITY FUNCTIONS
 * ============================================================================ */

/* Get hostname */
void hexos_hw_get_hostname(char *buf, size_t len);

/* Get OS info */
void hexos_hw_get_os_info(os_type_t *type, char *version, size_t len);

/* Format bytes as human readable */
void hexos_hw_format_bytes(uint64_t bytes, char *buf, size_t len);

/* CUDA cores estimation from SM count and compute capability */
uint32_t hexos_hw_estimate_cuda_cores(uint8_t compute_major, uint8_t compute_minor, uint16_t sm_count);

/* Tensor cores estimation */
uint16_t hexos_hw_estimate_tensor_cores(uint8_t compute_major, uint16_t sm_count);

#endif /* HEXOS_HW_H */
