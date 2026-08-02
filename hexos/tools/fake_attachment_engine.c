#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("tú>");

    char *line = NULL;
    size_t line_cap = 0;
    if (getline(&line, &line_cap, stdin) <= 0) return 1;
    if (!strcmp(line, "/fast\n")) {
        printf("(velocidad plena)\ntú>");
        if (getline(&line, &line_cap, stdin) <= 0) return 1;
    }
    unsigned width = 0, height = 0;
    size_t stride = 0, bytes = 0;
    if (sscanf(line, "/adjunto-rgb8 %u %u %zu %zu",
               &width, &height, &stride, &bytes) != 4 ||
        !width || !height || stride != (size_t)width * 3 ||
        bytes != stride * height) return 2;

    unsigned char *payload = malloc(bytes);
    if (!payload) return 3;
    if (fread(payload, 1, bytes, stdin) != bytes || fgetc(stdin) != '\n') {
        free(payload);
        return 4;
    }
    for (size_t i = 0; i < bytes; i++) {
        if (payload[i] != (unsigned char)(i & 0xff)) {
            free(payload);
            return 5;
        }
    }
    free(payload);
    printf("(imagen lista)\ntú>");

    if (getline(&line, &line_cap, stdin) <= 0 ||
        strcmp(line, "describe\n")) return 6;
    printf("helios>ok\ntú>");

    if (getline(&line, &line_cap, stdin) <= 0 ||
        strcmp(line, "/salir\n")) return 7;
    free(line);
    return 0;
}
