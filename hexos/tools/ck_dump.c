/* Volcador gemelo del CK portado — E2. Debe producir el MISMO fichero que
 * Hector-engine/tools/ck_dump.cpp sobre el mismo corpus. */
#include "hexos_ck.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Lector JSON de un solo nivel: el corpus es plano y lo genera nuestra propia
 * herramienta, así que no hace falta un parser completo — pero sí respetar
 * escapes, o un mensaje con comillas rompería el caso. */
static void unescape(const char *src, size_t n, char *out) {
    size_t o = 0;
    for (size_t i = 0; i < n; i++) {
        if (src[i] != '\\') { out[o++] = src[i]; continue; }
        if (++i >= n) break;
        switch (src[i]) {
            case 'n': out[o++] = '\n'; break;
            case 't': out[o++] = '\t'; break;
            case 'r': out[o++] = '\r'; break;
            case '"': out[o++] = '"';  break;
            case '\\': out[o++] = '\\'; break;
            case '/': out[o++] = '/'; break;
            default: out[o++] = src[i];
        }
    }
    out[o] = '\0';
}

static char *get_str(const char *line, const char *key) {
    char pat[64];
    snprintf(pat, sizeof(pat), "\"%s\"", key);
    const char *k = strstr(line, pat);
    if (!k) return strdup("");
    const char *c = strchr(k + strlen(pat), ':');
    if (!c) return strdup("");
    const char *q = strchr(c, '"');
    if (!q) return strdup("");
    const char *p = q + 1;
    const char *start = p;
    while (*p) {
        if (*p == '\\') { p += 2; continue; }
        if (*p == '"') break;
        p++;
    }
    size_t n = (size_t)(p - start);
    char *out = (char *)malloc(n + 1);
    unescape(start, n, out);
    return out;
}

static bool get_bool(const char *line, const char *key) {
    char pat[64];
    snprintf(pat, sizeof(pat), "\"%s\"", key);
    const char *k = strstr(line, pat);
    if (!k) return false;
    const char *c = strchr(k + strlen(pat), ':');
    if (!c) return false;
    while (*++c == ' ') {}
    return strncmp(c, "true", 4) == 0;
}

static void print_escaped(const char *s) {
    for (const unsigned char *p = (const unsigned char *)s; *p; p++) {
        switch (*p) {
            case '"':  fputs("\\\"", stdout); break;
            case '\\': fputs("\\\\", stdout); break;
            case '\n': fputs("\\n", stdout);  break;
            case '\t': fputs("\\t", stdout);  break;
            case '\r': fputs("\\r", stdout);  break;
            default:
                if (*p < 0x20) printf("\\u%04x", *p);
                else putchar(*p);
        }
    }
}

int main(void) {
    char *line = NULL;
    size_t cap = 0;
    ssize_t n;
    while ((n = getline(&line, &cap, stdin)) > 0) {
        if (n <= 1) continue;
        if (line[n - 1] == '\n') line[n - 1] = '\0';

        char *id  = get_str(line, "id");
        char *msg = get_str(line, "message");
        char *reg = get_str(line, "registro");
        char *rq  = get_str(line, "recall_query");
        char *cf  = get_str(line, "confirmed_facts");
        const bool triv = get_bool(line, "trivial");
        const bool art  = get_bool(line, "artifact_active");
        const bool adj  = get_bool(line, "has_attachment");

        ck_turn_frame_t f = ck_classify_turn(msg, triv, art, adj);

        ck_str_t recall; ck_str_init(&recall);
        if (rq[0]) ck_prepare_recall_context(rq, cf, &recall);
        const char *rc = recall.data ? recall.data : "";

        ck_str_t contrato; ck_str_init(&contrato);
        ck_response_contract(&f, reg, rc, &contrato);
        ck_str_t framed; ck_str_init(&framed);
        ck_frame_user_message(msg, &f, reg, rc, &framed);

        fputs("{\"id\":\"", stdout); print_escaped(id);
        printf("\",\"act\":\"%s\",\"artifact_active\":%s,\"has_attachment\":%s,"
               "\"trivial\":%s,\"visible_budget\":%d,\"thinking_budget\":%d,"
               "\"contract_needed\":%s,\"contract\":\"",
               ck_response_act_name(f.act),
               f.artifact_active ? "true" : "false",
               f.has_attachment ? "true" : "false",
               f.trivial ? "true" : "false",
               ck_visible_token_budget(&f),
               ck_thinking_token_budget(&f, strlen(msg)),
               ck_contract_needed(&f) ? "true" : "false");
        print_escaped(contrato.data ? contrato.data : "");
        fputs("\",\"social_steer\":\"", stdout); print_escaped(ck_social_steer(&f));
        fputs("\",\"framed_user\":\"", stdout); print_escaped(framed.data ? framed.data : "");
        fputs("\",\"recall_context\":\"", stdout); print_escaped(rc);
        fputs("\"}\n", stdout);

        ck_str_free(&recall); ck_str_free(&contrato); ck_str_free(&framed);
        free(id); free(msg); free(reg); free(rq); free(cf);
    }
    free(line);
    return 0;
}
