#include "hexos_runtime.h"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static hexos_cuda_runtime_caps_t supported_caps(void)
{
    hexos_cuda_runtime_caps_t caps;
    memset(&caps, 0, sizeof(caps));
    caps.driver_available = true;
    caps.device_count = 1;
    caps.device_index = 0;
    caps.pageable_memory_access = true;
    caps.concurrent_managed_access = true;
    caps.async_engine_count = 2;
    return caps;
}

int main(void)
{
    hexos_cuda_runtime_caps_t caps = supported_caps();

    assert(hexos_runtime_decide_vision_mmap(NULL, true, &caps) ==
           HEXOS_VISION_MMAP_AUTO_ON);
    assert(hexos_runtime_decide_vision_mmap("auto", true, &caps) ==
           HEXOS_VISION_MMAP_AUTO_ON);
    assert(hexos_runtime_decide_vision_mmap(NULL, false, &caps) ==
           HEXOS_VISION_MMAP_AUTO_OFF_ONESHOT);

    caps.pageable_memory_access = false;
    assert(hexos_runtime_decide_vision_mmap(NULL, true, &caps) ==
           HEXOS_VISION_MMAP_AUTO_OFF_UNSUPPORTED);
    assert(hexos_runtime_decide_vision_mmap("1", true, &caps) ==
           HEXOS_VISION_MMAP_FORCED_ON);
    assert(hexos_runtime_decide_vision_mmap("off", true, &caps) ==
           HEXOS_VISION_MMAP_FORCED_OFF);
    assert(hexos_runtime_decide_vision_mmap("basura", true, &caps) ==
           HEXOS_VISION_MMAP_INVALID);

    /* Los overrides explícitos se aplican sin consultar la GPU. */
    setenv("HELIOS_EMBED_MMAP", "0", 1);
    setenv("HELIOS_VISION_MMAP", "1", 1);
    setenv("HELIOS_MMAP_DOUBLE_BUFFER", "0", 1);
    hexos_runtime_report_t report;
    assert(hexos_runtime_apply_engine_env(true, &report));
    assert(!report.embed_mmap);
    assert(report.vision_mmap);
    assert(!report.mmap_double_buffer);
    assert(!strcmp(getenv("HELIOS_EMBED_MMAP"), "0"));
    assert(!strcmp(getenv("HELIOS_VISION_MMAP"), "1"));
    assert(!strcmp(getenv("HELIOS_MMAP_DOUBLE_BUFFER"), "0"));

    setenv("HELIOS_MMAP_DOUBLE_BUFFER", "valor-invalido", 1);
    assert(!hexos_runtime_apply_engine_env(true, &report));
    assert(strstr(report.double_buffer_reason, "no es 0, 1 ni auto"));

    puts("runtime_policy_test: OK");
    return 0;
}
