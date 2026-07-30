/*
 * HEXOS - HELIOS Executive Operating System
 * Logging System
 */

#ifndef HEXOS_LOG_H
#define HEXOS_LOG_H

#include "hexos_types.h"

/* ============================================================================
 * ANSI COLORS
 * ============================================================================ */

#define ANSI_RESET       "\033[0m"
#define ANSI_BOLD        "\033[1m"
#define ANSI_DIM         "\033[2m"

#define ANSI_BLACK       "\033[30m"
#define ANSI_RED         "\033[31m"
#define ANSI_GREEN       "\033[32m"
#define ANSI_YELLOW      "\033[33m"
#define ANSI_BLUE        "\033[34m"
#define ANSI_MAGENTA     "\033[35m"
#define ANSI_CYAN        "\033[36m"
#define ANSI_WHITE       "\033[37m"

#define ANSI_BRIGHT_BLACK    "\033[90m"
#define ANSI_BRIGHT_RED      "\033[91m"
#define ANSI_BRIGHT_GREEN    "\033[92m"
#define ANSI_BRIGHT_YELLOW   "\033[93m"
#define ANSI_BRIGHT_BLUE     "\033[94m"
#define ANSI_BRIGHT_MAGENTA  "\033[95m"
#define ANSI_BRIGHT_CYAN     "\033[96m"
#define ANSI_BRIGHT_WHITE    "\033[97m"

#define ANSI_BG_RED      "\033[41m"
#define ANSI_BG_GREEN    "\033[42m"
#define ANSI_BG_YELLOW   "\033[43m"
#define ANSI_BG_BLUE     "\033[44m"
#define ANSI_BG_MAGENTA  "\033[45m"
#define ANSI_BG_CYAN     "\033[46m"
#define ANSI_BG_WHITE    "\033[47m"

/* ============================================================================
 * UI SYMBOLS - Unicode
 * ============================================================================ */

#define SYM_OK           "OK"
#define SYM_FAIL         "FAIL"
#define SYM_WARN         "WARN"
#define SYM_CRITICAL     "CRITICAL"
#define SYM_BULLET       "*"
#define SYM_BULLET_EMPTY "o"
#define SYM_ARROW        "->"
#define SYM_ARROW_UP     "^"
#define SYM_ARROW_DOWN   "v"

/* Box drawing - Unicode */
#define BOX_H            "─"
#define BOX_V            "│"
#define BOX_TL           "┌"
#define BOX_TR           "┐"
#define BOX_BL           "└"
#define BOX_BR           "┘"
#define BOX_VR           "├"
#define BOX_VL           "┤"
#define BOX_HD           "┬"
#define BOX_HU           "┴"
#define BOX_CROSS        "┼"

/* Double box - Unicode */
#define DBOX_H           "═"
#define DBOX_V           "║"
#define DBOX_TL          "╔"
#define DBOX_TR          "╗"
#define DBOX_BL          "╚"
#define DBOX_BR          "╝"

/* Progress bar - Unicode */
#define BAR_FULL         "█"
#define BAR_HALF         "▓"
#define BAR_EMPTY        "░"

/* Tree - Unicode */
#define TREE_V           "│"
#define TREE_VR          "├"
#define TREE_BRANCH      "├─"
#define TREE_LAST        "└─"

/* ============================================================================
 * API
 * ============================================================================ */

/* Initialize logging system */
void hexos_log_init(log_level_t min_level, bool use_colors);

/* Set minimum log level */
void hexos_log_set_level(log_level_t level);

/* Set quiet mode (suppress boot output for UI mode) */
void hexos_log_set_quiet(bool quiet);

/* Core logging functions */
void hexos_log(log_level_t level, const char *source, const char *fmt, ...);

/* Convenience macros */
#define LOG_TRACE(src, fmt, ...) hexos_log(LOG_TRACE, src, fmt, ##__VA_ARGS__)
#define LOG_DEBUG(src, fmt, ...) hexos_log(LOG_DEBUG, src, fmt, ##__VA_ARGS__)
#define LOG_INFO(src, fmt, ...)  hexos_log(LOG_INFO, src, fmt, ##__VA_ARGS__)
#define LOG_WARN(src, fmt, ...)  hexos_log(LOG_WARN, src, fmt, ##__VA_ARGS__)
#define LOG_ERROR(src, fmt, ...) hexos_log(LOG_ERROR, src, fmt, ##__VA_ARGS__)
#define LOG_FATAL(src, fmt, ...) hexos_log(LOG_FATAL, src, fmt, ##__VA_ARGS__)

/* ============================================================================
 * BOOT OUTPUT HELPERS
 * ============================================================================ */

/* Print phase header */
void hexos_print_phase(int phase, int total, const char *name);

/* Print phase complete with timing */
void hexos_print_phase_done(float seconds);

/* Print tree item */
void hexos_print_tree(int depth, bool is_last, const char *fmt, ...);

/* Print status line with dots */
void hexos_print_status(const char *label, bool ok, const char *value);

/* Print progress bar */
void hexos_print_bar(int width, float percent, const char *label);

/* Print colored percentage bar */
void hexos_print_pct_bar(int width, float percent);

/* Print horizontal separator */
void hexos_print_separator(int width, char c);

/* Print boxed text */
void hexos_print_box_start(int width);
void hexos_print_box_line(int width, const char *text);
void hexos_print_box_end(int width);

/* ============================================================================
 * BANNER
 * ============================================================================ */

/* Print HEXOS ASCII banner */
void hexos_print_banner(void);

/* Print HELIOS AWAKE banner */
void hexos_print_awake_banner(void);

#endif /* HEXOS_LOG_H */
