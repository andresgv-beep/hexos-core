/*
 * HEXOS - HELIOS Executive Operating System
 * Logging System Implementation
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <time.h>
#include "../include/hexos_log.h"

/* ============================================================================
 * STATIC STATE
 * ============================================================================ */

static log_level_t s_min_level = LOG_INFO;
static bool s_use_colors = false;  /* B&W mode by default */
static bool s_quiet_mode = false;  /* When true, suppress boot output (UI mode) */

/* ============================================================================
 * INIT
 * ============================================================================ */

void hexos_log_init(log_level_t min_level, bool use_colors) {
    s_min_level = min_level;
    s_use_colors = use_colors;
}

void hexos_log_set_level(log_level_t level) {
    s_min_level = level;
}

void hexos_log_set_quiet(bool quiet) {
    s_quiet_mode = quiet;
}

/* ============================================================================
 * CORE LOGGING
 * ============================================================================ */

static const char* level_to_str(log_level_t level) {
    switch (level) {
        case LOG_TRACE: return "TRACE";
        case LOG_DEBUG: return "DEBUG";
        case LOG_INFO:  return "INFO";
        case LOG_WARN:  return "WARN";
        case LOG_ERROR: return "ERROR";
        case LOG_FATAL: return "FATAL";
        default:        return "???";
    }
}

static const char* level_to_color(log_level_t level) {
    if (!s_use_colors) return "";
    switch (level) {
        case LOG_TRACE: return "";  /* No color */
        case LOG_DEBUG: return "";  /* No color */
        case LOG_INFO:  return "";  /* No color */
        case LOG_WARN:  return ANSI_YELLOW;
        case LOG_ERROR: return ANSI_RED;
        case LOG_FATAL: return ANSI_BRIGHT_RED;
        default:        return "";
    }
}

void hexos_log(log_level_t level, const char *source, const char *fmt, ...) {
    if (level < s_min_level) return;
    if (s_quiet_mode) return;  /* Suppress in UI mode */
    
    /* Get timestamp */
    time_t now = time(NULL);
    struct tm *tm_info = localtime(&now);
    char time_buf[32];
    strftime(time_buf, sizeof(time_buf), "%H:%M:%S", tm_info);
    
    /* Print log line - use stdout to maintain order with boot output */
    const char *color = level_to_color(level);
    const char *reset = s_use_colors ? ANSI_RESET : "";
    
    printf("[%s] %s%-5s%s [%s] ", 
            time_buf, color, level_to_str(level), reset, source);
    
    va_list args;
    va_start(args, fmt);
    vprintf(fmt, args);
    va_end(args);
    
    printf("\n");
    fflush(stdout);
}

/* ============================================================================
 * BOOT OUTPUT HELPERS
 * ============================================================================ */

void hexos_print_phase(int phase, int total, const char *name) {
    if (s_quiet_mode) return;
    printf("\n[PHASE %d/%d] %s\n", phase, total, name);
}

void hexos_print_phase_done(float seconds) {
    if (s_quiet_mode) return;
    printf("[%.1fs]\n", seconds);
}

void hexos_print_tree(int depth, bool is_last, const char *fmt, ...) {
    if (s_quiet_mode) return;
    
    /* Print indentation */
    for (int i = 0; i < depth - 1; i++) {
        printf("%s   ", TREE_V);
    }
    
    if (depth > 0) {
        printf("%s ", is_last ? TREE_LAST : TREE_BRANCH);
    }
    
    /* Print content */
    va_list args;
    va_start(args, fmt);
    vprintf(fmt, args);
    va_end(args);
    
    printf("\n");
}

void hexos_print_status(const char *label, bool ok, const char *value) {
    if (s_quiet_mode) return;
    
    /* States ALWAYS use colors: OK=green, FAIL=red */
    const char *green = ANSI_GREEN;
    const char *red = ANSI_RED;
    const char *reset = ANSI_RESET;
    
    int label_len = strlen(label);
    int dots = 40 - label_len;
    if (dots < 3) dots = 3;
    
    printf("  %s ", TREE_VR);
    printf("%s ", label);
    
    for (int i = 0; i < dots; i++) {
        printf(".");
    }
    
    if (ok) {
        printf(" %s%s%s", green, value ? value : "OK", reset);
    } else {
        printf(" %s%s%s", red, value ? value : "FAIL", reset);
    }
    
    printf("\n");
}

void hexos_print_bar(int width, float percent, const char *label) {
    if (s_quiet_mode) return;
    
    if (percent < 0) percent = 0;
    if (percent > 100) percent = 100;
    
    int filled = (int)(width * percent / 100.0f);
    
    printf("  %s", label ? label : "");
    
    for (int i = 0; i < width; i++) {
        if (i < filled) {
            printf("%s", BAR_FULL);
        } else {
            printf("%s", BAR_EMPTY);
        }
    }
    
    printf(" %.0f%%\n", percent);
}

void hexos_print_pct_bar(int width, float percent) {
    if (s_quiet_mode) return;
    
    if (percent < 0) percent = 0;
    if (percent > 100) percent = 100;
    
    int filled = (int)(width * percent / 100.0f);
    
    for (int i = 0; i < filled; i++) {
        printf("%s", BAR_FULL);
    }
    for (int i = filled; i < width; i++) {
        printf("%s", BAR_EMPTY);
    }
}

void hexos_print_separator(int width, char c) {
    if (s_quiet_mode) return;
    
    for (int i = 0; i < width; i++) {
        putchar(c);
    }
    printf("\n");
}

/* ============================================================================
 * BOX DRAWING
 * ============================================================================ */

/* Calculate visual width of UTF-8 string (approximate) */
static int visual_width(const char *text) {
    int width = 0;
    const unsigned char *p = (const unsigned char *)text;
    
    while (*p) {
        if (*p < 0x80) {
            /* ASCII */
            width++;
            p++;
        } else if ((*p & 0xE0) == 0xC0) {
            /* 2-byte UTF-8 */
            width++;
            p += 2;
        } else if ((*p & 0xF0) == 0xE0) {
            /* 3-byte UTF-8 (most box drawing, CJK) */
            width++;
            p += 3;
        } else if ((*p & 0xF8) == 0xF0) {
            /* 4-byte UTF-8 (emoji, etc) - often 2 cells wide */
            width += 2;
            p += 4;
        } else {
            /* Invalid or continuation byte, skip */
            p++;
        }
    }
    return width;
}

void hexos_print_box_start(int width) {
    if (s_quiet_mode) return;
    
    printf("%s", BOX_TL);
    for (int i = 0; i < width - 2; i++) printf("%s", BOX_H);
    printf("%s\n", BOX_TR);
}

void hexos_print_box_line(int width, const char *text) {
    if (s_quiet_mode) return;
    
    /* width includes the two border characters */
    int content_width = width - 4;  /* Space between borders minus padding */
    int text_width = visual_width(text);
    int padding = content_width - text_width;
    if (padding < 0) padding = 0;
    
    printf("%s ", BOX_V);
    printf("%s", text);
    for (int i = 0; i < padding; i++) printf(" ");
    printf(" %s\n", BOX_V);
}

void hexos_print_box_end(int width) {
    if (s_quiet_mode) return;
    
    printf("%s", BOX_BL);
    for (int i = 0; i < width - 2; i++) printf("%s", BOX_H);
    printf("%s\n", BOX_BR);
}

/* ============================================================================
 * BANNERS
 * ============================================================================ */

void hexos_print_banner(void) {
    if (s_quiet_mode) return;
    
    printf("%s", DBOX_TL);
    for (int i = 0; i < 74; i++) printf("%s", DBOX_H);
    printf("%s\n", DBOX_TR);
    
    printf("%s                                                                          %s\n", DBOX_V, DBOX_V);
    printf("%s    ██╗  ██╗███████╗██╗  ██╗ ██████╗ ███████╗                             %s\n", DBOX_V, DBOX_V);
    printf("%s    ██║  ██║██╔════╝╚██╗██╔╝██╔═══██╗██╔════╝                             %s\n", DBOX_V, DBOX_V);
    printf("%s    ███████║█████╗   ╚███╔╝ ██║   ██║███████╗                             %s\n", DBOX_V, DBOX_V);
    printf("%s    ██╔══██║██╔══╝   ██╔██╗ ██║   ██║╚════██║                             %s\n", DBOX_V, DBOX_V);
    printf("%s    ██║  ██║███████╗██╔╝ ██╗╚██████╔╝███████║                             %s\n", DBOX_V, DBOX_V);
    printf("%s    ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝                             %s\n", DBOX_V, DBOX_V);
    printf("%s                                                                          %s\n", DBOX_V, DBOX_V);
    printf("%s    HELIOS Executive Operating System                                     %s\n", DBOX_V, DBOX_V);
    printf("%s    \"El cuerpo que protege la mente\"                                      %s\n", DBOX_V, DBOX_V);
    printf("%s                                                                          %s\n", DBOX_V, DBOX_V);
    printf("%s    Build %d.%d.%d · HNFv%d · Profile BALANCED                              %s\n", 
           DBOX_V, HEXOS_VERSION_MAJOR, HEXOS_VERSION_MINOR, HEXOS_BUILD_NUMBER, HEXOS_HNF_VERSION, DBOX_V);
    printf("%s                                                                          %s\n", DBOX_V, DBOX_V);
    
    printf("%s", DBOX_BL);
    for (int i = 0; i < 74; i++) printf("%s", DBOX_H);
    printf("%s\n", DBOX_BR);
}

void hexos_print_awake_banner(void) {
    if (s_quiet_mode) return;
    
    printf("\n%s", DBOX_TL);
    for (int i = 0; i < 74; i++) printf("%s", DBOX_H);
    printf("%s\n", DBOX_TR);
    
    printf("%s                                                                          %s\n", DBOX_V, DBOX_V);
    printf("%s               ██   ██ ███████ ██      ██  ██████  ███████                %s\n", DBOX_V, DBOX_V);
    printf("%s               ██   ██ ██      ██      ██ ██    ██ ██                     %s\n", DBOX_V, DBOX_V);
    printf("%s               ███████ █████   ██      ██ ██    ██ ███████                %s\n", DBOX_V, DBOX_V);
    printf("%s               ██   ██ ██      ██      ██ ██    ██      ██                %s\n", DBOX_V, DBOX_V);
    printf("%s               ██   ██ ███████ ███████ ██  ██████  ███████                %s\n", DBOX_V, DBOX_V);
    printf("%s                                                                          %s\n", DBOX_V, DBOX_V);
    printf("%s                              A W A K E                                   %s\n", DBOX_V, DBOX_V);
    printf("%s                                                                          %s\n", DBOX_V, DBOX_V);
    
    printf("%s", DBOX_BL);
    for (int i = 0; i < 74; i++) printf("%s", DBOX_H);
    printf("%s\n", DBOX_BR);
}
