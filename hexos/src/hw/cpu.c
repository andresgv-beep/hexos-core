/*
 * HEXOS - HELIOS Executive Operating System
 * CPU Detection (Linux)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "../include/hexos_hw.h"
#include "../include/hexos_log.h"

/* ============================================================================
 * HELPERS
 * ============================================================================ */

static void trim_string(char *str) {
    /* Trim leading whitespace */
    char *start = str;
    while (*start == ' ' || *start == '\t') start++;
    
    if (start != str) {
        memmove(str, start, strlen(start) + 1);
    }
    
    /* Trim trailing whitespace and newline */
    size_t len = strlen(str);
    while (len > 0 && (str[len-1] == ' ' || str[len-1] == '\t' || 
                       str[len-1] == '\n' || str[len-1] == '\r')) {
        str[--len] = '\0';
    }
}

static bool file_contains(const char *filename, const char *needle) {
    FILE *f = fopen(filename, "r");
    if (!f) return false;
    
    char line[256];
    bool found = false;
    
    while (fgets(line, sizeof(line), f)) {
        if (strstr(line, needle)) {
            found = true;
            break;
        }
    }
    
    fclose(f);
    return found;
}

/* ============================================================================
 * CPU DETECTION
 * ============================================================================ */

hexos_result_t hexos_hw_detect_cpu(cpu_info_t *cpu) {
    if (!cpu) return HEXOS_ERROR;
    
    memset(cpu, 0, sizeof(cpu_info_t));
    
    FILE *f = fopen("/proc/cpuinfo", "r");
    if (!f) {
        LOG_ERROR("HW", "Cannot open /proc/cpuinfo");
        return HEXOS_ERROR_HW_DETECT;
    }
    
    char line[256];
    char *key, *value;
    int processor_count = 0;
    int physical_id_max = -1;
    int core_id_max = -1;
    int current_physical_id = 0;
    
    while (fgets(line, sizeof(line), f)) {
        /* Parse key : value */
        key = strtok(line, ":");
        value = strtok(NULL, ":");
        
        if (!key || !value) continue;
        
        trim_string(key);
        trim_string(value);
        
        if (strcmp(key, "vendor_id") == 0) {
            strncpy(cpu->vendor, value, HEXOS_MAX_STRING - 1);
        }
        else if (strcmp(key, "model name") == 0) {
            strncpy(cpu->model_name, value, HEXOS_MAX_STRING - 1);
        }
        else if (strcmp(key, "processor") == 0) {
            processor_count++;
        }
        else if (strcmp(key, "physical id") == 0) {
            current_physical_id = atoi(value);
            if (current_physical_id > physical_id_max) {
                physical_id_max = current_physical_id;
            }
        }
        else if (strcmp(key, "core id") == 0) {
            int core_id = atoi(value);
            if (core_id > core_id_max) {
                core_id_max = core_id;
            }
        }
        else if (strcmp(key, "cpu MHz") == 0) {
            if (cpu->base_freq_mhz == 0) {
                cpu->base_freq_mhz = (uint32_t)atof(value);
            }
        }
        else if (strcmp(key, "cache size") == 0) {
            /* This is usually L2 or L3, approximate */
            int cache_kb = atoi(value);
            if (cache_kb > 1024) {
                cpu->l3_cache_kb = cache_kb;
            }
        }
        else if (strcmp(key, "flags") == 0) {
            cpu->has_avx2 = (strstr(value, "avx2") != NULL);
            cpu->has_avx512 = (strstr(value, "avx512") != NULL);
            cpu->has_amx = (strstr(value, "amx") != NULL);
        }
    }
    
    fclose(f);
    
    /* Calculate core counts */
    cpu->logical_cores = processor_count;
    
    /* Try to get physical cores from /sys */
    f = fopen("/sys/devices/system/cpu/cpu0/topology/core_siblings_list", "r");
    if (f) {
        if (fgets(line, sizeof(line), f)) {
            /* Count siblings to determine SMT ratio */
            int siblings = 1;
            for (char *p = line; *p; p++) {
                if (*p == ',' || *p == '-') siblings++;
            }
            cpu->physical_cores = processor_count / (siblings > 0 ? siblings : 1);
        }
        fclose(f);
    }
    
    /* Fallback: if physical_cores not set, estimate from core_id */
    if (cpu->physical_cores == 0) {
        cpu->physical_cores = (core_id_max + 1) * (physical_id_max + 1);
        if (cpu->physical_cores == 0 || cpu->physical_cores > cpu->logical_cores) {
            /* Assume SMT=2 as fallback */
            cpu->physical_cores = cpu->logical_cores / 2;
            if (cpu->physical_cores == 0) cpu->physical_cores = cpu->logical_cores;
        }
    }
    
    /* Try to get max frequency */
    f = fopen("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq", "r");
    if (f) {
        if (fgets(line, sizeof(line), f)) {
            cpu->max_freq_mhz = atoi(line) / 1000;  /* kHz to MHz */
        }
        fclose(f);
    }
    
    /* If max_freq not found, use base_freq */
    if (cpu->max_freq_mhz == 0) {
        cpu->max_freq_mhz = cpu->base_freq_mhz;
    }
    
    /* Get cache sizes from /sys if available */
    for (int i = 0; i <= 3; i++) {
        char path[128];
        snprintf(path, sizeof(path), 
                 "/sys/devices/system/cpu/cpu0/cache/index%d/size", i);
        
        f = fopen(path, "r");
        if (f) {
            if (fgets(line, sizeof(line), f)) {
                int size = atoi(line);
                char unit = line[strlen(line) - 2];  /* K or M */
                if (unit == 'M' || unit == 'm') size *= 1024;
                
                /* Determine cache level */
                char level_path[128];
                snprintf(level_path, sizeof(level_path),
                         "/sys/devices/system/cpu/cpu0/cache/index%d/level", i);
                FILE *lf = fopen(level_path, "r");
                if (lf) {
                    int level = 0;
                    if (fscanf(lf, "%d", &level) == 1) {
                        switch (level) {
                            case 1: cpu->l1_cache_kb = size; break;
                            case 2: cpu->l2_cache_kb = size; break;
                            case 3: cpu->l3_cache_kb = size; break;
                        }
                    }
                    fclose(lf);
                }
            }
            fclose(f);
        }
    }
    
    /* Debug log commented out - tree shows this info
    LOG_DEBUG("HW", "CPU: %s (%d cores, %d threads)", 
              cpu->model_name, cpu->physical_cores, cpu->logical_cores);
    */
    
    return HEXOS_OK;
}
