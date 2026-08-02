#include "hexos_model.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
    static const char fixture[] =
        "schema=helios.model-capabilities.v1\n"
        "schema_version=1\n"
        "text_architecture=gemma4\n"
        "multimodal=1\n"
        "modality.text.present=1\n"
        "modality.text.configured=1\n"
        "modality.text.architecture=gemma4\n"
        "modality.text.status=metadata_ready\n"
        "modality.vision.declared=1\n"
        "modality.vision.present=1\n"
        "modality.vision.configured=1\n"
        "modality.vision.architecture=gemma4\n"
        "modality.vision.adapter=helios.gemma4.vision.v1\n"
        "modality.vision.status=runtime_ready\n"
        "future.key=ignored\n"
        "diagnostic_count=0\n";

    hexos_model_report_t report;
    assert(hexos_model_parse_probe(fixture, &report));
    assert(report.valid && report.schema_version == 1 && report.multimodal);
    assert(!strcmp(report.text_architecture, "gemma4"));
    const hexos_modality_capability_t *vision =
        &report.modalities[HEXOS_MODALITY_VISION];
    assert(vision->present && vision->configured);
    assert(vision->status == HEXOS_ADAPTER_RUNTIME_READY);
    assert(!strcmp(vision->adapter, "helios.gemma4.vision.v1"));

    assert(!hexos_model_parse_probe("schema=wrong\nschema_version=1\n", &report));
    assert(strstr(report.error, "unsupported"));
    puts("PASS: HexOS model probe v1 parser");
    return 0;
}
