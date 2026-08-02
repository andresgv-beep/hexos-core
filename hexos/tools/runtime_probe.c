#include "hexos_runtime.h"

#include <stdio.h>
#include <string.h>

static void usage(const char *prog)
{
    fprintf(stderr,
            "uso: %s <vision-mmap|mmap-double-buffer> "
            "[persistent|oneshot]\n", prog);
}

int main(int argc, char **argv)
{
    if (argc < 2 || argc > 3 ||
        (strcmp(argv[1], "vision-mmap") &&
         strcmp(argv[1], "mmap-double-buffer"))) {
        usage(argv[0]);
        return 2;
    }

    bool persistent = true;
    if (argc == 3) {
        if (!strcmp(argv[2], "oneshot")) persistent = false;
        else if (strcmp(argv[2], "persistent")) {
            usage(argv[0]);
            return 2;
        }
    }

    hexos_runtime_report_t report;
    if (!hexos_runtime_apply_engine_env(persistent, &report)) {
        fprintf(stderr, "[hexos] política runtime inválida: %s\n",
                report.reason);
        return 1;
    }

    if (!strcmp(argv[1], "vision-mmap")) {
        fprintf(stderr, "[hexos] visión mmap: %s\n", report.reason);
        puts(report.vision_mmap ? "1" : "0");
    } else {
        fprintf(stderr, "[hexos] doble buffer mmap: %s\n",
                report.double_buffer_reason);
        puts(report.mmap_double_buffer ? "1" : "0");
    }
    return 0;
}
