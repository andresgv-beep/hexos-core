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

/* Tipo de almacenamiento del dispositivo que REALMENTE contiene la ruta.
 *
 * La version anterior recorria /sys/block entero y se quedaba con el ultimo
 * disco leido, y despues una "heuristica" lo forzaba a NVMe si existia
 * cualquier /dev/nvme0. En una maquina con NVMe + HDD reportaba NVMe para
 * rutas que estaban en el HDD. Ahora se resuelve el disco concreto por su
 * major:minor, que es lo que el major() de antes insinuaba y nunca se uso. */
static storage_type_t detect_storage_type(const char *path) {
    struct stat st;
    if (stat(path, &st) != 0) {
        return STORAGE_TYPE_UNKNOWN;
    }

    /* /sys/dev/block/MAJ:MIN apunta al dispositivo exacto. Para una particion
     * es el hijo; el disco padre es quien tiene queue/rotational. */
    char link[64];
    snprintf(link, sizeof(link), "/sys/dev/block/%u:%u",
             major(st.st_dev), minor(st.st_dev));

    char dev_path[HEXOS_MAX_PATH];
    if (realpath(link, dev_path) == NULL) {
        return STORAGE_TYPE_UNKNOWN;
    }

    /* Subir hasta el nodo que tenga queue/ (como mucho un nivel en la
     * practica, pero el bucle evita suponerlo). */
    char probe[HEXOS_MAX_PATH + 32];
    for (int up = 0; up < 3; up++) {
        snprintf(probe, sizeof(probe), "%s/queue/rotational", dev_path);
        FILE *f = fopen(probe, "r");
        if (f) {
            int rotational = 1;
            int got = (fscanf(f, "%d", &rotational) == 1);
            fclose(f);
            if (!got) break;

            /* El nombre del disco distingue NVMe de SATA: nvme0n1 vs sda. */
            const char *name = strrchr(dev_path, '/');
            name = name ? name + 1 : dev_path;
            if (strncmp(name, "nvme", 4) == 0) return STORAGE_TYPE_NVME;
            return rotational ? STORAGE_TYPE_HDD : STORAGE_TYPE_SSD;
        }
        char *slash = strrchr(dev_path, '/');
        if (!slash || slash == dev_path) break;
        *slash = '\0';
    }

    return STORAGE_TYPE_UNKNOWN;
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
        HEXOS_STRCPY(real_path, work_path);
    }
    HEXOS_STRCPY(storage->work_path, real_path);
    
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
    HEXOS_STRCPY(storage->model_path, storage->work_path);
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
