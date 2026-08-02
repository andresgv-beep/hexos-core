#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include "hexos_model.h"

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define PROBE_OUTPUT_CAP (32 * 1024)

static const char *const k_modality_names[HEXOS_MODEL_MODALITY_COUNT] = {
    "text", "vision", "audio", "video", "spatial_3d", "code", "cortex"
};

const char *hexos_model_modality_name(hexos_model_modality_t modality)
{
    if ((unsigned)modality >= HEXOS_MODEL_MODALITY_COUNT) return "unknown";
    return k_modality_names[modality];
}

const char *hexos_adapter_status_name(hexos_adapter_status_t status)
{
    switch (status) {
        case HEXOS_ADAPTER_ABSENT:         return "absent";
        case HEXOS_ADAPTER_DECLARED_ONLY:  return "declared_only";
        case HEXOS_ADAPTER_METADATA_READY: return "metadata_ready";
        case HEXOS_ADAPTER_RUNTIME_READY:  return "runtime_ready";
    }
    return "unknown";
}

static void reset_report(hexos_model_report_t *report)
{
    memset(report, 0, sizeof(*report));
    for (unsigned i = 0; i < HEXOS_MODEL_MODALITY_COUNT; i++) {
        report->modalities[i].status = HEXOS_ADAPTER_ABSENT;
    }
}

static void set_error(hexos_model_report_t *report, const char *message)
{
    snprintf(report->error, sizeof(report->error), "%s", message);
}

static int modality_index(const char *name, size_t len)
{
    for (unsigned i = 0; i < HEXOS_MODEL_MODALITY_COUNT; i++) {
        if (strlen(k_modality_names[i]) == len &&
            !memcmp(k_modality_names[i], name, len)) return (int)i;
    }
    return -1;
}

static bool parse_bool(const char *value, bool *out)
{
    if (!strcmp(value, "1")) { *out = true; return true; }
    if (!strcmp(value, "0")) { *out = false; return true; }
    return false;
}

static bool parse_status(const char *value, hexos_adapter_status_t *out)
{
    for (int i = HEXOS_ADAPTER_ABSENT; i <= HEXOS_ADAPTER_RUNTIME_READY; i++) {
        if (!strcmp(value, hexos_adapter_status_name((hexos_adapter_status_t)i))) {
            *out = (hexos_adapter_status_t)i;
            return true;
        }
    }
    return false;
}

static bool copy_value(char *dst, size_t cap, const char *value,
                       hexos_model_report_t *report)
{
    if (strlen(value) >= cap) {
        set_error(report, "model probe value exceeds the v1 contract");
        return false;
    }
    for (const unsigned char *p = (const unsigned char *)value; *p; p++) {
        if (!isalnum(*p) && *p != '_' && *p != '-' && *p != '.') {
            set_error(report, "model probe identifier contains invalid bytes");
            return false;
        }
    }
    memcpy(dst, value, strlen(value) + 1);
    return true;
}

bool hexos_model_parse_probe(const char *text, hexos_model_report_t *report)
{
    if (!text || !report) return false;
    reset_report(report);

    char *copy = strdup(text);
    if (!copy) {
        set_error(report, "out of memory parsing model probe");
        return false;
    }

    bool schema_seen = false;
    char *save = NULL;
    for (char *line = strtok_r(copy, "\n", &save); line;
         line = strtok_r(NULL, "\n", &save)) {
        size_t n = strlen(line);
        if (n && line[n - 1] == '\r') line[--n] = '\0';
        if (!n) continue;
        char *equal = strchr(line, '=');
        if (!equal) continue; /* forward-compatible unknown record */
        *equal = '\0';
        const char *key = line;
        const char *value = equal + 1;

        if (!strcmp(key, "schema")) {
            if (strcmp(value, "helios.model-capabilities.v1")) {
                set_error(report, "unsupported model probe schema");
                free(copy);
                return false;
            }
            schema_seen = true;
        } else if (!strcmp(key, "schema_version")) {
            char *end = NULL;
            unsigned long parsed = strtoul(value, &end, 10);
            if (!*value || (end && *end) || parsed != 1) {
                set_error(report, "unsupported model probe version");
                free(copy);
                return false;
            }
            report->schema_version = (uint32_t)parsed;
        } else if (!strcmp(key, "text_architecture")) {
            if (!copy_value(report->text_architecture,
                            sizeof(report->text_architecture), value, report)) {
                free(copy); return false;
            }
        } else if (!strcmp(key, "multimodal")) {
            if (!parse_bool(value, &report->multimodal)) {
                set_error(report, "invalid multimodal flag from model probe");
                free(copy); return false;
            }
        } else if (!strcmp(key, "diagnostic_count")) {
            char *end = NULL;
            unsigned long parsed = strtoul(value, &end, 10);
            if (!*value || (end && *end)) {
                set_error(report, "invalid diagnostic count from model probe");
                free(copy); return false;
            }
            report->diagnostic_count = (unsigned)parsed;
        } else if (!strncmp(key, "modality.", 9)) {
            const char *name = key + 9;
            const char *dot = strchr(name, '.');
            if (!dot) continue;
            const int index = modality_index(name, (size_t)(dot - name));
            if (index < 0) continue; /* a future modality is harmless to v1 */
            hexos_modality_capability_t *cap = &report->modalities[index];
            const char *field = dot + 1;
            bool ok = true;
            if (!strcmp(field, "declared")) ok = parse_bool(value, &cap->declared);
            else if (!strcmp(field, "present")) ok = parse_bool(value, &cap->present);
            else if (!strcmp(field, "configured")) ok = parse_bool(value, &cap->configured);
            else if (!strcmp(field, "architecture")) {
                ok = copy_value(cap->architecture, sizeof(cap->architecture),
                                value, report);
            } else if (!strcmp(field, "adapter")) {
                ok = copy_value(cap->adapter, sizeof(cap->adapter), value, report);
            } else if (!strcmp(field, "status")) {
                ok = parse_status(value, &cap->status);
            }
            if (!ok) {
                if (!report->error[0]) set_error(report, "invalid modality record");
                free(copy); return false;
            }
        }
    }
    free(copy);

    if (!schema_seen || report->schema_version != 1) {
        set_error(report, "incomplete model probe header");
        return false;
    }
    report->valid = true;
    return true;
}

bool hexos_model_probe(const char *probe_binary, const char *model_path,
                       hexos_model_report_t *report)
{
    if (!probe_binary || !model_path || !report) return false;
    reset_report(report);

    int output[2];
    if (pipe(output) != 0) {
        snprintf(report->error, sizeof(report->error), "probe pipe: %s",
                 strerror(errno));
        return false;
    }
    pid_t pid = fork();
    if (pid < 0) {
        close(output[0]); close(output[1]);
        snprintf(report->error, sizeof(report->error), "probe fork: %s",
                 strerror(errno));
        return false;
    }
    if (pid == 0) {
        dup2(output[1], STDOUT_FILENO);
        close(output[0]); close(output[1]);
        execlp(probe_binary, probe_binary, "--kv", model_path, (char *)NULL);
        _exit(127);
    }

    close(output[1]);
    char buffer[PROBE_OUTPUT_CAP];
    size_t used = 0;
    bool overflow = false;
    for (;;) {
        if (used == sizeof(buffer) - 1) { overflow = true; break; }
        ssize_t got = read(output[0], buffer + used, sizeof(buffer) - 1 - used);
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0) break;
        used += (size_t)got;
    }
    close(output[0]);
    buffer[used] = '\0';

    int status = 0;
    while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {}
    if (overflow) {
        set_error(report, "model probe output exceeds 32 KiB");
        return false;
    }
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        snprintf(report->error, sizeof(report->error),
                 "model probe exited with status %d",
                 WIFEXITED(status) ? WEXITSTATUS(status) : -1);
        return false;
    }
    return hexos_model_parse_probe(buffer, report);
}
