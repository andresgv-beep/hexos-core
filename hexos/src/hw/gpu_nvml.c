/*
 * HEXOS - HELIOS Executive Operating System
 * GPU Detection via NVML (Linux)
 * 
 * NOTE: This code runs on CPU only.
 * NVML is a CPU-side library that reads GPU state via PCIe.
 * We do NOT link with CUDA runtime or execute anything on GPU.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include "../include/hexos_hw.h"
#include "../include/hexos_log.h"

/* ============================================================================
 * NVML TYPES (copied from nvml.h to avoid dependency)
 * ============================================================================ */

typedef void* nvmlDevice_t;

typedef enum {
    NVML_SUCCESS = 0,
    NVML_ERROR_UNINITIALIZED = 1,
    NVML_ERROR_INVALID_ARGUMENT = 2,
    NVML_ERROR_NOT_SUPPORTED = 3,
    NVML_ERROR_NO_PERMISSION = 4,
    NVML_ERROR_ALREADY_INITIALIZED = 5,
    NVML_ERROR_NOT_FOUND = 6,
    NVML_ERROR_INSUFFICIENT_SIZE = 7,
    NVML_ERROR_INSUFFICIENT_POWER = 8,
    NVML_ERROR_DRIVER_NOT_LOADED = 9,
    NVML_ERROR_TIMEOUT = 10,
    NVML_ERROR_IRQ_ISSUE = 11,
    NVML_ERROR_LIBRARY_NOT_FOUND = 12,
    NVML_ERROR_FUNCTION_NOT_FOUND = 13,
    NVML_ERROR_CORRUPTED_INFOROM = 14,
    NVML_ERROR_GPU_IS_LOST = 15,
    NVML_ERROR_RESET_REQUIRED = 16,
    NVML_ERROR_OPERATING_SYSTEM = 17,
    NVML_ERROR_LIB_RM_VERSION_MISMATCH = 18,
    NVML_ERROR_IN_USE = 19,
    NVML_ERROR_MEMORY = 20,
    NVML_ERROR_UNKNOWN = 999
} nvmlReturn_t;

typedef struct {
    unsigned long long total;
    unsigned long long free;
    unsigned long long used;
} nvmlMemory_t;

typedef enum {
    NVML_TEMPERATURE_GPU = 0
} nvmlTemperatureSensors_t;

typedef struct {
    unsigned int gpu;
    unsigned int memory;
} nvmlUtilization_t;

typedef enum {
    NVML_PCIE_UTIL_TX_BYTES = 0,
    NVML_PCIE_UTIL_RX_BYTES = 1
} nvmlPcieUtilCounter_t;

/* ============================================================================
 * NVML FUNCTION POINTERS
 * ============================================================================ */

static void *s_nvml_handle = NULL;

typedef nvmlReturn_t (*nvmlInit_t)(void);
typedef nvmlReturn_t (*nvmlShutdown_t)(void);
typedef nvmlReturn_t (*nvmlDeviceGetCount_t)(unsigned int *deviceCount);
typedef nvmlReturn_t (*nvmlDeviceGetHandleByIndex_t)(unsigned int index, nvmlDevice_t *device);
typedef nvmlReturn_t (*nvmlDeviceGetName_t)(nvmlDevice_t device, char *name, unsigned int length);
typedef nvmlReturn_t (*nvmlDeviceGetMemoryInfo_t)(nvmlDevice_t device, nvmlMemory_t *memory);
typedef nvmlReturn_t (*nvmlDeviceGetCudaComputeCapability_t)(nvmlDevice_t device, int *major, int *minor);
typedef nvmlReturn_t (*nvmlDeviceGetNumGpuCores_t)(nvmlDevice_t device, unsigned int *numCores);
typedef nvmlReturn_t (*nvmlDeviceGetTemperature_t)(nvmlDevice_t device, nvmlTemperatureSensors_t sensorType, unsigned int *temp);
typedef nvmlReturn_t (*nvmlDeviceGetPowerUsage_t)(nvmlDevice_t device, unsigned int *power);
/* Relojes: detectar estrangulamiento termico. Sin esto, medir rendimiento
 * es adivinar — entre GPU fria y estrangulada hay un 35% de diferencia. */
typedef nvmlReturn_t (*nvmlDeviceGetClockInfo_t)(nvmlDevice_t device, int type, unsigned int *clock);
typedef nvmlReturn_t (*nvmlDeviceGetMaxClockInfo_t)(nvmlDevice_t device, int type, unsigned int *clock);
typedef nvmlReturn_t (*nvmlDeviceGetEnforcedPowerLimit_t)(nvmlDevice_t device, unsigned int *limit);
typedef nvmlReturn_t (*nvmlDeviceGetUtilizationRates_t)(nvmlDevice_t device, nvmlUtilization_t *utilization);
typedef nvmlReturn_t (*nvmlDeviceGetPciInfo_t)(nvmlDevice_t device, void *pci);
typedef nvmlReturn_t (*nvmlDeviceGetCurrPcieLinkGeneration_t)(nvmlDevice_t device, unsigned int *currLinkGen);
typedef nvmlReturn_t (*nvmlDeviceGetCurrPcieLinkWidth_t)(nvmlDevice_t device, unsigned int *currLinkWidth);
typedef nvmlReturn_t (*nvmlDeviceGetMultiGpuBoard_t)(nvmlDevice_t device, unsigned int *multiGpuBool);

static nvmlInit_t                           nvmlInit = NULL;
static nvmlShutdown_t                       nvmlShutdown = NULL;
static nvmlDeviceGetCount_t                 nvmlDeviceGetCount = NULL;
static nvmlDeviceGetHandleByIndex_t         nvmlDeviceGetHandleByIndex = NULL;
static nvmlDeviceGetName_t                  nvmlDeviceGetName = NULL;
static nvmlDeviceGetMemoryInfo_t            nvmlDeviceGetMemoryInfo = NULL;
static nvmlDeviceGetCudaComputeCapability_t nvmlDeviceGetCudaComputeCapability = NULL;
static nvmlDeviceGetNumGpuCores_t           nvmlDeviceGetNumGpuCores = NULL;
static nvmlDeviceGetTemperature_t           nvmlDeviceGetTemperature = NULL;
static nvmlDeviceGetClockInfo_t             nvmlDeviceGetClockInfo = NULL;
static nvmlDeviceGetMaxClockInfo_t          nvmlDeviceGetMaxClockInfo = NULL;
static nvmlDeviceGetPowerUsage_t            nvmlDeviceGetPowerUsage = NULL;
static nvmlDeviceGetEnforcedPowerLimit_t    nvmlDeviceGetEnforcedPowerLimit = NULL;
static nvmlDeviceGetUtilizationRates_t      nvmlDeviceGetUtilizationRates = NULL;
static nvmlDeviceGetCurrPcieLinkGeneration_t nvmlDeviceGetCurrPcieLinkGeneration = NULL;
static nvmlDeviceGetCurrPcieLinkWidth_t     nvmlDeviceGetCurrPcieLinkWidth = NULL;

/* ============================================================================
 * NVML LOADING
 * ============================================================================ */

static bool load_nvml(void) {
    if (s_nvml_handle) return true;
    
    /* Try to load NVML library */
    s_nvml_handle = dlopen("libnvidia-ml.so.1", RTLD_NOW);
    if (!s_nvml_handle) {
        s_nvml_handle = dlopen("libnvidia-ml.so", RTLD_NOW);
    }
    
    if (!s_nvml_handle) {
        LOG_WARN("HW", "Cannot load NVML: %s", dlerror());
        return false;
    }
    
    /* Load functions */
    #define LOAD_FUNC(name) \
        name = (name##_t)dlsym(s_nvml_handle, #name); \
        if (!name) { LOG_WARN("HW", "Cannot find " #name); }
    
    LOAD_FUNC(nvmlInit);
    LOAD_FUNC(nvmlShutdown);
    LOAD_FUNC(nvmlDeviceGetCount);
    LOAD_FUNC(nvmlDeviceGetHandleByIndex);
    LOAD_FUNC(nvmlDeviceGetName);
    LOAD_FUNC(nvmlDeviceGetMemoryInfo);
    LOAD_FUNC(nvmlDeviceGetCudaComputeCapability);
    LOAD_FUNC(nvmlDeviceGetNumGpuCores);
    LOAD_FUNC(nvmlDeviceGetTemperature);
    LOAD_FUNC(nvmlDeviceGetClockInfo);
    LOAD_FUNC(nvmlDeviceGetMaxClockInfo);
    LOAD_FUNC(nvmlDeviceGetPowerUsage);
    LOAD_FUNC(nvmlDeviceGetEnforcedPowerLimit);
    LOAD_FUNC(nvmlDeviceGetUtilizationRates);
    LOAD_FUNC(nvmlDeviceGetCurrPcieLinkGeneration);
    LOAD_FUNC(nvmlDeviceGetCurrPcieLinkWidth);
    
    #undef LOAD_FUNC
    
    if (!nvmlInit || !nvmlDeviceGetCount || !nvmlDeviceGetHandleByIndex) {
        LOG_ERROR("HW", "NVML missing critical functions");
        dlclose(s_nvml_handle);
        s_nvml_handle = NULL;
        return false;
    }
    
    return true;
}

/* Cierra NVML y suelta la libreria. Existia desde el principio pero no la
 * llamaba nadie: HEXOS hacia dlopen de libnvidia-ml y salia sin cerrarla. */
void hexos_hw_gpu_shutdown(void) {
    if (s_nvml_handle) {
        if (nvmlShutdown) nvmlShutdown();
        dlclose(s_nvml_handle);
        s_nvml_handle = NULL;
    }
}

/* ============================================================================
 * CUDA CORE / TENSOR CORE ESTIMATION
 * ============================================================================ */

uint32_t hexos_hw_estimate_cuda_cores(uint8_t compute_major, uint8_t compute_minor, uint16_t sm_count) {
    /* CUDA cores per SM by compute capability */
    int cores_per_sm;
    
    if (compute_major == 8) {
        /* Ampere (8.0, 8.6, 8.7, 8.9) */
        if (compute_minor == 0) {
            cores_per_sm = 64;   /* A100 */
        } else {
            cores_per_sm = 128;  /* RTX 30xx, RTX 40xx */
        }
    } else if (compute_major == 7) {
        /* Volta/Turing (7.0, 7.5) */
        cores_per_sm = 64;
    } else if (compute_major == 6) {
        /* Pascal (6.0, 6.1, 6.2) */
        cores_per_sm = 64;
    } else if (compute_major == 5) {
        /* Maxwell (5.0, 5.2, 5.3) */
        cores_per_sm = 128;
    } else {
        cores_per_sm = 64;  /* Default */
    }
    
    return sm_count * cores_per_sm;
}

uint16_t hexos_hw_estimate_tensor_cores(uint8_t compute_major, uint16_t sm_count) {
    /* Tensor cores per SM by generation */
    int tc_per_sm;
    
    if (compute_major >= 8) {
        tc_per_sm = 4;   /* Ampere and later: 4 tensor cores per SM */
    } else if (compute_major == 7) {
        tc_per_sm = 8;   /* Volta/Turing: 8 tensor cores per SM */
    } else {
        tc_per_sm = 0;   /* No tensor cores */
    }
    
    return sm_count * tc_per_sm;
}

/* ============================================================================
 * SIMULATION MODE (for development without real GPU)
 * ============================================================================ */

#ifndef HEXOS_SIMULATE_GPU
#define HEXOS_SIMULATE_GPU 0  /* Set to 1 for development without GPU */
#endif

#if HEXOS_SIMULATE_GPU
static void simulate_gpu(gpu_info_t *gpu, int index) {
    memset(gpu, 0, sizeof(gpu_info_t));
    
    gpu->index = index;
    gpu->vendor = GPU_VENDOR_NVIDIA;
    strncpy(gpu->name, "RTX 4070 Ti [SIM]", HEXOS_MAX_STRING - 1);
    strncpy(gpu->driver_version, "535.154.05", HEXOS_MAX_STRING - 1);
    
    gpu->vram_total_mb = 12288;
    gpu->vram_free_mb = 11500;
    
    gpu->compute_cap_major = 8;
    gpu->compute_cap_minor = 9;
    gpu->sm_count = 60;
    gpu->cuda_cores = 7680;
    gpu->tensor_cores = 240;
    
    gpu->pcie_gen = 4;
    gpu->pcie_width = 16;
    gpu->pcie_bandwidth_gbs = 31.5f;
    
    gpu->power_limit_w = 285;
    gpu->temp_limit_c = 83;
    
    gpu->has_fp16 = true;
    gpu->has_bf16 = true;
    gpu->has_int8 = true;
    gpu->has_tf32 = true;
    
    gpu->is_primary = (index == 0);
    gpu->is_healthy = true;
}
#endif /* HEXOS_SIMULATE_GPU */

/* ============================================================================
 * GPU DETECTION
 * ============================================================================ */

hexos_result_t hexos_hw_detect_gpus(gpu_info_t *gpus, uint8_t *count) {
    if (!gpus || !count) return HEXOS_ERROR;
    
    *count = 0;
    memset(gpus, 0, sizeof(gpu_info_t) * HEXOS_MAX_GPUS);
    
#if HEXOS_SIMULATE_GPU
    /* Simulation mode - fake a GPU for development */
    LOG_WARN("HW", "SIMULATION MODE: Using fake GPU data");
    simulate_gpu(&gpus[0], 0);
    *count = 1;
    return HEXOS_OK;
#endif
    
    /* Load NVML */
    if (!load_nvml()) {
        LOG_ERROR("HW", "NVML not available - no GPU detection");
        return HEXOS_ERROR_NO_GPU;
    }
    
    /* Initialize NVML */
    nvmlReturn_t ret = nvmlInit();
    if (ret != NVML_SUCCESS) {
        LOG_ERROR("HW", "nvmlInit failed: %d", ret);
        return HEXOS_ERROR_NO_GPU;
    }
    
    /* Get device count */
    unsigned int device_count = 0;
    ret = nvmlDeviceGetCount(&device_count);
    if (ret != NVML_SUCCESS || device_count == 0) {
        LOG_ERROR("HW", "No NVIDIA GPUs found");
        hexos_hw_gpu_shutdown();
        return HEXOS_ERROR_NO_GPU;
    }
    
    if (device_count > HEXOS_MAX_GPUS) {
        device_count = HEXOS_MAX_GPUS;
    }
    
    /* Get driver version from /proc/driver/nvidia/version */
    char driver_version[64] = "unknown";
    FILE *f = fopen("/proc/driver/nvidia/version", "r");
    if (f) {
        char line[256];
        if (fgets(line, sizeof(line), f)) {
            /* Line format varies, look for version pattern XXX.XX.XX */
            char *p = line;
            while (*p) {
                /* Look for digit followed by dot pattern */
                if (*p >= '0' && *p <= '9') {
                    char *start = p;
                    int dots = 0;
                    while ((*p >= '0' && *p <= '9') || *p == '.') {
                        if (*p == '.') dots++;
                        p++;
                    }
                    /* Valid version has at least one dot and reasonable length */
                    if (dots >= 1 && (p - start) >= 5 && (p - start) < 20) {
                        int len = p - start;
                        strncpy(driver_version, start, len);
                        driver_version[len] = '\0';
                        break;
                    }
                }
                p++;
            }
        }
        fclose(f);
    }
    
    uint32_t max_vram = 0;
    uint8_t primary_idx = 0;
    
    /* Enumerate GPUs */
    for (unsigned int i = 0; i < device_count; i++) {
        gpu_info_t *gpu = &gpus[i];
        gpu->index = i;
        gpu->vendor = GPU_VENDOR_NVIDIA;
        gpu->is_healthy = true;
        
        nvmlDevice_t device;
        ret = nvmlDeviceGetHandleByIndex(i, &device);
        if (ret != NVML_SUCCESS) {
            LOG_WARN("HW", "Cannot get handle for GPU %d", i);
            gpu->is_healthy = false;
            continue;
        }
        
        /* Name */
        if (nvmlDeviceGetName) {
            nvmlDeviceGetName(device, gpu->name, HEXOS_MAX_STRING);
        }
        
        /* Driver version */
        HEXOS_STRCPY(gpu->driver_version, driver_version);
        
        /* Memory */
        if (nvmlDeviceGetMemoryInfo) {
            nvmlMemory_t mem;
            if (nvmlDeviceGetMemoryInfo(device, &mem) == NVML_SUCCESS) {
                gpu->vram_total_mb = (uint32_t)(mem.total / (1024 * 1024));
                gpu->vram_free_mb = (uint32_t)(mem.free / (1024 * 1024));
            }
        }
        
        /* Compute capability */
        if (nvmlDeviceGetCudaComputeCapability) {
            int major = 0, minor = 0;
            if (nvmlDeviceGetCudaComputeCapability(device, &major, &minor) == NVML_SUCCESS) {
                gpu->compute_cap_major = major;
                gpu->compute_cap_minor = minor;
            }
        }
        
        /* SM count (try to get from NVML or estimate) */
        if (nvmlDeviceGetNumGpuCores) {
            unsigned int cores = 0;
            if (nvmlDeviceGetNumGpuCores(device, &cores) == NVML_SUCCESS) {
                /* This might return total cores, need to divide by cores per SM */
                /* For now, estimate SM count */
                gpu->cuda_cores = cores;
            }
        }
        
        /* Estimate SM count from name or compute capability */
        /* This is a rough estimate based on typical configurations */
        if (gpu->cuda_cores > 0) {
            int cores_per_sm = 128;  /* Default for Ampere/Ada */
            if (gpu->compute_cap_major == 7) cores_per_sm = 64;
            gpu->sm_count = gpu->cuda_cores / cores_per_sm;
        } else {
            /* Estimate from GPU name/VRAM */
            if (strstr(gpu->name, "4090")) gpu->sm_count = 128;
            else if (strstr(gpu->name, "4080")) gpu->sm_count = 76;
            else if (strstr(gpu->name, "4070 Ti")) gpu->sm_count = 60;
            else if (strstr(gpu->name, "4070")) gpu->sm_count = 46;
            else if (strstr(gpu->name, "3090")) gpu->sm_count = 82;
            else if (strstr(gpu->name, "3080")) gpu->sm_count = 68;
            else if (strstr(gpu->name, "3070")) gpu->sm_count = 46;
            else gpu->sm_count = 40;  /* Conservative default */
            
            gpu->cuda_cores = hexos_hw_estimate_cuda_cores(
                gpu->compute_cap_major, gpu->compute_cap_minor, gpu->sm_count);
        }
        
        /* Tensor cores */
        gpu->tensor_cores = hexos_hw_estimate_tensor_cores(gpu->compute_cap_major, gpu->sm_count);
        
        /* PCIe info */
        if (nvmlDeviceGetCurrPcieLinkGeneration) {
            unsigned int gen = 0;
            if (nvmlDeviceGetCurrPcieLinkGeneration(device, &gen) == NVML_SUCCESS) {
                gpu->pcie_gen = gen;
            }
        }
        if (nvmlDeviceGetCurrPcieLinkWidth) {
            unsigned int width = 0;
            if (nvmlDeviceGetCurrPcieLinkWidth(device, &width) == NVML_SUCCESS) {
                gpu->pcie_width = width;
            }
        }
        
        /* Estimate PCIe bandwidth */
        float bandwidth_per_lane[] = {0, 0.25, 0.5, 0.985, 1.969, 3.938};  /* GB/s per lane per gen */
        if (gpu->pcie_gen > 0 && gpu->pcie_gen <= 5) {
            gpu->pcie_bandwidth_gbs = bandwidth_per_lane[gpu->pcie_gen] * gpu->pcie_width;
        }
        
        /* Power limit */
        if (nvmlDeviceGetEnforcedPowerLimit) {
            unsigned int limit = 0;
            if (nvmlDeviceGetEnforcedPowerLimit(device, &limit) == NVML_SUCCESS) {
                gpu->power_limit_w = limit / 1000;  /* mW to W */
            }
        }
        
        /* Temp limit (assume 83C typical for gaming GPUs) */
        gpu->temp_limit_c = 83;
        
        /* Feature detection based on compute capability */
        gpu->has_fp16 = (gpu->compute_cap_major >= 6);
        gpu->has_bf16 = (gpu->compute_cap_major >= 8);
        gpu->has_int8 = (gpu->compute_cap_major >= 6);
        gpu->has_tf32 = (gpu->compute_cap_major >= 8);
        
        /* Track primary GPU (most VRAM) */
        if (gpu->vram_total_mb > max_vram) {
            max_vram = gpu->vram_total_mb;
            primary_idx = i;
        }
    }
    
    /* Mark primary GPU */
    gpus[primary_idx].is_primary = true;
    
    *count = device_count;
    
    /* Don't shutdown NVML - keep it open for dynamic state updates */
    
    return HEXOS_OK;
}

/* ============================================================================
 * DYNAMIC STATE UPDATE
 * ============================================================================ */

hexos_result_t hexos_hw_update_gpu_state(dynamic_state_t *state, uint8_t gpu_count) {
    if (!state || !s_nvml_handle) return HEXOS_ERROR;
    
    for (uint8_t i = 0; i < gpu_count && i < HEXOS_MAX_GPUS; i++) {
        nvmlDevice_t device;
        if (nvmlDeviceGetHandleByIndex(i, &device) != NVML_SUCCESS) {
            continue;
        }
        
        /* Memory */
        if (nvmlDeviceGetMemoryInfo) {
            nvmlMemory_t mem;
            if (nvmlDeviceGetMemoryInfo(device, &mem) == NVML_SUCCESS) {
                state->gpu_vram_used_mb[i] = (uint32_t)(mem.used / (1024 * 1024));
                state->gpu_vram_free_mb[i] = (uint32_t)(mem.free / (1024 * 1024));
            }
        }
        
        /* Temperature */
        if (nvmlDeviceGetTemperature) {
            unsigned int temp = 0;
            if (nvmlDeviceGetTemperature(device, NVML_TEMPERATURE_GPU, &temp) == NVML_SUCCESS) {
                state->gpu_temp_c[i] = temp;
            }
        }
        
        /* Relojes (NVML_CLOCK_SM = 1). El maximo se lee cada vez porque es
         * barato y evita cachear un valor erroneo si NVML tarda en responder
         * durante el arranque. */
        if (nvmlDeviceGetClockInfo) {
            unsigned int clk = 0;
            if (nvmlDeviceGetClockInfo(device, 1, &clk) == NVML_SUCCESS) {
                state->gpu_clock_mhz[i] = (uint16_t)clk;
            }
        }
        if (nvmlDeviceGetMaxClockInfo) {
            unsigned int clk = 0;
            if (nvmlDeviceGetMaxClockInfo(device, 1, &clk) == NVML_SUCCESS) {
                state->gpu_clock_max_mhz[i] = (uint16_t)clk;
            }
        }

        /* Power */
        if (nvmlDeviceGetPowerUsage) {
            unsigned int power = 0;
            if (nvmlDeviceGetPowerUsage(device, &power) == NVML_SUCCESS) {
                state->gpu_power_w[i] = power / 1000;  /* mW to W */
            }
        }
        
        /* Utilization */
        if (nvmlDeviceGetUtilizationRates) {
            nvmlUtilization_t util;
            if (nvmlDeviceGetUtilizationRates(device, &util) == NVML_SUCCESS) {
                state->gpu_util_pct[i] = util.gpu;
            }
        }
    }
    
    return HEXOS_OK;
}
