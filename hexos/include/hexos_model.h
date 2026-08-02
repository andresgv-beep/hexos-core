#ifndef HEXOS_MODEL_H
#define HEXOS_MODEL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define HEXOS_MODEL_MODALITY_COUNT 7
#define HEXOS_MODEL_ARCH_CAP 32
#define HEXOS_MODEL_ADAPTER_CAP 64
#define HEXOS_MODEL_ERROR_CAP 256

typedef enum {
    HEXOS_MODALITY_TEXT = 0,
    HEXOS_MODALITY_VISION,
    HEXOS_MODALITY_AUDIO,
    HEXOS_MODALITY_VIDEO,
    HEXOS_MODALITY_SPATIAL_3D,
    HEXOS_MODALITY_CODE,
    HEXOS_MODALITY_CORTEX,
} hexos_model_modality_t;

typedef enum {
    HEXOS_ADAPTER_ABSENT = 0,
    HEXOS_ADAPTER_DECLARED_ONLY,
    HEXOS_ADAPTER_METADATA_READY,
    HEXOS_ADAPTER_RUNTIME_READY,
} hexos_adapter_status_t;

typedef struct {
    bool declared;
    bool present;
    bool configured;
    char architecture[HEXOS_MODEL_ARCH_CAP];
    char adapter[HEXOS_MODEL_ADAPTER_CAP];
    hexos_adapter_status_t status;
} hexos_modality_capability_t;

typedef struct {
    bool valid;
    uint32_t schema_version;
    bool multimodal;
    char text_architecture[HEXOS_MODEL_ARCH_CAP];
    hexos_modality_capability_t modalities[HEXOS_MODEL_MODALITY_COUNT];
    unsigned diagnostic_count;
    char error[HEXOS_MODEL_ERROR_CAP];
} hexos_model_report_t;

const char *hexos_model_modality_name(hexos_model_modality_t modality);
const char *hexos_adapter_status_name(hexos_adapter_status_t status);

/* Parse the stable key/value protocol emitted by helios_model_probe --kv. */
bool hexos_model_parse_probe(const char *text, hexos_model_report_t *report);

/* Execute Hector's metadata-only probe without a shell or CUDA context. */
bool hexos_model_probe(const char *probe_binary, const char *model_path,
                       hexos_model_report_t *report);

#endif /* HEXOS_MODEL_H */
