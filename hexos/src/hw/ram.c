/*
 * HEXOS - HELIOS Executive Operating System
 * RAM Detection (Linux)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "../include/hexos_hw.h"
#include "../include/hexos_log.h"

/* ============================================================================
 * RAM DETECTION
 * ============================================================================ */

hexos_result_t hexos_hw_detect_ram(ram_info_t *ram) {
    if (!ram) return HEXOS_ERROR;
    
    memset(ram, 0, sizeof(ram_info_t));
    
    FILE *f = fopen("/proc/meminfo", "r");
    if (!f) {
        LOG_ERROR("HW", "Cannot open /proc/meminfo");
        return HEXOS_ERROR_HW_DETECT;
    }
    
    char line[256];
    char key[64];
    uint64_t value;
    
    uint64_t mem_total_kb = 0;
    uint64_t mem_available_kb = 0;
    uint64_t mem_free_kb = 0;
    uint64_t buffers_kb = 0;
    uint64_t cached_kb = 0;
    
    while (fgets(line, sizeof(line), f)) {
        if (sscanf(line, "%63[^:]: %lu", key, &value) == 2) {
            if (strcmp(key, "MemTotal") == 0) {
                mem_total_kb = value;
            }
            else if (strcmp(key, "MemAvailable") == 0) {
                mem_available_kb = value;
            }
            else if (strcmp(key, "MemFree") == 0) {
                mem_free_kb = value;
            }
            else if (strcmp(key, "Buffers") == 0) {
                buffers_kb = value;
            }
            else if (strcmp(key, "Cached") == 0) {
                cached_kb = value;
            }
        }
    }
    
    fclose(f);
    
    /* Convert to MB */
    ram->total_mb = (uint32_t)(mem_total_kb / 1024);
    
    /* MemAvailable is the best metric for usable memory */
    if (mem_available_kb > 0) {
        ram->available_mb = (uint32_t)(mem_available_kb / 1024);
    } else {
        /* Fallback: Free + Buffers + Cached */
        ram->available_mb = (uint32_t)((mem_free_kb + buffers_kb + cached_kb) / 1024);
    }
    
    /* Estimate OS reserved (total - available at boot is a reasonable estimate) */
    ram->reserved_os_mb = ram->total_mb - ram->available_mb;
    
    /* For HEXOS, usable = available minus some safety margin */
    uint32_t safety_margin = 2048;  /* 2 GB safety for OS */
    if (ram->available_mb > safety_margin) {
        ram->usable_mb = ram->available_mb - safety_margin;
    } else {
        ram->usable_mb = ram->available_mb / 2;
    }
    
    /* Spillover max = 50% of usable */
    ram->spillover_max_mb = ram->usable_mb / 2;
    
    /* Try to detect RAM speed from dmidecode or /sys */
    /* This requires root or specific permissions, so we'll try a simpler approach */
    ram->speed_mhz = 0;  /* Unknown by default */
    ram->channels = 0;   /* Unknown */
    ram->type = RAM_TYPE_UNKNOWN;
    
    /* Try /sys/devices/system/memory for speed (often not available without root) */
    /* For now, leave as unknown - can be populated by external tools */
    
    return HEXOS_OK;
}
