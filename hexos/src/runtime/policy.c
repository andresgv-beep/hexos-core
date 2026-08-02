#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include "hexos_runtime.h"

#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

/* Valores estables de CUdevice_attribute en la API pública del driver. */
#define HEXOS_CU_DEVICE_ATTRIBUTE_PAGEABLE_MEMORY_ACCESS    88
#define HEXOS_CU_DEVICE_ATTRIBUTE_CONCURRENT_MANAGED_ACCESS 89
#define HEXOS_CU_DEVICE_ATTRIBUTE_ASYNC_ENGINE_COUNT         40
#define HEXOS_CUDA_SUCCESS 0

typedef int hexos_cu_result_t;
typedef int hexos_cu_device_t;
typedef hexos_cu_result_t (*hexos_cu_init_fn)(unsigned int flags);
typedef hexos_cu_result_t (*hexos_cu_device_get_count_fn)(int *count);
typedef hexos_cu_result_t (*hexos_cu_device_get_fn)(hexos_cu_device_t *device,
                                                     int ordinal);
typedef hexos_cu_result_t (*hexos_cu_device_get_attribute_fn)(
    int *value, int attribute, hexos_cu_device_t device);

static bool parse_switch(const char *value, bool *enabled)
{
    if (!value || !*value || !strcasecmp(value, "auto")) return false;
    if (!strcmp(value, "1") || !strcasecmp(value, "true") ||
        !strcasecmp(value, "yes") || !strcasecmp(value, "on")) {
        *enabled = true;
        return true;
    }
    if (!strcmp(value, "0") || !strcasecmp(value, "false") ||
        !strcasecmp(value, "no") || !strcasecmp(value, "off")) {
        *enabled = false;
        return true;
    }
    return false;
}

bool hexos_runtime_probe_cuda(hexos_cuda_runtime_caps_t *caps)
{
    if (!caps) return false;
    memset(caps, 0, sizeof(*caps));
    caps->device_index = -1;

    void *driver = dlopen("libcuda.so.1", RTLD_NOW | RTLD_LOCAL);
    if (!driver) driver = dlopen("libcuda.so", RTLD_NOW | RTLD_LOCAL);
    if (!driver) return false;

    hexos_cu_init_fn cu_init =
        (hexos_cu_init_fn)dlsym(driver, "cuInit");
    hexos_cu_device_get_count_fn cu_device_get_count =
        (hexos_cu_device_get_count_fn)dlsym(driver, "cuDeviceGetCount");
    hexos_cu_device_get_fn cu_device_get =
        (hexos_cu_device_get_fn)dlsym(driver, "cuDeviceGet");
    hexos_cu_device_get_attribute_fn cu_device_get_attribute =
        (hexos_cu_device_get_attribute_fn)dlsym(driver, "cuDeviceGetAttribute");

    bool ok = false;
    if (!cu_init || !cu_device_get_count || !cu_device_get ||
        !cu_device_get_attribute) {
        goto done;
    }
    if (cu_init(0) != HEXOS_CUDA_SUCCESS) goto done;

    caps->driver_available = true;
    if (cu_device_get_count(&caps->device_count) != HEXOS_CUDA_SUCCESS ||
        caps->device_count < 1) {
        goto done;
    }

    hexos_cu_device_t device;
    if (cu_device_get(&device, 0) != HEXOS_CUDA_SUCCESS) goto done;
    caps->device_index = 0;

    int pageable = 0;
    int concurrent = 0;
    int async_engines = 0;
    if (cu_device_get_attribute(
            &pageable, HEXOS_CU_DEVICE_ATTRIBUTE_PAGEABLE_MEMORY_ACCESS,
            device) != HEXOS_CUDA_SUCCESS ||
        cu_device_get_attribute(
            &concurrent, HEXOS_CU_DEVICE_ATTRIBUTE_CONCURRENT_MANAGED_ACCESS,
            device) != HEXOS_CUDA_SUCCESS ||
        cu_device_get_attribute(
            &async_engines, HEXOS_CU_DEVICE_ATTRIBUTE_ASYNC_ENGINE_COUNT,
            device) != HEXOS_CUDA_SUCCESS) {
        goto done;
    }

    caps->pageable_memory_access = pageable != 0;
    caps->concurrent_managed_access = concurrent != 0;
    caps->async_engine_count = async_engines;
    ok = true;

done:
    dlclose(driver);
    return ok;
}

hexos_vision_mmap_policy_t hexos_runtime_decide_vision_mmap(
    const char *override_value,
    bool persistent_process,
    const hexos_cuda_runtime_caps_t *caps)
{
    bool forced = false;
    if (override_value && *override_value &&
        strcasecmp(override_value, "auto")) {
        if (!parse_switch(override_value, &forced)) {
            return HEXOS_VISION_MMAP_INVALID;
        }
        return forced ? HEXOS_VISION_MMAP_FORCED_ON
                      : HEXOS_VISION_MMAP_FORCED_OFF;
    }

    if (!persistent_process) return HEXOS_VISION_MMAP_AUTO_OFF_ONESHOT;
    if (!caps || !caps->driver_available || caps->device_count < 1 ||
        !caps->pageable_memory_access ||
        !caps->concurrent_managed_access) {
        return HEXOS_VISION_MMAP_AUTO_OFF_UNSUPPORTED;
    }
    return HEXOS_VISION_MMAP_AUTO_ON;
}

const char *hexos_runtime_vision_policy_name(hexos_vision_mmap_policy_t policy)
{
    switch (policy) {
        case HEXOS_VISION_MMAP_FORCED_OFF: return "forzado-off";
        case HEXOS_VISION_MMAP_FORCED_ON: return "forzado-on";
        case HEXOS_VISION_MMAP_AUTO_OFF_ONESHOT: return "auto-off-no-persistente";
        case HEXOS_VISION_MMAP_AUTO_OFF_UNSUPPORTED: return "auto-off-incompatible";
        case HEXOS_VISION_MMAP_AUTO_ON: return "auto-on";
        case HEXOS_VISION_MMAP_INVALID: break;
    }
    return "inválido";
}

bool hexos_runtime_apply_engine_env(
    bool persistent_process,
    hexos_runtime_report_t *report)
{
    hexos_runtime_report_t local;
    memset(&local, 0, sizeof(local));

    const char *embed_value = getenv("HELIOS_EMBED_MMAP");
    if (!embed_value || !*embed_value) {
        if (setenv("HELIOS_EMBED_MMAP", "1", 1) != 0) return false;
        local.embed_mmap = true;
    } else {
        bool enabled = false;
        local.embed_mmap = parse_switch(embed_value, &enabled) && enabled;
    }

    const char *vision_value = getenv("HELIOS_VISION_MMAP");
    const bool automatic = !vision_value || !*vision_value ||
                           !strcasecmp(vision_value, "auto");
    if (automatic) hexos_runtime_probe_cuda(&local.cuda);

    local.vision_policy = hexos_runtime_decide_vision_mmap(
        vision_value, persistent_process, &local.cuda);
    if (local.vision_policy == HEXOS_VISION_MMAP_INVALID) {
        snprintf(local.reason, sizeof(local.reason),
                 "HELIOS_VISION_MMAP='%s' no es 0, 1 ni auto",
                 vision_value ? vision_value : "");
        if (report) *report = local;
        return false;
    }

    local.vision_mmap =
        local.vision_policy == HEXOS_VISION_MMAP_FORCED_ON ||
        local.vision_policy == HEXOS_VISION_MMAP_AUTO_ON;
    if (setenv("HELIOS_VISION_MMAP", local.vision_mmap ? "1" : "0", 1) != 0) {
        return false;
    }

    if (automatic) {
        snprintf(local.reason, sizeof(local.reason),
                 "%s; CUDA=%s, dispositivo=%d, pageable=%d, concurrent=%d",
                 hexos_runtime_vision_policy_name(local.vision_policy),
                 local.cuda.driver_available ? "sí" : "no",
                 local.cuda.device_index,
                 local.cuda.pageable_memory_access ? 1 : 0,
                 local.cuda.concurrent_managed_access ? 1 : 0);
    } else {
        snprintf(local.reason, sizeof(local.reason), "%s por override",
                 hexos_runtime_vision_policy_name(local.vision_policy));
    }

    const char* double_value = getenv("HELIOS_MMAP_DOUBLE_BUFFER");
    const bool double_automatic = !double_value || !*double_value ||
                                  !strcasecmp(double_value, "auto");
    if (double_automatic && !automatic) {
        hexos_runtime_probe_cuda(&local.cuda);
    }
    bool double_forced = false;
    if (!double_automatic && !parse_switch(double_value, &double_forced)) {
        snprintf(local.double_buffer_reason,
                 sizeof(local.double_buffer_reason),
                 "HELIOS_MMAP_DOUBLE_BUFFER='%s' no es 0, 1 ni auto",
                 double_value);
        if (report) *report = local;
        return false;
    }
    local.mmap_double_buffer = double_automatic
        ? persistent_process && local.cuda.driver_available &&
          local.cuda.pageable_memory_access &&
          local.cuda.concurrent_managed_access &&
          local.cuda.async_engine_count > 0
        : double_forced;
    if (setenv("HELIOS_MMAP_DOUBLE_BUFFER",
               local.mmap_double_buffer ? "1" : "0", 1) != 0) {
        return false;
    }
    if (double_automatic) {
        snprintf(local.double_buffer_reason,
                 sizeof(local.double_buffer_reason),
                 "auto-%s; motores asíncronos=%d",
                 local.mmap_double_buffer ? "on" : "off",
                 local.cuda.async_engine_count);
    } else {
        snprintf(local.double_buffer_reason,
                 sizeof(local.double_buffer_reason),
                 "forzado-%s por override",
                 local.mmap_double_buffer ? "on" : "off");
    }

    if (report) *report = local;
    return true;
}
