/*
 * HEXOS - Política de lanzamiento del runtime HELIOS
 *
 * Mantiene fuera de Héctor las decisiones de producto que dependen del
 * hardware. La detección usa libcuda mediante dlopen: HEXOS continúa sin
 * depender del CUDA Toolkit ni crea un contexto CUDA.
 */

#ifndef HEXOS_RUNTIME_H
#define HEXOS_RUNTIME_H

#include <stdbool.h>

typedef struct {
    bool driver_available;
    int device_count;
    int device_index;
    bool pageable_memory_access;
    bool concurrent_managed_access;
} hexos_cuda_runtime_caps_t;

typedef enum {
    HEXOS_VISION_MMAP_INVALID = 0,
    HEXOS_VISION_MMAP_FORCED_OFF,
    HEXOS_VISION_MMAP_FORCED_ON,
    HEXOS_VISION_MMAP_AUTO_OFF_ONESHOT,
    HEXOS_VISION_MMAP_AUTO_OFF_UNSUPPORTED,
    HEXOS_VISION_MMAP_AUTO_ON
} hexos_vision_mmap_policy_t;

typedef struct {
    hexos_cuda_runtime_caps_t cuda;
    hexos_vision_mmap_policy_t vision_policy;
    bool embed_mmap;
    bool vision_mmap;
    char reason[192];
} hexos_runtime_report_t;

/* Consulta el dispositivo CUDA visible número cero. No crea contexto. */
bool hexos_runtime_probe_cuda(hexos_cuda_runtime_caps_t *caps);

/* Decisión pura, separada de getenv/setenv para poder probarla sin GPU. */
hexos_vision_mmap_policy_t hexos_runtime_decide_vision_mmap(
    const char *override_value,
    bool persistent_process,
    const hexos_cuda_runtime_caps_t *caps
);

/*
 * Aplica los defaults al entorno que heredará Héctor.
 *
 * - HELIOS_EMBED_MMAP: 1 si el usuario no lo ha definido.
 * - HELIOS_VISION_MMAP: auto según capacidades en procesos persistentes.
 *
 * Los valores explícitos 0/1 nunca se pisan. Devuelve false únicamente ante
 * un override inválido o si setenv falla.
 */
bool hexos_runtime_apply_engine_env(
    bool persistent_process,
    hexos_runtime_report_t *report
);

const char *hexos_runtime_vision_policy_name(hexos_vision_mmap_policy_t policy);

#endif /* HEXOS_RUNTIME_H */
