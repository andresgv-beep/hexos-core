/*
 * HEXOS - HELIOS Executive Operating System
 * Storage Detection (Linux)
 */

#define _DEFAULT_SOURCE  /* For major/minor */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/statvfs.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/sysmacros.h>
#include <unistd.h>
#include <dirent.h>
#include "../include/hexos_hw.h"
#include "../include/hexos_log.h"

/* ============================================================================
 * HELPERS
 * ============================================================================ */

/* Get storage type from device */
static storage_type_t detect_storage_type(const char *path) {
    struct stat st;
    if (stat(path, &st) != 0) {
        return STORAGE_TYPE_UNKNOWN;
    }
    
    /* Get the device major/minor */
    dev_t dev = st.st_dev;
    unsigned int major_num = major(dev);
    
    /* Try to find the block device */
    char sys_path[256];
    DIR *dir = opendir("/sys/block");
    if (!dir) {
        return STORAGE_TYPE_UNKNOWN;
    }
    
    storage_type_t type = STORAGE_TYPE_UNKNOWN;
    struct dirent *entry;
    
    while ((entry = readdir(dir)) != NULL) {
        if (entry->d_name[0] == '.') continue;
        
        /* Check if this is an NVMe device */
        if (strncmp(entry->d_name, "nvme", 4) == 0) {
            /* Check device numbers match (simplified) */
            snprintf(sys_path, sizeof(sys_path), "/sys/block/%s/device", entry->d_name);
            if (access(sys_path, F_OK) == 0) {
                type = STORAGE_TYPE_NVME;
                break;
            }
        }
        
        /* Check rotational flag for HDD vs SSD */
        snprintf(sys_path, sizeof(sys_path), "/sys/block/%s/queue/rotational", entry->d_name);
        FILE *f = fopen(sys_path, "r");
        if (f) {
            int rotational = 1;
            if (fscanf(f, "%d", &rotational) == 1) {
                if (rotational == 0) {
                    type = STORAGE_TYPE_SSD;
                } else {
                    type = STORAGE_TYPE_HDD;
                }
            }
            fclose(f);
        }
    }
    
    closedir(dir);
    
    /* More specific NVMe check */
    if (type == STORAGE_TYPE_UNKNOWN || type == STORAGE_TYPE_SSD) {
        /* Check if any nvme device exists */
        if (access("/dev/nvme0", F_OK) == 0 || access("/dev/nvme0n1", F_OK) == 0) {
            /* Rough heuristic: if nvme exists and we're on fast storage, assume nvme */
            struct statvfs vfs;
            if (statvfs(path, &vfs) == 0) {
                /* NVMe typically has very large block sizes or we can't really tell */
                /* Default to NVMe if /dev/nvme exists */
                type = STORAGE_TYPE_NVME;
            }
        }
    }
    
    return type;
}

/* Estimate storage speed based on type */
static uint32_t estimate_speed(storage_type_t type) {
    switch (type) {
        case STORAGE_TYPE_NVME: return 3500;  /* ~3.5 GB/s typical */
        case STORAGE_TYPE_SSD:  return 550;   /* ~550 MB/s typical SATA SSD */
        case STORAGE_TYPE_HDD:  return 150;   /* ~150 MB/s typical HDD */
        default:                return 100;   /* Conservative default */
    }
}

/* ============================================================================
 * STORAGE DETECTION
 * ============================================================================ */

hexos_result_t hexos_hw_detect_storage(storage_info_t *storage, const char *work_path) {
    if (!storage) return HEXOS_ERROR;
    
    memset(storage, 0, sizeof(storage_info_t));
    
    /* Default work path */
    if (!work_path || strlen(work_path) == 0) {
        work_path = ".";
    }
    
    /* Get real path */
    char real_path[HEXOS_MAX_PATH];
    if (realpath(work_path, real_path) == NULL) {
        strncpy(real_path, work_path, HEXOS_MAX_PATH - 1);
    }
    strncpy(storage->work_path, real_path, HEXOS_MAX_PATH - 1);
    
    /* Get free space */
    struct statvfs vfs;
    if (statvfs(storage->work_path, &vfs) == 0) {
        uint64_t free_bytes = (uint64_t)vfs.f_bavail * vfs.f_frsize;
        storage->work_free_mb = (uint32_t)(free_bytes / (1024 * 1024));
    } else {
        LOG_WARN("HW", "Cannot stat %s", storage->work_path);
        storage->work_free_mb = 0;
    }
    
    /* Detect storage type */
    storage->work_type = detect_storage_type(storage->work_path);
    storage->work_speed_mbs = estimate_speed(storage->work_type);
    
    /* Model path defaults to work path */
    strncpy(storage->model_path, storage->work_path, HEXOS_MAX_PATH - 1);
    storage->model_free_mb = storage->work_free_mb;
    
    const char *type_str;
    switch (storage->work_type) {
        case STORAGE_TYPE_NVME: type_str = "NVMe"; break;
        case STORAGE_TYPE_SSD:  type_str = "SSD"; break;
        case STORAGE_TYPE_HDD:  type_str = "HDD"; break;
        default:                type_str = "Unknown"; break;
    }
    
    (void)type_str;  /* Used for debug logging */
    
    return HEXOS_OK;
}
