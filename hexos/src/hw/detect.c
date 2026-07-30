/*
 * HEXOS - HELIOS Executive Operating System
 * Hardware Detection Coordinator
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "../include/hexos_hw.h"
#include "../include/hexos_log.h"

/* ============================================================================
 * HOSTNAME / OS INFO
 * ============================================================================ */

void hexos_hw_get_hostname(char *buf, size_t len) {
    if (gethostname(buf, len) != 0) {
        strncpy(buf, "unknown", len - 1);
    }
}

void hexos_hw_get_os_info(os_type_t *type, char *version, size_t len) {
    *type = OS_LINUX;
    
    /* Try to read /etc/os-release */
    FILE *f = fopen("/etc/os-release", "r");
    if (f) {
        char line[256];
        while (fgets(line, sizeof(line), f)) {
            if (strncmp(line, "PRETTY_NAME=", 12) == 0) {
                char *start = line + 12;
                if (*start == '"') start++;
                strncpy(version, start, len - 1);
                /* Remove trailing quote and newline */
                size_t slen = strlen(version);
                while (slen > 0 && (version[slen-1] == '"' || 
                       version[slen-1] == '\n' || version[slen-1] == '\r')) {
                    version[--slen] = '\0';
                }
                fclose(f);
                return;
            }
        }
        fclose(f);
    }
    
    /* Fallback */
    strncpy(version, "Linux", len - 1);
}

/* ============================================================================
 * CONTRACT ID GENERATION
 * ============================================================================ */

void hexos_hw_generate_contract_id(hardware_contract_t *hw) {
    /* Generate a simple hash-like ID from hardware properties */
    uint32_t hash = 0;
    
    /* Mix in various hardware values */
    hash ^= hw->cpu.physical_cores * 31;
    hash ^= hw->cpu.logical_cores * 37;
    hash ^= hw->ram.total_mb * 41;
    hash ^= hw->total_vram_mb * 43;
    hash ^= hw->gpu_count * 47;
    
    if (hw->gpu_count > 0) {
        hash ^= hw->gpus[0].sm_count * 53;
        hash ^= hw->gpus[0].compute_cap_major * 59;
    }
    
    /* Add timestamp component */
    hash ^= (uint32_t)(hw->timestamp & 0xFFFF) * 61;
    
    snprintf(hw->contract_id, HEXOS_CONTRACT_ID_LEN + 1, "hwc_%08x", hash);
}

void hexos_hw_seal_contract(hardware_contract_t *hw) {
    hw->sealed = true;
}

/* ============================================================================
 * BUDGET PROFILES
 * ============================================================================ */

static const budget_profile_t s_profiles[] = {
    /* BALANCED: 60/30/8/2 */
    [PROFILE_BALANCED] = { .model_pct = 60, .kv_pct = 30, .workspace_pct = 8, .reserve_pct = 2 },
    
    /* LOW_VRAM: 65/25/8/2 - more for model, less for KV */
    [PROFILE_LOW_VRAM] = { .model_pct = 65, .kv_pct = 25, .workspace_pct = 8, .reserve_pct = 2 },
    
    /* PERFORMANCE: 55/35/8/2 - more KV for longer context */
    [PROFILE_PERFORMANCE] = { .model_pct = 55, .kv_pct = 35, .workspace_pct = 8, .reserve_pct = 2 },
    
    /* STABLE_LONGCTX: 50/40/8/2 - maximum KV for very long context */
    [PROFILE_STABLE_LONGCTX] = { .model_pct = 50, .kv_pct = 40, .workspace_pct = 8, .reserve_pct = 2 },
};

const budget_profile_t* hexos_hw_get_budget_profile(hexos_profile_t profile) {
    if (profile > PROFILE_STABLE_LONGCTX) {
        profile = PROFILE_BALANCED;
    }
    return &s_profiles[profile];
}

void hexos_hw_calculate_budget(vram_budget_t *budget, uint32_t total_vram_mb, hexos_profile_t profile) {
    if (!budget) return;
    
    const budget_profile_t *p = hexos_hw_get_budget_profile(profile);
    
    budget->total_mb = total_vram_mb;
    budget->model_pct = p->model_pct;
    budget->kv_pct = p->kv_pct;
    budget->workspace_pct = p->workspace_pct;
    budget->reserve_pct = p->reserve_pct;
    
    budget->model_weights_mb = (total_vram_mb * p->model_pct) / 100;
    budget->kv_cache_mb = (total_vram_mb * p->kv_pct) / 100;
    budget->workspace_mb = (total_vram_mb * p->workspace_pct) / 100;
    budget->reserve_mb = (total_vram_mb * p->reserve_pct) / 100;
    
    /* Estimate max tokens (assuming ~640 bytes per token for typical model) */
    budget->max_tokens = (budget->kv_cache_mb * 1024 * 1024) / 640;
}

/* ============================================================================
 * VALIDATION
 * ============================================================================ */

hexos_result_t hexos_hw_validate(const hardware_contract_t *hw) {
    /* Check for NVIDIA GPU */
    if (hw->gpu_count == 0) {
        LOG_ERROR("HW", "NO-GO: No NVIDIA GPU found");
        return HEXOS_NOGO;
    }
    
    bool has_compatible_gpu = false;
    for (int i = 0; i < hw->gpu_count; i++) {
        const gpu_info_t *gpu = &hw->gpus[i];
        
        /* Check compute capability */
        if (gpu->compute_cap_major < HEXOS_MIN_GPU_COMPUTE_MAJOR) {
            LOG_ERROR("HW", "NO-GO: GPU %d compute capability %d.%d < %d.0 required",
                      i, gpu->compute_cap_major, gpu->compute_cap_minor,
                      HEXOS_MIN_GPU_COMPUTE_MAJOR);
            continue;
        }
        
        /* Check VRAM */
        if (gpu->vram_total_mb < HEXOS_MIN_VRAM_MB) {
            LOG_ERROR("HW", "NO-GO: GPU %d VRAM %u MB < %u MB required",
                      i, gpu->vram_total_mb, HEXOS_MIN_VRAM_MB);
            continue;
        }
        
        has_compatible_gpu = true;
    }
    
    if (!has_compatible_gpu) {
        return HEXOS_NOGO;
    }
    
    /* Check RAM */
    if (hw->ram.total_mb < HEXOS_MIN_RAM_MB) {
        LOG_ERROR("HW", "NO-GO: RAM %u MB < %u MB required",
                  hw->ram.total_mb, HEXOS_MIN_RAM_MB);
        return HEXOS_NOGO;
    }
    
    /* Check storage */
    if (hw->storage.work_free_mb < HEXOS_MIN_STORAGE_MB) {
        LOG_ERROR("HW", "NO-GO: Storage %u MB < %u MB required",
                  hw->storage.work_free_mb, HEXOS_MIN_STORAGE_MB);
        return HEXOS_NOGO;
    }
    
    /* Warnings (non-fatal) */
    if (hw->total_vram_mb < HEXOS_REC_VRAM_MB) {
        LOG_WARN("HW", "VRAM %u MB < %u MB recommended - large models may not fit",
                 hw->total_vram_mb, HEXOS_REC_VRAM_MB);
    }
    
    if (hw->ram.total_mb < HEXOS_REC_RAM_MB) {
        LOG_WARN("HW", "RAM %u MB < %u MB recommended - limited spillover capacity",
                 hw->ram.total_mb, HEXOS_REC_RAM_MB);
    }
    
    if (hw->storage.work_type == STORAGE_TYPE_HDD) {
        LOG_WARN("HW", "HDD detected - model loading will be slow");
    }
    
    return HEXOS_OK;
}

/* ============================================================================
 * MAIN DETECTION ENTRY POINT
 * ============================================================================ */

hexos_result_t hexos_hw_detect(hardware_contract_t *hw) {
    if (!hw) return HEXOS_ERROR;
    
    memset(hw, 0, sizeof(hardware_contract_t));
    
    /* Metadata */
    hw->version = 1;
    hw->timestamp = (uint64_t)time(NULL);
    hexos_hw_get_hostname(hw->hostname, HEXOS_MAX_STRING);
    hexos_hw_get_os_info(&hw->os_type, hw->os_version, HEXOS_MAX_STRING);
    
    hexos_result_t result;
    
    /* Detect CPU */
    result = hexos_hw_detect_cpu(&hw->cpu);
    if (result != HEXOS_OK) {
        LOG_ERROR("HW", "CPU detection failed");
        return result;
    }
    
    /* Detect RAM */
    result = hexos_hw_detect_ram(&hw->ram);
    if (result != HEXOS_OK) {
        LOG_ERROR("HW", "RAM detection failed");
        return result;
    }
    
    /* Detect GPUs */
    result = hexos_hw_detect_gpus(hw->gpus, &hw->gpu_count);
    if (result != HEXOS_OK) {
        LOG_ERROR("HW", "GPU detection failed");
        return result;
    }
    
    /* Detect storage */
    result = hexos_hw_detect_storage(&hw->storage, ".");
    if (result != HEXOS_OK) {
        LOG_WARN("HW", "Storage detection failed (non-fatal)");
        /* Continue anyway */
    }
    
    /* Aggregates */
    hw->total_vram_mb = 0;
    for (int i = 0; i < hw->gpu_count; i++) {
        hw->total_vram_mb += hw->gpus[i].vram_total_mb;
        if (hw->gpus[i].is_primary) {
            hw->primary_gpu_idx = i;
        }
    }
    
    /* Flags */
    hw->has_cuda = (hw->gpu_count > 0);
    hw->has_multi_gpu = (hw->gpu_count > 1);
    hw->has_nvlink = false;  /* TODO: detect NVLink */
    hw->has_network = false; /* TODO: detect network */
    hw->migration_capable = hw->has_network;
    
    /* Generate contract ID */
    hexos_hw_generate_contract_id(hw);
    
    return HEXOS_OK;
}

/* ============================================================================
 * RAM STATE UPDATE
 * ============================================================================ */

hexos_result_t hexos_hw_update_ram_state(dynamic_state_t *state) {
    if (!state) return HEXOS_ERROR;
    
    FILE *f = fopen("/proc/meminfo", "r");
    if (!f) return HEXOS_ERROR_IO;
    
    char line[256];
    uint64_t mem_available_kb = 0;
    uint64_t mem_total_kb = 0;
    
    while (fgets(line, sizeof(line), f)) {
        if (sscanf(line, "MemTotal: %lu", &mem_total_kb) == 1) continue;
        if (sscanf(line, "MemAvailable: %lu", &mem_available_kb) == 1) break;
    }
    
    fclose(f);
    
    state->ram_available_mb = (uint32_t)(mem_available_kb / 1024);
    state->ram_used_mb = (uint32_t)((mem_total_kb - mem_available_kb) / 1024);
    
    return HEXOS_OK;
}

/* ============================================================================
 * UTILITY
 * ============================================================================ */

void hexos_hw_format_bytes(uint64_t bytes, char *buf, size_t len) {
    const char *units[] = {"B", "KB", "MB", "GB", "TB"};
    int unit = 0;
    double size = bytes;
    
    while (size >= 1024 && unit < 4) {
        size /= 1024;
        unit++;
    }
    
    snprintf(buf, len, "%.1f %s", size, units[unit]);
}
