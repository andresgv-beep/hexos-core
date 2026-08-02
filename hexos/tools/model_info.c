#include "hexos_model.h"

#include <stdio.h>

int main(int argc, char **argv)
{
    if (argc != 2 && argc != 3) {
        fprintf(stderr, "uso: %s modelo.hnf [helios_model_probe]\n", argv[0]);
        return 2;
    }
    const char *probe = argc == 3 ? argv[2] : "helios_model_probe";
    hexos_model_report_t report;
    if (!hexos_model_probe(probe, argv[1], &report)) {
        fprintf(stderr, "hexos_model_info: %s\n", report.error);
        return 1;
    }

    printf("text=%s multimodal=%s\n", report.text_architecture,
           report.multimodal ? "yes" : "no");
    for (int i = 0; i < HEXOS_MODEL_MODALITY_COUNT; i++) {
        const hexos_modality_capability_t *cap = &report.modalities[i];
        if (!cap->declared && !cap->present) continue;
        printf("%s=%s", hexos_model_modality_name((hexos_model_modality_t)i),
               hexos_adapter_status_name(cap->status));
        if (cap->architecture[0]) printf(" arch=%s", cap->architecture);
        if (cap->adapter[0]) printf(" adapter=%s", cap->adapter);
        putchar('\n');
    }
    return 0;
}
