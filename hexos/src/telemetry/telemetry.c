/*
 * HEXOS - HELIOS Executive Operating System
 * Telemetry System Implementation
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE   /* el Makefile ya lo define; guardas para no redefinir */
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/time.h>
#include <dlfcn.h>
#include "../include/hexos_telemetry.h"
#include "../include/hexos_log.h"
#include "../include/hexos_ipc.h"

/* External IPC context from main.c */
extern hexos_ipc_ctx_t* hexos_get_ipc(void);

/* ============================================================================
 * NVML DYNAMIC LOADING (for GPU metrics)
 * ============================================================================ */

typedef void* nvmlDevice_t;
typedef int nvmlReturn_t;

typedef struct {
    unsigned long long total;
    unsigned long long free;
    unsigned long long used;
} nvmlMemory_t;

typedef struct {
    unsigned int gpu;
    unsigned int memory;
} nvmlUtilization_t;

#define NVML_SUCCESS 0
#define NVML_TEMPERATURE_GPU 0

static void *s_nvml_handle = NULL;

/* Function pointers */
typedef nvmlReturn_t (*nvmlInit_t)(void);
typedef nvmlReturn_t (*nvmlShutdown_t)(void);
typedef nvmlReturn_t (*nvmlDeviceGetHandleByIndex_t)(unsigned int index, nvmlDevice_t *device);
typedef nvmlReturn_t (*nvmlDeviceGetTemperature_t)(nvmlDevice_t device, int sensorType, unsigned int *temp);
typedef nvmlReturn_t (*nvmlDeviceGetMemoryInfo_t)(nvmlDevice_t device, nvmlMemory_t *memory);
typedef nvmlReturn_t (*nvmlDeviceGetUtilizationRates_t)(nvmlDevice_t device, nvmlUtilization_t *utilization);
typedef nvmlReturn_t (*nvmlDeviceGetPowerUsage_t)(nvmlDevice_t device, unsigned int *power);
typedef nvmlReturn_t (*nvmlDeviceGetClockInfo_t)(nvmlDevice_t device, int type, unsigned int *clock);
typedef nvmlReturn_t (*nvmlDeviceGetThrottleReasons_t)(nvmlDevice_t device, unsigned long long *reasons);

static nvmlInit_t nvml_init = NULL;
static nvmlShutdown_t nvml_shutdown = NULL;
static nvmlDeviceGetHandleByIndex_t nvml_get_handle = NULL;
static nvmlDeviceGetTemperature_t nvml_get_temp = NULL;
static nvmlDeviceGetMemoryInfo_t nvml_get_memory = NULL;
static nvmlDeviceGetUtilizationRates_t nvml_get_util = NULL;
static nvmlDeviceGetPowerUsage_t nvml_get_power = NULL;
static nvmlDeviceGetClockInfo_t nvml_get_clock = NULL;
static nvmlDeviceGetClockInfo_t nvml_get_clock_max = NULL;
static nvmlDeviceGetThrottleReasons_t nvml_get_throttle = NULL;

static nvmlDevice_t s_gpu_device = NULL;
static bool s_nvml_ready = false;

/* ============================================================================
 * GLOBAL STATE
 * ============================================================================ */

static telemetry_state_t s_state = {0};

/* ============================================================================
 * TIME UTILITIES
 * ============================================================================ */

static uint64_t get_time_ms(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (uint64_t)tv.tv_sec * 1000 + tv.tv_usec / 1000;
}

/* ============================================================================
 * NVML INITIALIZATION
 * ============================================================================ */

static bool init_nvml_telemetry(void) {
    if (s_nvml_ready) return true;
    
    /* Try to load NVML */
    s_nvml_handle = dlopen("libnvidia-ml.so.1", RTLD_NOW);
    if (!s_nvml_handle) {
        s_nvml_handle = dlopen("libnvidia-ml.so", RTLD_NOW);
    }
    
    if (!s_nvml_handle) {
        return false;
    }
    
    /* Load functions */
    nvml_init = (nvmlInit_t)dlsym(s_nvml_handle, "nvmlInit_v2");
    if (!nvml_init) nvml_init = (nvmlInit_t)dlsym(s_nvml_handle, "nvmlInit");
    
    nvml_shutdown = (nvmlShutdown_t)dlsym(s_nvml_handle, "nvmlShutdown");
    nvml_get_handle = (nvmlDeviceGetHandleByIndex_t)dlsym(s_nvml_handle, "nvmlDeviceGetHandleByIndex_v2");
    if (!nvml_get_handle) nvml_get_handle = (nvmlDeviceGetHandleByIndex_t)dlsym(s_nvml_handle, "nvmlDeviceGetHandleByIndex");
    
    nvml_get_temp = (nvmlDeviceGetTemperature_t)dlsym(s_nvml_handle, "nvmlDeviceGetTemperature");
    nvml_get_memory = (nvmlDeviceGetMemoryInfo_t)dlsym(s_nvml_handle, "nvmlDeviceGetMemoryInfo");
    nvml_get_util = (nvmlDeviceGetUtilizationRates_t)dlsym(s_nvml_handle, "nvmlDeviceGetUtilizationRates");
    nvml_get_power = (nvmlDeviceGetPowerUsage_t)dlsym(s_nvml_handle, "nvmlDeviceGetPowerUsage");
    nvml_get_clock = (nvmlDeviceGetClockInfo_t)dlsym(s_nvml_handle, "nvmlDeviceGetClockInfo");
    nvml_get_clock_max = (nvmlDeviceGetClockInfo_t)dlsym(s_nvml_handle, "nvmlDeviceGetMaxClockInfo");
    /* El nombre cambio en NVML 12; probar el nuevo y caer al antiguo. */
    nvml_get_throttle = (nvmlDeviceGetThrottleReasons_t)dlsym(s_nvml_handle, "nvmlDeviceGetCurrentClocksEventReasons");
    if (!nvml_get_throttle) {
        nvml_get_throttle = (nvmlDeviceGetThrottleReasons_t)dlsym(s_nvml_handle, "nvmlDeviceGetCurrentClocksThrottleReasons");
    }
    
    if (!nvml_init || !nvml_get_handle) {
        dlclose(s_nvml_handle);
        s_nvml_handle = NULL;
        return false;
    }
    
    /* Initialize NVML */
    if (nvml_init() != NVML_SUCCESS) {
        dlclose(s_nvml_handle);
        s_nvml_handle = NULL;
        return false;
    }
    
    /* Get handle to GPU 0 */
    if (nvml_get_handle(0, &s_gpu_device) != NVML_SUCCESS) {
        nvml_shutdown();
        dlclose(s_nvml_handle);
        s_nvml_handle = NULL;
        return false;
    }
    
    s_nvml_ready = true;
    return true;
}

/* ============================================================================
 * METRIC COLLECTION
 * ============================================================================ */

static void collect_gpu_metrics(telemetry_snapshot_t *snap) {
    snap->gpu_healthy = false;
    snap->gpu_temp_c = 0;
    snap->gpu_power_w = 0;
    snap->gpu_util_pct = 0;
    snap->vram_used_mb = 0;
    snap->thermal_throttle = false;
    snap->gpu_clock_mhz = 0;
    snap->gpu_clock_max_mhz = 0;
    
    if (!s_nvml_ready) return;
    
    /* Temperature */
    if (nvml_get_temp) {
        unsigned int temp = 0;
        if (nvml_get_temp(s_gpu_device, NVML_TEMPERATURE_GPU, &temp) == NVML_SUCCESS) {
            snap->gpu_temp_c = temp;
            snap->gpu_healthy = true;
        }
    }
    
    /* Memory */
    if (nvml_get_memory) {
        nvmlMemory_t mem = {0};
        if (nvml_get_memory(s_gpu_device, &mem) == NVML_SUCCESS) {
            snap->vram_total_mb = (uint32_t)(mem.total / (1024 * 1024));
            snap->vram_used_mb = (uint32_t)(mem.used / (1024 * 1024));
            snap->gpu_healthy = true;
        }
    }
    
    /* Utilization */
    if (nvml_get_util) {
        nvmlUtilization_t util = {0};
        if (nvml_get_util(s_gpu_device, &util) == NVML_SUCCESS) {
            snap->gpu_util_pct = util.gpu;
        }
    }
    
    /* Power */
    if (nvml_get_power) {
        unsigned int power = 0;
        if (nvml_get_power(s_gpu_device, &power) == NVML_SUCCESS) {
            snap->gpu_power_w = power / 1000;  /* mW to W */
        }
    }

    /* Relojes SM (NVML_CLOCK_SM = 1, NVML_CLOCK_ID_MAX apunta al boost).
     *
     * El throttle se MIDE, no se supone: antes se marcaba por temperatura
     * >= 83C, pero un portatil puede recortar por limite de potencia estando
     * frio, y puede pasar de 83C sosteniendo el boost. Lo unico que importa
     * para interpretar un tok/s es el reloj real frente al maximo. */
    if (nvml_get_clock) {
        unsigned int cur = 0, max = 0;
        if (nvml_get_clock(s_gpu_device, 1, &cur) == NVML_SUCCESS) {
            snap->gpu_clock_mhz = (uint16_t)cur;
        }
        if (nvml_get_clock_max && nvml_get_clock_max(s_gpu_device, 1, &max) == NVML_SUCCESS) {
            snap->gpu_clock_max_mhz = (uint16_t)max;
        }
    }

    /* El throttle lo dice el driver, no lo deducimos nosotros.
     *
     * Dos intentos anteriores fallaron: por temperatura (>=83C) daba falsos
     * negativos, porque un portatil recorta por potencia estando frio; y por
     * porcentaje del reloj maximo daba falsos POSITIVOS, porque el maximo que
     * reporta NVML (3090 MHz aqui) es el bin teorico, no un reloj que la
     * tarjeta sostenga jamas. Bajo carga normal se corre a ~2450 y cualquier
     * umbral contra 3090 grita siempre.
     *
     * Bits que importan: recorte por potencia (0x4, 0x80), por hardware (0x8)
     * y termico (0x20, 0x40). Se excluye GpuIdle (0x1), que es bajar de reloj
     * a proposito por no tener trabajo. */
    if (nvml_get_throttle) {
        unsigned long long reasons = 0;
        if (nvml_get_throttle(s_gpu_device, &reasons) == NVML_SUCCESS) {
            const unsigned long long RECORTE = 0x4ULL | 0x8ULL | 0x20ULL
                                             | 0x40ULL | 0x80ULL;
            snap->thermal_throttle = (reasons & RECORTE) != 0;
        }
    }
}

static void collect_ram_metrics(telemetry_snapshot_t *snap) {
    snap->ram_used_mb = 0;
    snap->ram_total_mb = 0;
    snap->ram_available_mb = 0;
    
    FILE *f = fopen("/proc/meminfo", "r");
    if (!f) return;
    
    char line[256];
    uint64_t total = 0, available = 0;
    
    while (fgets(line, sizeof(line), f)) {
        if (sscanf(line, "MemTotal: %lu kB", &total) == 1) continue;
        if (sscanf(line, "MemAvailable: %lu kB", &available) == 1) break;
    }
    fclose(f);
    
    snap->ram_total_mb = (uint32_t)(total / 1024);
    snap->ram_available_mb = (uint32_t)(available / 1024);
    snap->ram_used_mb = snap->ram_total_mb - snap->ram_available_mb;
}

static void collect_cpu_metrics(telemetry_snapshot_t *snap) {
    /* Simple CPU usage from /proc/stat */
    static uint64_t prev_idle = 0, prev_total = 0;
    
    FILE *f = fopen("/proc/stat", "r");
    if (!f) {
        snap->cpu_util_pct = 0;
        return;
    }
    
    char line[256];
    if (fgets(line, sizeof(line), f)) {
        uint64_t user, nice, system, idle, iowait, irq, softirq;
        if (sscanf(line, "cpu %lu %lu %lu %lu %lu %lu %lu",
                   &user, &nice, &system, &idle, &iowait, &irq, &softirq) == 7) {
            uint64_t total = user + nice + system + idle + iowait + irq + softirq;
            uint64_t idle_total = idle + iowait;
            
            if (prev_total > 0) {
                uint64_t total_diff = total - prev_total;
                uint64_t idle_diff = idle_total - prev_idle;
                if (total_diff > 0) {
                    snap->cpu_util_pct = 100.0f * (1.0f - (float)idle_diff / total_diff);
                }
            }
            
            prev_idle = idle_total;
            prev_total = total;
        }
    }
    fclose(f);
}

static void update_telemetry(void) {
    telemetry_snapshot_t snap = {0};
    
    /* Collect hardware metrics */
    collect_gpu_metrics(&snap);
    collect_ram_metrics(&snap);
    collect_cpu_metrics(&snap);
    
    /* Update timing */
    snap.last_update_ms = get_time_ms();
    snap.uptime_ms = snap.last_update_ms - s_state.start_time_ms;
    
    /* Read runtime state from IPC if available */
    hexos_ipc_ctx_t *ipc = hexos_get_ipc();
    if (ipc && ipc->state) {
        /* Cognitive Kernel state */
        snap.engine_running = ipc->state->cognitive.running;
        snap.tokens_per_sec = ipc->state->cognitive.tokens_per_sec;
        snap.queue_depth = ipc->state->cognitive.queue_depth;
        
        /* Memory Core state */
        snap.spillover_active = ipc->state->memory.spillover_active;
        
        /* Predictive state */
        snap.predictive_armed = ipc->state->predictive.armed;
    } else {
        /* Defaults when IPC not available */
        snap.engine_running = false;
        snap.tokens_per_sec = 0.0f;
        snap.queue_depth = 0;
        snap.predictive_armed = true;
        
        /* Fallback: spillover activates when VRAM pressure > 85% */
        int vram_pct = snap.vram_total_mb > 0 ? (snap.vram_used_mb * 100 / snap.vram_total_mb) : 0;
        snap.spillover_active = (vram_pct > 85);
    }
    
    /* Thread-safe update */
    pthread_mutex_lock(&s_state.mutex);
    s_state.current = snap;
    
    /* Add to history */
    s_state.history[s_state.history_idx] = snap;
    s_state.history_idx = (s_state.history_idx + 1) % TELEMETRY_HISTORY_SIZE;
    
    pthread_mutex_unlock(&s_state.mutex);
}

/* ============================================================================
 * TELEMETRY THREAD
 * ============================================================================ */

static void* telemetry_thread(void *arg) {
    (void)arg;
    
    while (s_state.running) {
        update_telemetry();
        usleep(s_state.interval_ms * 1000);
    }
    
    return NULL;
}

/* ============================================================================
 * PUBLIC API
 * ============================================================================ */

int hexos_telemetry_init(uint32_t interval_ms) {
    if (s_state.running) return 0;  /* Already running */
    
    /* Initialize NVML for GPU metrics */
    init_nvml_telemetry();
    
    /* Initialize state */
    memset(&s_state, 0, sizeof(s_state));
    s_state.interval_ms = interval_ms > 0 ? interval_ms : 1000;
    s_state.start_time_ms = get_time_ms();
    s_state.running = true;
    
    pthread_mutex_init(&s_state.mutex, NULL);
    
    /* Do initial update */
    update_telemetry();
    
    /* Start thread */
    if (pthread_create(&s_state.thread, NULL, telemetry_thread, NULL) != 0) {
        LOG_WARN("TELEMETRY", "Failed to create thread, running in manual mode");
        s_state.running = false;
        return -1;
    }
    
    return 0;
}

void hexos_telemetry_shutdown(void) {
    if (!s_state.running) return;
    
    s_state.running = false;
    pthread_join(s_state.thread, NULL);
    pthread_mutex_destroy(&s_state.mutex);
    
    /* Cleanup NVML */
    if (s_nvml_ready && nvml_shutdown) {
        nvml_shutdown();
    }
    if (s_nvml_handle) {
        dlclose(s_nvml_handle);
        s_nvml_handle = NULL;
    }
    s_nvml_ready = false;
}

void hexos_telemetry_get_snapshot(telemetry_snapshot_t *out) {
    if (!out) return;
    
    pthread_mutex_lock(&s_state.mutex);
    *out = s_state.current;
    pthread_mutex_unlock(&s_state.mutex);
}

void hexos_telemetry_format_uptime(uint64_t uptime_ms, char *buf, size_t len) {
    uint64_t seconds = uptime_ms / 1000;
    uint64_t minutes = seconds / 60;
    uint64_t hours = minutes / 60;
    
    seconds %= 60;
    minutes %= 60;
    
    snprintf(buf, len, "%lu:%02lu:%02lu", hours, minutes, seconds);
}

void hexos_telemetry_update_once(void) {
    update_telemetry();
}

void hexos_telemetry_print_dashboard(void) {
    telemetry_snapshot_t snap;
    hexos_telemetry_get_snapshot(&snap);
    
    char uptime_str[32];
    hexos_telemetry_format_uptime(snap.uptime_ms, uptime_str, sizeof(uptime_str));
    
    /* Calculate states */
    const char *gpu_state = snap.gpu_util_pct > 5 ? "RUNNING" : "IDLE";
    const char *cpu_state = snap.cpu_util_pct > 5.0f ? "ACTIVE" : "IDLE";
    
    int vram_pct = snap.vram_total_mb > 0 ? (snap.vram_used_mb * 100 / snap.vram_total_mb) : 0;
    const char *mem_state = vram_pct > 85 ? "CRITICAL" : (vram_pct > 70 ? "PRESSURE" : "STABLE");
    const char *mem_color = vram_pct > 85 ? ANSI_RED : (vram_pct > 70 ? ANSI_YELLOW : ANSI_GREEN);
    
    int ram_pct = snap.ram_total_mb > 0 ? (snap.ram_used_mb * 100 / snap.ram_total_mb) : 0;
    int cpu_pct = (int)snap.cpu_util_pct;
    if (cpu_pct > 100) cpu_pct = 100;
    if (cpu_pct < 0) cpu_pct = 0;
    
    const char *engine_state = snap.engine_running ? "RUNNING" : "IDLE";
    const char *pred_state = snap.predictive_armed ? "ARMED" : "OFF";
    const char *spill_state = snap.spillover_active ? "ACTIVE" : "STANDBY";
    
    const char *status_str = snap.thermal_throttle ? "THROTTLE" : "NOMINAL";
    const char *status_color = snap.thermal_throttle ? ANSI_YELLOW : ANSI_GREEN;
    const char *gpu_health = snap.gpu_healthy ? "HEALTHY" : "ERROR";
    const char *gpu_color = snap.gpu_healthy ? ANSI_GREEN : ANSI_RED;
    
    /* Build bar strings (40 chars) */
    char vram_bar[48], ram_bar[48], cpu_bar[48];
    int i;
    
    int vram_fill = (40 * vram_pct) / 100;
    for (i = 0; i < vram_fill; i++) vram_bar[i] = '#';
    for (; i < 40; i++) vram_bar[i] = '-';
    vram_bar[40] = '\0';
    
    int ram_fill = (40 * ram_pct) / 100;
    for (i = 0; i < ram_fill; i++) ram_bar[i] = '#';
    for (; i < 40; i++) ram_bar[i] = '-';
    ram_bar[40] = '\0';
    
    int cpu_fill = (40 * cpu_pct) / 100;
    for (i = 0; i < cpu_fill; i++) cpu_bar[i] = '#';
    for (; i < 40; i++) cpu_bar[i] = '-';
    cpu_bar[40] = '\0';
    
    /* All lines exactly 78 chars wide (76 content + 2 borders) */
    printf("+----------------------------------------------------------------------------+\n");
    printf("| HEXOS DASHBOARD                                       Uptime: %-10s |\n", uptime_str);
    printf("+----------------------------------------------------------------------------+\n");
    printf("|                                                                            |\n");
    printf("| GPU 0                                                                      |\n");
    printf("|   Temp: %3uC   Power: %3uW   Util: %3u%%   State: %-7s                   |\n",
           snap.gpu_temp_c, snap.gpu_power_w, snap.gpu_util_pct, gpu_state);
    printf("|   VRAM: %5u / %5u MB (%2d%%)   Budget: 60%% MODEL / 30%% KV                |\n",
           snap.vram_used_mb, snap.vram_total_mb, vram_pct);
    printf("|          [%s]                        |\n", vram_bar);
    printf("|                                                                            |\n");
    printf("| RAM                                                                        |\n");
    printf("|   Used: %5u / %5u MB (%2d%%)   Spillover: %-7s                          |\n",
           snap.ram_used_mb, snap.ram_total_mb, ram_pct, spill_state);
    printf("|          [%s]                        |\n", ram_bar);
    printf("|                                                                            |\n");
    printf("| CPU                                                                        |\n");
    printf("|   Util: %5.1f%%                      State: %-7s                         |\n",
           snap.cpu_util_pct, cpu_state);
    printf("|          [%s]                        |\n", cpu_bar);
    printf("|                                                                            |\n");
    printf("+----------------------------------------------------------------------------+\n");
    printf("| RUNTIME                                                                    |\n");
    printf("|   Engine: %-7s    Tokens/s: %6.1f    Queue: %-3u                        |\n",
           engine_state, snap.tokens_per_sec, snap.queue_depth);
    printf("|   Predictive Memory: %-5s          Spillover: %-7s                     |\n",
           pred_state, spill_state);
    printf("|                                                                            |\n");
    printf("+----------------------------------------------------------------------------+\n");
    printf("| Status: %s%-8s%s    GPU: %s%-7s%s    Memory: %s%-8s%s                   |\n",
           status_color, status_str, ANSI_RESET,
           gpu_color, gpu_health, ANSI_RESET,
           mem_color, mem_state, ANSI_RESET);
    printf("+----------------------------------------------------------------------------+\n");
    printf("| Press 'q' to exit                                                          |\n");
    printf("+----------------------------------------------------------------------------+\n");
    
    fflush(stdout);
}
