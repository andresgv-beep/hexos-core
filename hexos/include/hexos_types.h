/*
 * HEXOS - HELIOS Executive Operating System
 * Types and Structures
 * 
 * "El cuerpo que protege la mente"
 */

#ifndef HEXOS_TYPES_H
#define HEXOS_TYPES_H

#include <stdint.h>
#include <stdbool.h>
#include <time.h>
#include <string.h>

/* ============================================================================
 * VERSION
 * ============================================================================ */

#define HEXOS_VERSION_MAJOR    1
#define HEXOS_VERSION_MINOR    0
#define HEXOS_VERSION_PATCH    0
#define HEXOS_VERSION_STRING   "1.0.0"

#define HEXOS_HNF_VERSION      9
#define HEXOS_BUILD_NUMBER     247

/* ============================================================================
 * LIMITS
 * ============================================================================ */

#define HEXOS_MAX_GPUS              8
#define HEXOS_MAX_MODULES           16
#define HEXOS_MAX_STRING            64
#define HEXOS_MAX_PATH              256
#define HEXOS_MAX_LOG_MSG           512
#define HEXOS_MAX_EVENTS            100

#define HEXOS_CONTRACT_ID_LEN       16
#define HEXOS_SESSION_ID_LEN        16
#define HEXOS_HASH_LEN              32

/* ============================================================================
 * ENUMS
 * ============================================================================ */

/* System state */
typedef enum {
    HEXOS_STATE_INIT = 0,
    HEXOS_STATE_ATTESTING,
    HEXOS_STATE_READY,
    HEXOS_STATE_RUNNING,
    HEXOS_STATE_DEGRADED,
    HEXOS_STATE_CRITICAL,
    HEXOS_STATE_MIGRATING,
    HEXOS_STATE_SHUTDOWN
} hexos_state_t;

/* Module state */
typedef enum {
    MODULE_STATE_OK = 0,
    MODULE_STATE_DEGRADED,
    MODULE_STATE_FAULTED,
    MODULE_STATE_RECOVERING,
    MODULE_STATE_QUARANTINED
} module_state_t;

/* OS type */
typedef enum {
    OS_LINUX = 0,
    OS_WINDOWS = 1
} os_type_t;

/* GPU vendor */
typedef enum {
    GPU_VENDOR_NVIDIA = 0,
    GPU_VENDOR_AMD,
    GPU_VENDOR_INTEL,
    GPU_VENDOR_OTHER = 255
} gpu_vendor_t;

/* RAM type */
typedef enum {
    RAM_TYPE_UNKNOWN = 0,
    RAM_TYPE_DDR4 = 4,
    RAM_TYPE_DDR5 = 5
} ram_type_t;

/* Storage type */
typedef enum {
    STORAGE_TYPE_UNKNOWN = 0,
    STORAGE_TYPE_HDD,
    STORAGE_TYPE_SSD,
    STORAGE_TYPE_NVME
} storage_type_t;

/* Log level */
typedef enum {
    LOG_TRACE = 0,
    LOG_DEBUG,
    LOG_INFO,
    LOG_WARN,
    LOG_ERROR,
    LOG_FATAL
} log_level_t;

/* Profile */
typedef enum {
    PROFILE_BALANCED = 0,
    PROFILE_LOW_VRAM,
    PROFILE_PERFORMANCE,
    PROFILE_STABLE_LONGCTX
} hexos_profile_t;

/* ============================================================================
 * HARDWARE STRUCTURES
 * ============================================================================ */

/* CPU Information */
typedef struct {
    char vendor[HEXOS_MAX_STRING];          /* "GenuineIntel", "AuthenticAMD" */
    char model_name[HEXOS_MAX_STRING];      /* "AMD Ryzen 9 5900X" */
    uint8_t physical_cores;
    uint8_t logical_cores;
    uint32_t base_freq_mhz;
    uint32_t max_freq_mhz;
    
    /* Cache */
    uint32_t l1_cache_kb;
    uint32_t l2_cache_kb;
    uint32_t l3_cache_kb;
    
    /* Features */
    bool has_avx2;
    bool has_avx512;
    bool has_amx;
} cpu_info_t;

/* RAM Information */
typedef struct {
    uint32_t total_mb;
    uint32_t available_mb;
    uint32_t speed_mhz;
    uint8_t channels;
    ram_type_t type;
    
    /* Derived */
    uint32_t reserved_os_mb;
    uint32_t usable_mb;
    uint32_t spillover_max_mb;
} ram_info_t;

/* GPU Information */
typedef struct {
    uint8_t index;
    gpu_vendor_t vendor;
    char name[HEXOS_MAX_STRING];            /* "NVIDIA GeForce RTX 4070 Ti" */
    char driver_version[HEXOS_MAX_STRING];
    
    /* Memory */
    uint32_t vram_total_mb;
    uint32_t vram_free_mb;
    
    /* Compute */
    uint8_t compute_cap_major;
    uint8_t compute_cap_minor;
    uint16_t sm_count;
    uint32_t cuda_cores;
    uint16_t tensor_cores;
    
    /* Bus */
    uint8_t pcie_gen;
    uint8_t pcie_width;
    float pcie_bandwidth_gbs;
    
    /* Thermal */
    uint16_t power_limit_w;
    uint8_t temp_limit_c;
    
    /* Features */
    bool has_fp16;
    bool has_bf16;
    bool has_int8;
    bool has_tf32;
    
    /* State */
    bool is_primary;
    bool is_healthy;
} gpu_info_t;

/* Storage Information */
typedef struct {
    char work_path[HEXOS_MAX_PATH];
    uint32_t work_free_mb;
    storage_type_t work_type;
    uint32_t work_speed_mbs;
    
    char model_path[HEXOS_MAX_PATH];
    uint32_t model_free_mb;
} storage_info_t;

/* Network Information */
typedef struct {
    bool available;
    char interface_name[HEXOS_MAX_STRING];
    char ip_address[16];
    uint32_t link_speed_mbps;
    bool is_ethernet;
} network_info_t;

/* ============================================================================
 * HARDWARE CONTRACT (inmutable después de boot)
 * ============================================================================ */

typedef struct {
    /* Metadata */
    uint16_t version;
    uint64_t timestamp;
    char hostname[HEXOS_MAX_STRING];
    os_type_t os_type;
    char os_version[HEXOS_MAX_STRING];
    char contract_id[HEXOS_CONTRACT_ID_LEN + 1];
    
    /* Components */
    cpu_info_t cpu;
    ram_info_t ram;
    gpu_info_t gpus[HEXOS_MAX_GPUS];
    uint8_t gpu_count;
    storage_info_t storage;
    network_info_t network;
    
    /* Aggregates */
    uint32_t total_vram_mb;
    uint8_t primary_gpu_idx;
    
    /* Flags */
    bool has_cuda;
    bool has_multi_gpu;
    bool has_nvlink;
    bool has_network;
    bool migration_capable;
    
    /* Sealed flag */
    bool sealed;
} hardware_contract_t;

/* ============================================================================
 * VRAM BUDGET
 * ============================================================================ */

typedef struct {
    uint32_t total_mb;
    uint32_t model_weights_mb;
    uint32_t kv_cache_mb;
    uint32_t workspace_mb;
    uint32_t reserve_mb;
    
    /* Percentages */
    uint8_t model_pct;
    uint8_t kv_pct;
    uint8_t workspace_pct;
    uint8_t reserve_pct;
    
    /* Derived */
    uint32_t max_tokens;
} vram_budget_t;

/* ============================================================================
 * DYNAMIC STATE (actualizado en runtime)
 * ============================================================================ */

typedef struct {
    /* Per GPU */
    uint32_t gpu_vram_used_mb[HEXOS_MAX_GPUS];
    uint32_t gpu_vram_free_mb[HEXOS_MAX_GPUS];
    uint8_t gpu_temp_c[HEXOS_MAX_GPUS];
    uint16_t gpu_power_w[HEXOS_MAX_GPUS];
    uint8_t gpu_util_pct[HEXOS_MAX_GPUS];
    /* Relojes SM: sin esto, comparar tok/s entre dos momentos es adivinar.
     * Un portatil estrangulado corre a ~1400 MHz frente a 2452 de boost. */
    uint16_t gpu_clock_mhz[HEXOS_MAX_GPUS];
    uint16_t gpu_clock_max_mhz[HEXOS_MAX_GPUS];
    
    /* RAM */
    uint32_t ram_used_mb;
    uint32_t ram_available_mb;
    
    /* KV Cache */
    uint32_t kv_vram_mb;
    uint32_t kv_ram_mb;
    uint32_t kv_tokens;
    bool spillover_active;
    float spillover_slowdown;
    
    /* Runtime */
    float tokens_per_second;
    float latency_ms;
    uint32_t context_tokens;
    
    /* Stress */
    uint8_t stress_score;
    
    /* Timestamps */
    uint64_t last_update_ms;
} dynamic_state_t;

/* ============================================================================
 * MODULE INFO
 * ============================================================================ */

typedef struct {
    char id[HEXOS_MAX_STRING];
    char version[HEXOS_MAX_STRING];
    uint8_t abi_version;
    module_state_t state;
    uint64_t uptime_ms;
    uint32_t restart_count;
    float cpu_usage_pct;
    uint32_t ram_usage_mb;
} module_info_t;

/* ============================================================================
 * SESSION INFO
 * ============================================================================ */

typedef struct {
    char session_id[HEXOS_SESSION_ID_LEN + 1];
    uint64_t start_time;
    hexos_state_t state;
    hexos_profile_t profile;
    uint64_t uptime_ms;
    
    /* Boot info */
    float boot_time_s;
    uint8_t module_count;
    uint8_t warnings;
    uint8_t errors;
} session_info_t;

/* ============================================================================
 * EVENT
 * ============================================================================ */

typedef struct {
    uint64_t timestamp;
    log_level_t level;
    char source[HEXOS_MAX_STRING];
    char message[HEXOS_MAX_LOG_MSG];
} hexos_event_t;

/* ============================================================================
 * BOOT PHASE TIMING
 * ============================================================================ */

typedef struct {
    float hardware_detection_s;
    float hardware_contract_s;
    float module_attestation_s;
    float resource_allocation_s;
    float model_loading_s;
    float helios_activation_s;
    float total_s;
} boot_timing_t;

/* ============================================================================
 * CONTEXT (main runtime structure)
 * ============================================================================ */

typedef struct {
    /* Core */
    session_info_t session;
    hardware_contract_t hw_contract;
    vram_budget_t vram_budget;
    dynamic_state_t dynamic;
    boot_timing_t boot_timing;
    
    /* Modules */
    module_info_t modules[HEXOS_MAX_MODULES];
    uint8_t module_count;
    
    /* Events */
    hexos_event_t events[HEXOS_MAX_EVENTS];
    uint16_t event_count;
    uint16_t event_head;
    
    /* Flags */
    bool initialized;
    bool running;
    bool console_active;
} hexos_context_t;

/* ============================================================================
 * RESULT TYPE
 * ============================================================================ */

typedef enum {
    HEXOS_OK = 0,
    HEXOS_ERROR,
    HEXOS_ERROR_INIT,
    HEXOS_ERROR_HW_DETECT,
    HEXOS_ERROR_NO_GPU,
    HEXOS_ERROR_INCOMPATIBLE,
    HEXOS_ERROR_NO_MEMORY,
    HEXOS_ERROR_MODULE,
    HEXOS_ERROR_IO,
    HEXOS_NOGO
} hexos_result_t;

/* ============================================================================
 * UTILIDADES
 * ============================================================================ */

/* Copia acotada que SIEMPRE cierra la cadena.
 *
 * strncpy(dst, src, sizeof(dst)-1) no termina en nulo cuando la fuente llena
 * el buffer: deja una cadena abierta que el siguiente printf lee de mas.
 * Solo funcionaba aqui por accidente, porque los structs se inicializan a
 * cero. Usar esto en su lugar. */
static inline void hexos_strcpy(char *dst, const char *src, size_t dst_size) {
    if (!dst || dst_size == 0) return;
    if (!src) { dst[0] = '\0'; return; }
    size_t n = strnlen(src, dst_size - 1);
    memcpy(dst, src, n);
    dst[n] = '\0';
}

#define HEXOS_STRCPY(dst, src) hexos_strcpy((dst), (src), sizeof(dst))

#endif /* HEXOS_TYPES_H */
