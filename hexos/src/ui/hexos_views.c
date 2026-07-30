/*
 * HEXOS Views
 * Panel-based views for the HEXOS UI
 * 
 * VIEW_BOOT - Boot sequence with live progress
 * VIEW_MAIN - Main status screen after boot
 */

#define _DEFAULT_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/stat.h>

#include "../include/hexos_ui.h"
#include "../include/hexos_views.h"
#include "../include/hexos_log.h"
#include "../include/hexos_types.h"
#include "../include/hexos_telemetry.h"
#include "../include/hexos.h"
#include "../include/hexos_ipc.h"

/* Definida en core/main.c — contexto IPC dueño del blackboard */
extern hexos_ipc_ctx_t* hexos_get_ipc(void);

/* HELIOS Cognitive Modules */
#include "../../../hnf_ext/include/hnf_ext.h"
#include "../../../memory_core/include/memory_core.h"

/* ============================================================================
 * BOOT STATE (shared with boot sequence)
 * ============================================================================ */

static boot_state_t s_boot = {0};

boot_state_t* hexos_boot_state(void) {
    return &s_boot;
}

/* ============================================================================
 * PANEL DEFINITIONS
 * ============================================================================ */

/* Boot screen panels - total width 80 */
static const ui_panel_t PANEL_HEADER = {0, 0, 80, 3, "HEXOS systems", false};
static const ui_panel_t PANEL_PIPELINE = {0, 3, 52, 10, "BOOT PIPELINE", false};
static const ui_panel_t PANEL_TELEMETRY = {52, 3, 28, 10, "LIVE TELEMETRY", false};
static const ui_panel_t PANEL_DETAILS = {0, 13, 80, 5, "DETAILS", false};

/* Main screen panels - adjusted widths */
static const ui_panel_t PANEL_MAIN_HEADER = {0, 0, 80, 3, "HEXOS systems", false};
static const ui_panel_t PANEL_STATUS = {0, 3, 45, 12, "SYSTEM STATUS", false};
static const ui_panel_t PANEL_MODULES = {45, 3, 35, 12, "MODULES", false};
static const ui_panel_t PANEL_CONTINUITY = {0, 15, 80, 6, "CONTINUITY", false};

/* ============================================================================
 * HELPER FUNCTIONS
 * ============================================================================ */

static const char* phase_status_str(phase_status_t status) {
    switch (status) {
        case PHASE_PENDING:  return "---";
        case PHASE_RUNNING:  return "RUN";
        case PHASE_OK:       return "OK";
        case PHASE_WARN:     return "WARN";
        case PHASE_FAIL:     return "FAIL";
        default:             return "???";
    }
}

static const char* phase_status_color(phase_status_t status) {
    switch (status) {
        case PHASE_PENDING:  return ANSI_BRIGHT_BLACK;
        case PHASE_RUNNING:  return ANSI_YELLOW;
        case PHASE_OK:       return ANSI_GREEN;
        case PHASE_WARN:     return ANSI_YELLOW;
        case PHASE_FAIL:     return ANSI_RED;
        default:             return ANSI_WHITE;
    }
}

static void format_uptime(uint64_t ms, char *buf, size_t len) {
    uint64_t secs = ms / 1000;
    uint64_t mins = secs / 60;
    uint64_t hours = mins / 60;
    
    secs %= 60;
    mins %= 60;
    
    if (hours > 0) {
        snprintf(buf, len, "%lu:%02lu:%02lu", 
                 (unsigned long)hours, (unsigned long)mins, (unsigned long)secs);
    } else {
        snprintf(buf, len, "%lu:%02lu", (unsigned long)mins, (unsigned long)secs);
    }
}

/* ============================================================================
 * VIEW_BOOT - Boot Sequence Screen
 * ============================================================================ */

static void draw_boot_header(void) {
    ui_panel_draw(&PANEL_HEADER);
    
    char session_short[9];
    strncpy(session_short, s_boot.session_id, 8);
    session_short[8] = '\0';
    
    /* Line 1: Build info (sin hostname) */
    ui_panel_print(&PANEL_HEADER, 1, 0, 
        "Build %d.%d.%d  HNFv%d  Profile %-10s  Session %s",
        s_boot.version_major, s_boot.version_minor, s_boot.build_number,
        s_boot.hnf_version, s_boot.profile, session_short);
}

static void draw_boot_pipeline(void) {
    ui_panel_draw(&PANEL_PIPELINE);
    
    /* Nombres cortos para que quepan */
    const char *phase_names[] = {
        "Hardware Detect",
        "HW Contract",
        "Module Attest",
        "Resource Alloc",
        "Runtime Init",
        "HELIOS Active"
    };
    
    for (int i = 0; i < 6; i++) {
        int y = i;
        phase_status_t status = s_boot.phases[i].status;
        float progress = s_boot.phases[i].progress;
        float time_s = s_boot.phases[i].time_ms / 1000.0f;
        
        /* Phase number and name (columna 1-18) */
        ui_panel_print(&PANEL_PIPELINE, 1, y, "%d %-15s", i + 1, phase_names[i]);
        
        /* Progress bar en columna fija 19 (8 chars) */
        int bar_x = PANEL_PIPELINE.x + 19;
        int bar_y = PANEL_PIPELINE.y + 1 + y;
        ui_goto(bar_x, bar_y);
        printf("[");
        
        int filled = (int)(8 * progress / 100.0f);
        for (int j = 0; j < 8; j++) {
            if (j < filled) {
                printf("%s", BAR_FULL);
            } else {
                printf("%s", BAR_EMPTY);
            }
        }
        printf("]");
        
        /* Status en columna 30 */
        const char *color = phase_status_color(status);
        const char *stat = phase_status_str(status);
        printf(" %s%-4s%s", color, stat, ANSI_RESET);
        
        /* Time en columna 36 */
        if (status == PHASE_OK || status == PHASE_WARN || status == PHASE_FAIL) {
            printf(" %4.1fs", time_s);
        }
    }
    
    /* Total time at bottom */
    if (s_boot.boot_complete) {
        ui_panel_print(&PANEL_PIPELINE, 1, 7, 
            "Total boot time: %.2fs", s_boot.total_time_ms / 1000.0f);
    }
}

static void draw_boot_telemetry(void) {
    ui_panel_draw(&PANEL_TELEMETRY);
    
    telemetry_snapshot_t snap;
    hexos_telemetry_get_snapshot(&snap);
    
    /* CPU & RAM - formato compacto */
    int cpu_pct = (int)snap.cpu_util_pct;
    ui_panel_print(&PANEL_TELEMETRY, 1, 0, "CPU %s%3d%%%s  RAM %u/%uG",
        cpu_pct > 80 ? ANSI_RED : ANSI_GREEN,
        cpu_pct, ANSI_RESET,
        snap.ram_used_mb / 1024, snap.ram_total_mb / 1024);
    
    /* GPU & VRAM */
    if (snap.gpu_healthy || snap.vram_total_mb > 0) {
        ui_panel_print(&PANEL_TELEMETRY, 1, 1, "GPU %s%3u%%%s  VRAM %u/%uG",
            snap.gpu_util_pct > 80 ? ANSI_RED : ANSI_GREEN,
            snap.gpu_util_pct, ANSI_RESET,
            snap.vram_used_mb / 1024, snap.vram_total_mb / 1024);
        
        /* Temp & Power */
        ui_panel_print(&PANEL_TELEMETRY, 1, 2, "Temp %s%3u°C%s  Pwr %3uW",
            snap.gpu_temp_c > 80 ? ANSI_RED : 
            snap.gpu_temp_c > 70 ? ANSI_YELLOW : ANSI_GREEN,
            snap.gpu_temp_c, ANSI_RESET, snap.gpu_power_w);
    } else {
        ui_panel_print(&PANEL_TELEMETRY, 1, 1, "GPU %s --%%%s  VRAM --/--G", 
            ANSI_BRIGHT_BLACK, ANSI_RESET);
        ui_panel_print(&PANEL_TELEMETRY, 1, 2, "Temp %s --°C%s  Pwr  --W",
            ANSI_BRIGHT_BLACK, ANSI_RESET);
    }
    
    /* Alerts */
    ui_panel_print(&PANEL_TELEMETRY, 1, 4, "Alerts:");
    if (s_boot.alert_count > 0) {
        printf(" %s%u %s%s", ANSI_YELLOW, s_boot.alert_count, 
               s_boot.alert_text, ANSI_RESET);
    } else {
        printf(" %sNone%s", ANSI_GREEN, ANSI_RESET);
    }
}

static void draw_boot_details(void) {
    ui_panel_draw(&PANEL_DETAILS);
    
    /* Line 1: Current status */
    ui_panel_print(&PANEL_DETAILS, 1, 0, "%s", s_boot.detail_line1);
    
    /* Line 2: Next action */
    ui_panel_print(&PANEL_DETAILS, 1, 1, "%s", s_boot.detail_line2);
}

void view_boot_draw(void) {
    draw_boot_header();
    draw_boot_pipeline();
    draw_boot_telemetry();
    draw_boot_details();
    
    /* Action bar */
    if (s_boot.boot_complete) {
        ui_action_bar("[Enter] Continue to HEXOS   [D] Dump diagnostics   [Q] Quit");
    } else {
        ui_action_bar("[F1] Help   [F2] Logs   [Esc] Safe mode   [Q] Abort boot");
    }
}

void view_boot_input(ui_key_t key) {
    switch (key) {
        case KEY_ENTER:
            /* Boot complete - let main loop handle transition */
            /* hexos_run will push VIEW_MAIN */
            break;
            
        case KEY_ESC:
            if (!s_boot.boot_complete) {
                /* TODO: Enter safe mode */
            }
            break;
            
        case KEY_F1:
            ui_dialog_message("HELP", "HEXOS Boot Sequence - Press Q to abort");
            break;
            
        case KEY_F2:
            /* TODO: Show logs */
            break;
            
        case 'q':
        case 'Q':
            s_boot.abort_requested = true;
            break;
            
        case 'd':
        case 'D':
            /* TODO: Dump diagnostics */
            break;
            
        default:
            break;
    }
}

/* ============================================================================
 * VIEW_MAIN - Main Status Screen
 * ============================================================================ */

static void draw_main_header(void) {
    ui_panel_draw(&PANEL_MAIN_HEADER);
    
    char uptime[32];
    format_uptime(s_boot.uptime_ms, uptime, sizeof(uptime));
    
    char session_short[9];
    strncpy(session_short, s_boot.session_id, 8);
    session_short[8] = '\0';
    
    ui_panel_print(&PANEL_MAIN_HEADER, 1, 0,
        "Build %d.%d.%d  Profile %-10s  Session %s  Uptime: %s",
        s_boot.version_major, s_boot.version_minor, s_boot.build_number,
        s_boot.profile, session_short, uptime);
}

static void draw_main_status(void) {
    ui_panel_draw(&PANEL_STATUS);
    
    telemetry_snapshot_t snap;
    hexos_telemetry_get_snapshot(&snap);
    
    bool gpu_present = snap.gpu_healthy || snap.vram_total_mb > 0;
    
    /* State */
    ui_panel_print(&PANEL_STATUS, 1, 0, "State:");
    ui_panel_print(&PANEL_STATUS, 12, 0, "%sRUNNING%s", ANSI_GREEN, ANSI_RESET);
    
    /* GPU - truncate name to fit */
    ui_panel_print(&PANEL_STATUS, 1, 2, "GPU:");
    if (gpu_present) {
        char gpu_short[28];
        strncpy(gpu_short, s_boot.gpu_name, 27);
        gpu_short[27] = '\0';
        ui_panel_print(&PANEL_STATUS, 12, 2, "%s", gpu_short);
    } else {
        ui_panel_print(&PANEL_STATUS, 12, 2, "%sNot detected%s", ANSI_YELLOW, ANSI_RESET);
    }
    
    /* VRAM bar - compact format */
    float vram_pct = snap.vram_total_mb > 0 ? 
        (float)snap.vram_used_mb * 100 / snap.vram_total_mb : 0;
    ui_panel_print(&PANEL_STATUS, 1, 4, "VRAM:");
    ui_goto(PANEL_STATUS.x + 8, PANEL_STATUS.y + 5);
    ui_progress_bar(PANEL_STATUS.x + 8, PANEL_STATUS.y + 5, 18, vram_pct);
    printf(" %.1f/%.1fG", snap.vram_used_mb/1024.0f, snap.vram_total_mb/1024.0f);
    
    /* RAM bar - compact format */
    float ram_pct = snap.ram_total_mb > 0 ?
        (float)snap.ram_used_mb * 100 / snap.ram_total_mb : 0;
    ui_panel_print(&PANEL_STATUS, 1, 6, "RAM:");
    ui_goto(PANEL_STATUS.x + 8, PANEL_STATUS.y + 7);
    ui_progress_bar(PANEL_STATUS.x + 8, PANEL_STATUS.y + 7, 18, ram_pct);
    printf(" %.1f/%.1fG", snap.ram_used_mb/1024.0f, snap.ram_total_mb/1024.0f);
    
    /* Temp */
    ui_panel_print(&PANEL_STATUS, 1, 8, "Temp:");
    if (gpu_present) {
        ui_panel_print(&PANEL_STATUS, 12, 8, "%s%u°C%s", 
            snap.gpu_temp_c > 80 ? ANSI_RED : ANSI_GREEN,
            snap.gpu_temp_c, ANSI_RESET);
    } else {
        ui_panel_print(&PANEL_STATUS, 12, 8, "--");
    }
}

static void draw_main_modules(void) {
    ui_panel_draw(&PANEL_MODULES);
    
    /* Module status - column 18 for status */
    ui_panel_print(&PANEL_MODULES, 1, 0, "HEXOS");
    ui_panel_print(&PANEL_MODULES, 18, 0, "[%sONLINE%s]", ANSI_GREEN, ANSI_RESET);
    
    ui_panel_print(&PANEL_MODULES, 1, 1, "Memory Core");
    ui_panel_print(&PANEL_MODULES, 18, 1, "[%sONLINE%s]", ANSI_GREEN, ANSI_RESET);
    
    ui_panel_print(&PANEL_MODULES, 1, 2, "HNF-EXT");
    if (s_boot.hnf_ext_found) {
        ui_panel_print(&PANEL_MODULES, 18, 2, "[%sLOADED%s]", ANSI_GREEN, ANSI_RESET);
    } else {
        ui_panel_print(&PANEL_MODULES, 15, 2, "[%sNOT FOUND%s]", ANSI_YELLOW, ANSI_RESET);
    }
    
    ui_panel_print(&PANEL_MODULES, 1, 3, "HERA");
    ui_panel_print(&PANEL_MODULES, 18, 3, "[%sACTIVE%s]", ANSI_GREEN, ANSI_RESET);
    
    ui_panel_print(&PANEL_MODULES, 1, 4, "Cogn. Kernel");
    ui_panel_print(&PANEL_MODULES, 20, 4, "[%sSTUB%s]", ANSI_BRIGHT_BLACK, ANSI_RESET);
    
    /* CUDA Engine (Héctor): estado real desde el blackboard IPC.
     * El motor externo marca su bit en modules_connected y publica
     * tokens_per_sec en cognitive.* — aquí solo se lee. */
    ui_panel_print(&PANEL_MODULES, 1, 5, "CUDA Engine");
    {
        hexos_ipc_ctx_t *ipc = hexos_get_ipc();
        bool engine_online = false;
        float tps = 0.0f;
        uint64_t total_tok = 0;
        bool generating = false;

        if (ipc && ipc->state) {
            engine_online = (ipc->state->modules_connected &
                             (1u << HEXOS_MODULE_INFERENCE)) != 0;
            tps = ipc->state->cognitive.tokens_per_sec;
            total_tok = ipc->state->cognitive.total_tokens;
            generating = ipc->state->cognitive.running != 0;
        }

        if (engine_online && generating) {
            ui_panel_print(&PANEL_MODULES, 15, 5, "[%sONLINE%s] %.1f tok/s",
                           ANSI_GREEN, ANSI_RESET, tps);
        } else if (engine_online) {
            ui_panel_print(&PANEL_MODULES, 15, 5, "[%sIDLE%s] %lu tokens",
                           ANSI_CYAN, ANSI_RESET, (unsigned long)total_tok);
        } else {
            ui_panel_print(&PANEL_MODULES, 15, 5, "[%sOFFLINE%s]",
                           ANSI_BRIGHT_BLACK, ANSI_RESET);
        }
    }
    
    /* IPC status - shortened */
    ui_panel_print(&PANEL_MODULES, 1, 7, "IPC: %s/dev/shm%s", ANSI_CYAN, ANSI_RESET);
}

static void draw_main_continuity(void) {
    ui_panel_draw(&PANEL_CONTINUITY);
    
    if (s_boot.continuity_message[0]) {
        /* Word wrap the message - max 72 chars per line */
        char msg_copy[256];
        strncpy(msg_copy, s_boot.continuity_message, 255);
        msg_copy[255] = '\0';
        
        char *line = msg_copy;
        int y = 0;
        while (*line && y < 3) {
            /* Print up to 72 chars */
            char tmp[74];
            strncpy(tmp, line, 72);
            tmp[72] = '\0';
            ui_panel_print(&PANEL_CONTINUITY, 1, y, "%s", tmp);
            
            line += strlen(line) > 72 ? 72 : strlen(line);
            y++;
        }
    } else {
        ui_panel_print(&PANEL_CONTINUITY, 1, 0, 
            "Initializing... awaiting Memory Core connection.");
    }
    
    ui_panel_print(&PANEL_CONTINUITY, 60, 3, "-- HELIOS");
}

void view_main_draw(void) {
    /* Update uptime */
    s_boot.uptime_ms = hexos_time_ms() - s_boot.boot_start_ms;
    
    draw_main_header();
    draw_main_status();
    draw_main_modules();
    draw_main_continuity();
    
    ui_action_bar("[H]Help  [I]Identity  [M]Memory  [G]GPU  [L]Logs  [A]Advanced  [Q]Quit");
}

void view_main_input(ui_key_t key) {
    switch (key) {
        case 'h':
        case 'H':
        case KEY_F1:
            ui_dialog_message("HEXOS HELP",
                "I=Identity  M=Memory  G=GPU  L=Logs  A=Advanced  Q=Quit");
            break;
            
        case 'i':
        case 'I':
            ui_view_push(VIEW_IDENTITY);
            break;
            
        case 'm':
        case 'M':
            ui_view_push(VIEW_MEMORY);
            break;
            
        case 'g':
        case 'G':
            ui_view_push(VIEW_GPU);
            break;
            
        case 'l':
        case 'L':
            ui_view_push(VIEW_LOGS);
            break;
            
        case 'a':
        case 'A':
            ui_view_push(VIEW_ADVANCED);
            break;
            
        case 'q':
        case 'Q':
            s_boot.quit_requested = true;
            break;
            
        default:
            break;
    }
}

/* ============================================================================
 * VIEW_IDENTITY - HNF-EXT Identity Display (Read-Only)
 * 
 * La identidad de Helios es fija por ahora. Evolucionará cuando HERA
 * analice las interacciones y proponga cambios.
 * ============================================================================ */

static const ui_panel_t PANEL_ID_HEADER = {0, 0, 80, 3, "IDENTITY", false};
static const ui_panel_t PANEL_ID_CORE = {0, 3, 80, 10, "CORE IDENTITY", false};
static const ui_panel_t PANEL_ID_TRAITS = {0, 13, 40, 8, "TRAITS", false};
static const ui_panel_t PANEL_ID_VALUES = {40, 13, 40, 8, "VALUES", false};

/* Ensure identity exists - create with defaults if not */
static void ensure_identity_exists(void) {
    const char *hnf_path = "runtime/hnf/helios.hnf";
    
    if (!hnf_ext_is_initialized()) {
        hnf_ext_init();
    }
    
    /* Try to load existing */
    if (hnf_ext_load(hnf_path) == HNF_OK) {
        return;  /* Already exists */
    }
    
    /* Create directory if needed */
    mkdir("runtime", 0755);
    mkdir("runtime/hnf", 0755);
    
    /* Create with defaults - Helios identity is fixed */
    if (hnf_ext_create(hnf_path, "Helios") == HNF_OK) {
        hnf_ext_save();
        hexos_log_to_ring("[HNF] Identity created: Helios");
    }
}

void view_identity_draw(void) {
    const char *hnf_path = "runtime/hnf/helios.hnf";
    
    /* Header */
    ui_panel_draw(&PANEL_ID_HEADER);
    ui_panel_print(&PANEL_ID_HEADER, 1, 0, 
        "HELIOS Identity (HNF-EXT v1.0)    [Esc] Back");
    
    ui_panel_draw(&PANEL_ID_CORE);
    
    /* Ensure identity exists */
    ensure_identity_exists();
    
    /* Load for display */
    if (hnf_ext_load(hnf_path) != HNF_OK) {
        ui_panel_print(&PANEL_ID_CORE, 1, 1, "%sError loading identity%s", 
            ANSI_RED, ANSI_RESET);
        ui_panel_draw(&PANEL_ID_TRAITS);
        ui_panel_draw(&PANEL_ID_VALUES);
        ui_action_bar("[Esc] Back");
        return;
    }
    
    /* Get stats */
    hnf_ext_stats_t stats;
    hnf_ext_get_stats(&stats);
    
    /* Get identity info */
    const char *name = hnf_ext_get_name();
    const char *purpose = hnf_ext_get_purpose();
    
    /* Core info */
    ui_panel_print(&PANEL_ID_CORE, 1, 0, "Name:");
    ui_panel_print(&PANEL_ID_CORE, 15, 0, "%s%s%s", 
        ANSI_CYAN, name ? name : "Helios", ANSI_RESET);
    
    ui_panel_print(&PANEL_ID_CORE, 1, 1, "Status:");
    ui_panel_print(&PANEL_ID_CORE, 15, 1, "%sActive%s", ANSI_GREEN, ANSI_RESET);
    
    ui_panel_print(&PANEL_ID_CORE, 1, 2, "Evolution:");
    ui_panel_print(&PANEL_ID_CORE, 15, 2, "Managed by HERA (when active)");
    
    ui_panel_print(&PANEL_ID_CORE, 1, 4, "Purpose:");
    if (purpose && purpose[0]) {
        /* Truncate purpose to fit */
        char purpose_line[60];
        strncpy(purpose_line, purpose, 59);
        purpose_line[59] = '\0';
        ui_panel_print(&PANEL_ID_CORE, 1, 5, "  %s", purpose_line);
        if (strlen(purpose) > 59) {
            strncpy(purpose_line, purpose + 59, 59);
            purpose_line[59] = '\0';
            ui_panel_print(&PANEL_ID_CORE, 1, 6, "  %s", purpose_line);
        }
    }
    
    ui_panel_print(&PANEL_ID_CORE, 1, 8, "Memories:");
    ui_panel_print(&PANEL_ID_CORE, 15, 8, "%u strong memories stored",
        stats.memory_count);
    
    /* Traits panel */
    ui_panel_draw(&PANEL_ID_TRAITS);
    
    hnf_trait_t traits[HNF_EXT_MAX_TRAITS];
    uint8_t trait_count = 0;
    if (hnf_ext_get_traits(traits, HNF_EXT_MAX_TRAITS, &trait_count) == HNF_OK && trait_count > 0) {
        for (uint8_t i = 0; i < trait_count && i < 6; i++) {
            /* Draw trait with bar */
            int bar_len = (int)(traits[i].strength * 12);
            char bar[16];
            for (int j = 0; j < 12; j++) {
                bar[j] = j < bar_len ? '#' : '-';
            }
            bar[12] = '\0';
            ui_panel_print(&PANEL_ID_TRAITS, 1, i, "%-10.10s [%s] %2d%%", 
                traits[i].name.data, bar, (int)(traits[i].strength * 100));
        }
    } else {
        ui_panel_print(&PANEL_ID_TRAITS, 1, 1, "(default traits)");
    }
    
    /* Values panel */
    ui_panel_draw(&PANEL_ID_VALUES);
    
    hnf_value_t values[HNF_EXT_MAX_VALUES];
    uint8_t value_count = 0;
    if (hnf_ext_get_values(values, HNF_EXT_MAX_VALUES, &value_count) == HNF_OK && value_count > 0) {
        for (uint8_t i = 0; i < value_count && i < 6; i++) {
            ui_panel_print(&PANEL_ID_VALUES, 1, i, "%u. %-28.28s", 
                values[i].priority, values[i].name.data);
        }
    } else {
        ui_panel_print(&PANEL_ID_VALUES, 1, 1, "(default values)");
    }
    
    ui_action_bar("[Esc] Back   [R] Reload   [J] Export JSON");
}

void view_identity_input(ui_key_t key) {
    switch (key) {
        case KEY_ESC:
            ui_view_pop();
            break;
        case 'r':
        case 'R':
            ui_view_redraw();
            break;
        case 'j':
        case 'J':
            /* Export to JSON for inspection */
            if (hnf_ext_is_initialized()) {
                if (hnf_ext_export_json("runtime/hnf/helios_export.json") == HNF_OK) {
                    hexos_log_to_ring("[HNF] Exported to runtime/hnf/helios_export.json");
                    ui_dialog_message("EXPORTED", "Identity exported to JSON");
                }
            }
            break;
        default:
            break;
    }
}

/* ============================================================================
 * VIEW_MEMORY - Episodic Memory Status
 * ============================================================================ */

static const ui_panel_t PANEL_MEM_HEADER = {0, 0, 80, 3, "MEMORY", false};
static const ui_panel_t PANEL_MEM_STATUS = {0, 3, 40, 10, "MEMORY CORE STATUS", false};
static const ui_panel_t PANEL_MEM_RECENT = {40, 3, 40, 10, "RECENT EVENTS", false};
static const ui_panel_t PANEL_MEM_STATS = {0, 13, 80, 8, "STATISTICS", false};

void view_memory_draw(void) {
    ui_panel_draw(&PANEL_MEM_HEADER);
    ui_panel_print(&PANEL_MEM_HEADER, 1, 0,
        "Episodic Memory (Memory Core v3.0)    [Esc] Back");
    
    ui_panel_draw(&PANEL_MEM_STATUS);
    
    /* Initialize Memory Core if needed */
    if (!mc_is_initialized()) {
        mc_config_t cfg = {0};
        strncpy(cfg.base_path, "runtime", sizeof(cfg.base_path) - 1);
        strncpy(cfg.memory_path, "runtime/memory", sizeof(cfg.memory_path) - 1);
        cfg.ram_active_limit_mb = 200;
        cfg.daily_episodic_limit = 10000;
        cfg.max_query_results = 100;
        cfg.embedding_dimension = 384;
        cfg.auto_archive = true;
        mc_init(&cfg);
    }
    
    if (!mc_is_initialized()) {
        ui_panel_print(&PANEL_MEM_STATUS, 1, 1, "Status: %sOFFLINE%s",
            ANSI_RED, ANSI_RESET);
        ui_panel_print(&PANEL_MEM_STATUS, 1, 3, "Memory Core init failed");
        
        ui_panel_draw(&PANEL_MEM_RECENT);
        ui_panel_print(&PANEL_MEM_RECENT, 1, 1, "(unavailable)");
        
        ui_panel_draw(&PANEL_MEM_STATS);
        ui_panel_print(&PANEL_MEM_STATS, 1, 1, "(unavailable)");
        
        ui_action_bar("[Esc] Back   [R] Retry Init");
        return;
    }
    
    /* Get stats */
    mc_stats_t stats;
    mc_get_stats(&stats);
    
    /* Status panel */
    ui_panel_print(&PANEL_MEM_STATUS, 1, 0, "Status:");
    ui_panel_print(&PANEL_MEM_STATUS, 14, 0, "%sONLINE%s", ANSI_GREEN, ANSI_RESET);
    
    ui_panel_print(&PANEL_MEM_STATUS, 1, 2, "Active Items:");
    ui_panel_print(&PANEL_MEM_STATUS, 14, 2, "%lu", (unsigned long)stats.active_items);
    
    ui_panel_print(&PANEL_MEM_STATUS, 1, 3, "RAM Used:");
    ui_panel_print(&PANEL_MEM_STATUS, 14, 3, "%lu / %lu MB", 
        (unsigned long)stats.active_size_mb, (unsigned long)stats.active_limit_mb);
    
    ui_panel_print(&PANEL_MEM_STATUS, 1, 5, "Pressure:");
    const char *pressure_str[] = {"LOW", "MEDIUM", "HIGH", "CRITICAL"};
    const char *pressure_color[] = {ANSI_GREEN, ANSI_YELLOW, ANSI_RED, ANSI_RED};
    ui_panel_print(&PANEL_MEM_STATUS, 14, 5, "%s%s%s", 
        pressure_color[stats.pressure_level], 
        pressure_str[stats.pressure_level], 
        ANSI_RESET);
    
    ui_panel_print(&PANEL_MEM_STATUS, 1, 7, "Candidates:");
    ui_panel_print(&PANEL_MEM_STATUS, 14, 7, "%u pending", stats.candidates_pending);
    
    /* Recent events panel */
    ui_panel_draw(&PANEL_MEM_RECENT);
    
    mc_episodic_event_t events[5];
    uint32_t event_count = 0;
    mc_get_recent_episodic(5, events, &event_count);
    
    if (event_count == 0) {
        ui_panel_print(&PANEL_MEM_RECENT, 1, 1, "(no recent events)");
        ui_panel_print(&PANEL_MEM_RECENT, 1, 3, "Events will appear here");
        ui_panel_print(&PANEL_MEM_RECENT, 1, 4, "as HELIOS converses.");
    } else {
        for (uint32_t i = 0; i < event_count && i < 5; i++) {
            char time_str[16];
            mc_format_timestamp(events[i].timestamp, time_str, sizeof(time_str));
            
            /* Truncate text to fit */
            char text_short[26];
            strncpy(text_short, events[i].text, 25);
            text_short[25] = '\0';
            if (strlen(events[i].text) > 25) {
                text_short[22] = '.';
                text_short[23] = '.';
                text_short[24] = '.';
            }
            
            ui_panel_print(&PANEL_MEM_RECENT, 1, i, "%.5s %s", 
                time_str + 11, text_short);  /* Show HH:MM + text */
        }
    }
    
    /* Statistics panel */
    ui_panel_draw(&PANEL_MEM_STATS);
    
    ui_panel_print(&PANEL_MEM_STATS, 1, 0, "Archived Days: %u", stats.archived_days);
    ui_panel_print(&PANEL_MEM_STATS, 30, 0, "Archived Items: %lu", 
        (unsigned long)stats.archived_items);
    
    ui_panel_print(&PANEL_MEM_STATS, 1, 1, "Archive Size: %lu MB", 
        (unsigned long)stats.archived_size_mb);
    ui_panel_print(&PANEL_MEM_STATS, 30, 1, "Index Items: %lu", 
        (unsigned long)stats.index_items);
    
    ui_panel_print(&PANEL_MEM_STATS, 1, 3, "Avg Query Time: %.1f ms", stats.avg_query_ms);
    
    /* Last archive time */
    if (stats.last_archive > 0) {
        char time_str[32];
        mc_format_timestamp(stats.last_archive, time_str, sizeof(time_str));
        ui_panel_print(&PANEL_MEM_STATS, 1, 4, "Last Archive: %s", time_str);
    } else {
        ui_panel_print(&PANEL_MEM_STATS, 1, 4, "Last Archive: Never");
    }
    
    ui_action_bar("[Esc] Back   [A] Archive   [C] Compact   [V] Verify   [R] Refresh");
}

void view_memory_input(ui_key_t key) {
    switch (key) {
        case KEY_ESC:
            ui_view_pop();
            break;
        case 'r':
        case 'R':
            ui_view_redraw();
            break;
        case 'a':
        case 'A':
            /* Archive current day */
            if (mc_is_initialized()) {
                if (mc_archive_day() == MC_OK) {
                    ui_dialog_message("ARCHIVE", "Day archived successfully");
                } else {
                    ui_dialog_message("ERROR", "Archive failed");
                }
            }
            break;
        case 'c':
        case 'C':
            /* Compact/degrade old memories */
            if (mc_is_initialized()) {
                uint32_t degraded = 0;
                if (mc_degrade(50, &degraded) == MC_OK) {
                    char msg[64];
                    snprintf(msg, sizeof(msg), "Compacted %u items", degraded);
                    ui_dialog_message("COMPACT", msg);
                } else {
                    ui_dialog_message("ERROR", "Compact failed");
                }
            }
            break;
        case 'v':
        case 'V':
            /* Verify integrity */
            if (mc_is_initialized()) {
                uint32_t errors = 0;
                mc_verify_integrity(true, &errors);
                char msg[64];
                snprintf(msg, sizeof(msg), "Verified. Errors found: %u", errors);
                ui_dialog_message("VERIFY", msg);
            }
            break;
        default:
            break;
    }
}

/* ============================================================================
 * VIEW_GPU - GPU Information
 * ============================================================================ */

static const ui_panel_t PANEL_GPU_HEADER = {0, 0, 80, 3, "GPU", false};
static const ui_panel_t PANEL_GPU_INFO = {0, 3, 40, 12, "DEVICE INFO", false};
static const ui_panel_t PANEL_GPU_METRICS = {40, 3, 40, 12, "LIVE METRICS", false};
static const ui_panel_t PANEL_GPU_VRAM = {0, 15, 80, 6, "VRAM ALLOCATION", false};

void view_gpu_draw(void) {
    ui_panel_draw(&PANEL_GPU_HEADER);
    ui_panel_print(&PANEL_GPU_HEADER, 1, 0,
        "GPU Monitor    [Esc] Back");
    
    ui_panel_draw(&PANEL_GPU_INFO);
    
    telemetry_snapshot_t snap;
    hexos_telemetry_get_snapshot(&snap);
    
    bool gpu_present = snap.gpu_healthy || snap.vram_total_mb > 0;
    
    if (!gpu_present) {
        ui_panel_print(&PANEL_GPU_INFO, 1, 1, "%sNo GPU detected%s",
            ANSI_YELLOW, ANSI_RESET);
        ui_panel_print(&PANEL_GPU_INFO, 1, 3, "HEXOS requires NVIDIA GPU");
        ui_panel_print(&PANEL_GPU_INFO, 1, 4, "with CUDA support");
    } else {
        ui_panel_print(&PANEL_GPU_INFO, 1, 0, "Name:");
        ui_panel_print(&PANEL_GPU_INFO, 12, 0, "%s", s_boot.gpu_name);
        
        ui_panel_print(&PANEL_GPU_INFO, 1, 2, "Driver:");
        ui_panel_print(&PANEL_GPU_INFO, 12, 2, "NVIDIA (via NVML)");
        
        ui_panel_print(&PANEL_GPU_INFO, 1, 4, "VRAM Total:");
        ui_panel_print(&PANEL_GPU_INFO, 12, 4, "%u MB", snap.vram_total_mb);
        
        ui_panel_print(&PANEL_GPU_INFO, 1, 5, "VRAM Used:");
        ui_panel_print(&PANEL_GPU_INFO, 12, 5, "%u MB", snap.vram_used_mb);
        
        ui_panel_print(&PANEL_GPU_INFO, 1, 6, "VRAM Free:");
        ui_panel_print(&PANEL_GPU_INFO, 12, 6, "%u MB", 
            snap.vram_total_mb - snap.vram_used_mb);
    }
    
    ui_panel_draw(&PANEL_GPU_METRICS);
    
    if (gpu_present) {
        /* Utilization */
        ui_panel_print(&PANEL_GPU_METRICS, 1, 0, "Utilization:");
        ui_goto(PANEL_GPU_METRICS.x + 14, PANEL_GPU_METRICS.y + 1);
        ui_progress_bar(PANEL_GPU_METRICS.x + 14, PANEL_GPU_METRICS.y + 1, 
            20, (float)snap.gpu_util_pct);
        printf(" %u%%", snap.gpu_util_pct);
        
        /* Memory */
        float vram_pct = snap.vram_total_mb > 0 ? 
            (float)snap.vram_used_mb * 100 / snap.vram_total_mb : 0;
        ui_panel_print(&PANEL_GPU_METRICS, 1, 2, "Memory:");
        ui_goto(PANEL_GPU_METRICS.x + 14, PANEL_GPU_METRICS.y + 3);
        ui_progress_bar(PANEL_GPU_METRICS.x + 14, PANEL_GPU_METRICS.y + 3,
            20, vram_pct);
        printf(" %.0f%%", vram_pct);
        
        /* Temperature */
        ui_panel_print(&PANEL_GPU_METRICS, 1, 4, "Temperature:");
        ui_panel_print(&PANEL_GPU_METRICS, 14, 4, "%s%u°C%s",
            snap.gpu_temp_c > 80 ? ANSI_RED :
            snap.gpu_temp_c > 70 ? ANSI_YELLOW : ANSI_GREEN,
            snap.gpu_temp_c, ANSI_RESET);
        
        /* Power */
        ui_panel_print(&PANEL_GPU_METRICS, 1, 6, "Power:");
        ui_panel_print(&PANEL_GPU_METRICS, 14, 6, "%u W", snap.gpu_power_w);
        
        /* Thermal throttle */
        ui_panel_print(&PANEL_GPU_METRICS, 1, 8, "Throttling:");
        ui_panel_print(&PANEL_GPU_METRICS, 14, 8, "%s%s%s",
            snap.thermal_throttle ? ANSI_RED : ANSI_GREEN,
            snap.thermal_throttle ? "YES" : "No", ANSI_RESET);
    } else {
        ui_panel_print(&PANEL_GPU_METRICS, 1, 1, "(no metrics available)");
    }
    
    ui_panel_draw(&PANEL_GPU_VRAM);
    ui_panel_print(&PANEL_GPU_VRAM, 1, 0, "VRAM Budget (BALANCED profile):");
    ui_panel_print(&PANEL_GPU_VRAM, 1, 2, 
        "Model: 60%%    KV Cache: 30%%    Workspace: 8%%    Reserve: 2%%");
    ui_panel_print(&PANEL_GPU_VRAM, 1, 3, "(Budget applies when model is loaded)");
    
    ui_action_bar("[Esc] Back   [R] Refresh");
}

void view_gpu_input(ui_key_t key) {
    switch (key) {
        case KEY_ESC:
            ui_view_pop();
            break;
        case 'r':
        case 'R':
            ui_view_redraw();
            break;
        default:
            break;
    }
}

/* ============================================================================
 * VIEW_LOGS - Log Viewer with Ring Buffer
 * ============================================================================ */

/* Simple ring buffer for logs */
#define LOG_RING_SIZE 100
#define LOG_LINE_MAX 120

typedef struct {
    char lines[LOG_RING_SIZE][LOG_LINE_MAX];
    int head;
    int count;
    int scroll_offset;
    int filter_level;  /* 0=all, 1=warn+error, 2=error only */
} log_ring_t;

static log_ring_t s_log_ring = {0};

/* Add a log line to the ring buffer */
void hexos_log_to_ring(const char *msg) {
    if (!msg || !msg[0]) return;
    
    strncpy(s_log_ring.lines[s_log_ring.head], msg, LOG_LINE_MAX - 1);
    s_log_ring.lines[s_log_ring.head][LOG_LINE_MAX - 1] = '\0';
    
    s_log_ring.head = (s_log_ring.head + 1) % LOG_RING_SIZE;
    if (s_log_ring.count < LOG_RING_SIZE) {
        s_log_ring.count++;
    }
}

static const ui_panel_t PANEL_LOG_HEADER = {0, 0, 80, 3, "LOGS", false};
static const ui_panel_t PANEL_LOG_VIEW = {0, 3, 80, 18, "LOG OUTPUT", false};

void view_logs_draw(void) {
    ui_panel_draw(&PANEL_LOG_HEADER);
    
    const char *filter_names[] = {"ALL", "WARN+ERR", "ERR ONLY"};
    ui_panel_print(&PANEL_LOG_HEADER, 1, 0,
        "System Logs [%d entries]    Filter: %s    [Esc] Back",
        s_log_ring.count, filter_names[s_log_ring.filter_level]);
    
    ui_panel_draw(&PANEL_LOG_VIEW);
    
    if (s_log_ring.count == 0) {
        ui_panel_print(&PANEL_LOG_VIEW, 1, 1, "(no log entries yet)");
        ui_panel_print(&PANEL_LOG_VIEW, 1, 3, "Logs will appear here as HEXOS runs.");
        ui_panel_print(&PANEL_LOG_VIEW, 1, 4, "Note: Boot logs appear before UI init.");
    } else {
        /* Display logs from ring buffer */
        int display_lines = 14;  /* Max lines to show */
        int start_idx = s_log_ring.head - s_log_ring.count;
        if (start_idx < 0) start_idx += LOG_RING_SIZE;
        
        /* Apply scroll offset */
        int offset = s_log_ring.scroll_offset;
        int displayed = 0;
        
        for (int i = 0; i < s_log_ring.count && displayed < display_lines; i++) {
            int idx = (start_idx + i + offset) % LOG_RING_SIZE;
            const char *line = s_log_ring.lines[idx];
            
            /* Apply filter */
            if (s_log_ring.filter_level == 1) {
                if (!strstr(line, "WARN") && !strstr(line, "ERROR") && 
                    !strstr(line, "warn") && !strstr(line, "error")) {
                    continue;
                }
            } else if (s_log_ring.filter_level == 2) {
                if (!strstr(line, "ERROR") && !strstr(line, "error")) {
                    continue;
                }
            }
            
            /* Color based on level */
            const char *color = ANSI_RESET;
            if (strstr(line, "ERROR") || strstr(line, "error")) {
                color = ANSI_RED;
            } else if (strstr(line, "WARN") || strstr(line, "warn")) {
                color = ANSI_YELLOW;
            } else if (strstr(line, "OK") || strstr(line, "success")) {
                color = ANSI_GREEN;
            }
            
            /* Truncate line to fit */
            char truncated[76];
            strncpy(truncated, line, 75);
            truncated[75] = '\0';
            
            ui_panel_print(&PANEL_LOG_VIEW, 1, displayed, "%s%s%s", 
                color, truncated, ANSI_RESET);
            displayed++;
        }
        
        /* Show scroll indicator */
        if (s_log_ring.count > display_lines) {
            ui_panel_print(&PANEL_LOG_VIEW, 75, 0, "[%d%%]", 
                (s_log_ring.scroll_offset * 100) / (s_log_ring.count - display_lines + 1));
        }
    }
    
    ui_action_bar("[Esc] Back  [↑/↓] Scroll  [F] Filter  [C] Clear  [T] Test Log");
}

void view_logs_input(ui_key_t key) {
    switch (key) {
        case KEY_ESC:
            ui_view_pop();
            break;
        case KEY_UP:
            if (s_log_ring.scroll_offset > 0) {
                s_log_ring.scroll_offset--;
            }
            break;
        case KEY_DOWN:
            if (s_log_ring.scroll_offset < s_log_ring.count - 14) {
                s_log_ring.scroll_offset++;
            }
            break;
        case KEY_PGUP:
            s_log_ring.scroll_offset -= 10;
            if (s_log_ring.scroll_offset < 0) s_log_ring.scroll_offset = 0;
            break;
        case KEY_PGDOWN:
            s_log_ring.scroll_offset += 10;
            if (s_log_ring.scroll_offset > s_log_ring.count - 14) {
                s_log_ring.scroll_offset = s_log_ring.count - 14;
            }
            if (s_log_ring.scroll_offset < 0) s_log_ring.scroll_offset = 0;
            break;
        case 'f':
        case 'F':
            s_log_ring.filter_level = (s_log_ring.filter_level + 1) % 3;
            break;
        case 'c':
        case 'C':
            /* Clear log buffer */
            s_log_ring.count = 0;
            s_log_ring.head = 0;
            s_log_ring.scroll_offset = 0;
            break;
        case 't':
        case 'T':
            /* Test: add some log entries */
            hexos_log_to_ring("[INFO] Test log entry from UI");
            hexos_log_to_ring("[WARN] This is a warning message");
            hexos_log_to_ring("[ERROR] This is an error message");
            hexos_log_to_ring("[OK] Operation completed successfully");
            break;
        default:
            break;
    }
}

/* ============================================================================
 * VIEW_ADVANCED - Advanced Menu (requires auth)
 * ============================================================================ */

static const ui_panel_t PANEL_ADV_HEADER = {0, 0, 80, 3, "ADVANCED", true};
static const ui_panel_t PANEL_ADV_MENU = {0, 3, 80, 18, "ADVANCED OPTIONS", true};

static bool s_advanced_authenticated = false;

void view_advanced_draw(void) {
    ui_panel_draw(&PANEL_ADV_HEADER);
    ui_panel_print(&PANEL_ADV_HEADER, 1, 0,
        "%sADVANCED MEMORY MANAGEMENT%s    [Esc] Back",
        ANSI_YELLOW, ANSI_RESET);
    
    ui_panel_draw(&PANEL_ADV_MENU);
    
    if (!s_advanced_authenticated) {
        ui_panel_print(&PANEL_ADV_MENU, 1, 2, 
            "%sAuthentication Required%s", ANSI_YELLOW, ANSI_RESET);
        ui_panel_print(&PANEL_ADV_MENU, 1, 4, 
            "Press [A] to authenticate");
        ui_panel_print(&PANEL_ADV_MENU, 1, 6,
            "Default credentials: helios / helios123");
    } else {
        ui_panel_print(&PANEL_ADV_MENU, 1, 0, 
            "%s✓ Authenticated%s", ANSI_GREEN, ANSI_RESET);
        
        ui_panel_print(&PANEL_ADV_MENU, 1, 2, "[1] Export Identity");
        ui_panel_print(&PANEL_ADV_MENU, 5, 3, "Export identity to JSON backup");
        
        ui_panel_print(&PANEL_ADV_MENU, 1, 5, "[2] Archive Memory");
        ui_panel_print(&PANEL_ADV_MENU, 5, 6, "Archive current day's episodic memory");
        
        ui_panel_print(&PANEL_ADV_MENU, 1, 8, "[3] Verify Integrity");
        ui_panel_print(&PANEL_ADV_MENU, 5, 9, "Check memory and identity integrity");
        
        ui_panel_print(&PANEL_ADV_MENU, 1, 11, 
            "%s[9] WIPE EPISODIC MEMORY%s", ANSI_RED, ANSI_RESET);
        ui_panel_print(&PANEL_ADV_MENU, 5, 12, 
            "%sDelete all conversation history%s", ANSI_RED, ANSI_RESET);
        
        ui_panel_print(&PANEL_ADV_MENU, 1, 14,
            "%s[0] FACTORY RESET%s", ANSI_RED, ANSI_RESET);
        ui_panel_print(&PANEL_ADV_MENU, 5, 15,
            "%sReset identity to defaults + wipe memory%s", ANSI_RED, ANSI_RESET);
    }
    
    ui_action_bar("[Esc] Back   [A] Authenticate   [1-9] Select option");
}

void view_advanced_input(ui_key_t key) {
    switch (key) {
        case KEY_ESC:
            ui_view_pop();
            s_advanced_authenticated = false;  /* Logout on exit */
            break;
            
        case 'a':
        case 'A':
            if (!s_advanced_authenticated) {
                char user[64], pass[64];
                if (ui_dialog_auth(user, sizeof(user), pass, sizeof(pass))) {
                    if (strcmp(user, "helios") == 0 && strcmp(pass, "helios123") == 0) {
                        s_advanced_authenticated = true;
                        ui_dialog_message("SUCCESS", "Authentication successful");
                    } else {
                        ui_dialog_message("ERROR", "Invalid credentials");
                    }
                }
            }
            break;
            
        case '1':
            if (s_advanced_authenticated) {
                /* Export identity to JSON */
                if (!hnf_ext_is_initialized()) {
                    hnf_ext_init();
                }
                if (hnf_ext_load("runtime/hnf/helios.hnf") == HNF_OK) {
                    char backup_path[256];
                    time_t now = time(NULL);
                    struct tm *tm_info = localtime(&now);
                    snprintf(backup_path, sizeof(backup_path),
                        "runtime/hnf/helios_%04d%02d%02d.json",
                        tm_info->tm_year + 1900, tm_info->tm_mon + 1, tm_info->tm_mday);
                    
                    if (hnf_ext_export_json(backup_path) == HNF_OK) {
                        hexos_log_to_ring("[OK] Identity exported");
                        ui_dialog_message("EXPORTED", "Identity saved to JSON");
                    } else {
                        ui_dialog_message("ERROR", "Export failed");
                    }
                } else {
                    ui_dialog_message("ERROR", "No identity to export");
                }
            }
            break;
            
        case '2':
            if (s_advanced_authenticated) {
                /* Archive memory */
                if (mc_is_initialized()) {
                    if (mc_archive_day() == MC_OK) {
                        hexos_log_to_ring("[OK] Memory archived");
                        ui_dialog_message("ARCHIVE", "Memory archived successfully");
                    } else {
                        ui_dialog_message("ERROR", "Archive failed");
                    }
                } else {
                    ui_dialog_message("INFO", "Memory Core not active");
                }
            }
            break;
            
        case '3':
            if (s_advanced_authenticated) {
                /* Verify integrity */
                uint32_t errors = 0;
                if (mc_is_initialized()) {
                    mc_verify_integrity(true, &errors);
                }
                char msg[64];
                snprintf(msg, sizeof(msg), "Integrity check: %u errors", errors);
                hexos_log_to_ring(errors > 0 ? "[WARN] Integrity errors found" : "[OK] Integrity OK");
                ui_dialog_message("VERIFY", msg);
            }
            break;
            
        case '9':
            if (s_advanced_authenticated) {
                if (ui_dialog_confirm_dangerous("WIPE MEMORY", 
                    "Delete ALL conversation history?", "WIPE")) {
                    if (mc_is_initialized()) {
                        uint32_t degraded = 0;
                        mc_degrade(9999999, &degraded);
                        hexos_log_to_ring("[WARN] Episodic memory wiped");
                        char msg[64];
                        snprintf(msg, sizeof(msg), "Wiped %u items", degraded);
                        ui_dialog_message("WIPED", msg);
                    }
                }
            }
            break;
            
        case '0':
            if (s_advanced_authenticated) {
                if (ui_dialog_confirm_dangerous("FACTORY RESET",
                    "Reset Helios to defaults? Cannot be undone!", "RESET")) {
                    /* Wipe memory */
                    if (mc_is_initialized()) {
                        uint32_t degraded = 0;
                        mc_degrade(9999999, &degraded);
                    }
                    
                    /* Reset identity to defaults */
                    if (hnf_ext_is_initialized()) {
                        hnf_ext_reset("I CONFIRM RESET");
                        hnf_ext_save();
                    }
                    
                    hexos_log_to_ring("[WARN] Factory reset complete");
                    ui_dialog_message("RESET", "Helios reset to defaults");
                    s_advanced_authenticated = false;
                }
            }
            break;
            
        default:
            break;
    }
}

/* ============================================================================
 * VIEW REGISTRATION
 * ============================================================================ */

void hexos_views_init(void) {
    ui_view_register(VIEW_BOOT, view_boot_draw, view_boot_input);
    ui_view_register(VIEW_MAIN, view_main_draw, view_main_input);
    ui_view_register(VIEW_IDENTITY, view_identity_draw, view_identity_input);
    ui_view_register(VIEW_MEMORY, view_memory_draw, view_memory_input);
    ui_view_register(VIEW_GPU, view_gpu_draw, view_gpu_input);
    ui_view_register(VIEW_LOGS, view_logs_draw, view_logs_input);
    ui_view_register(VIEW_ADVANCED, view_advanced_draw, view_advanced_input);
}

/* ============================================================================
 * BOOT STATE HELPERS
 * ============================================================================ */

void boot_state_init(void) {
    memset(&s_boot, 0, sizeof(s_boot));
    
    s_boot.version_major = HEXOS_VERSION_MAJOR;
    s_boot.version_minor = HEXOS_VERSION_MINOR;
    s_boot.build_number = HEXOS_BUILD_NUMBER;
    s_boot.hnf_version = HEXOS_HNF_VERSION;
    
    strcpy(s_boot.profile, "BALANCED");
    strcpy(s_boot.detail_line1, "Initializing...");
    strcpy(s_boot.detail_line2, "");
    
    s_boot.boot_start_ms = hexos_time_ms();
    
    /* Generate session ID */
    srand(time(NULL) ^ getpid());
    snprintf(s_boot.session_id, sizeof(s_boot.session_id), 
             "%08x", (unsigned int)rand());
    
    /* Get hostname */
    gethostname(s_boot.hostname, sizeof(s_boot.hostname));
}

void boot_phase_start(int phase, const char *detail) {
    if (phase < 0 || phase >= 6) return;
    
    s_boot.current_phase = phase;
    s_boot.phases[phase].status = PHASE_RUNNING;
    s_boot.phases[phase].start_ms = hexos_time_ms();
    s_boot.phases[phase].progress = 0;
    
    snprintf(s_boot.detail_line1, sizeof(s_boot.detail_line1),
             "Phase %d/6: %s", phase + 1, detail);
    s_boot.detail_line2[0] = '\0';
}

void boot_phase_progress(int phase, float progress) {
    if (phase < 0 || phase >= 6) return;
    s_boot.phases[phase].progress = progress;
}

void boot_phase_detail(const char *line2) {
    strncpy(s_boot.detail_line2, line2, sizeof(s_boot.detail_line2) - 1);
}

void boot_phase_end(int phase, phase_status_t status) {
    if (phase < 0 || phase >= 6) return;
    
    s_boot.phases[phase].status = status;
    s_boot.phases[phase].progress = 100;
    s_boot.phases[phase].time_ms = hexos_time_ms() - s_boot.phases[phase].start_ms;
}

void boot_set_alert(const char *text, int count) {
    strncpy(s_boot.alert_text, text, sizeof(s_boot.alert_text) - 1);
    s_boot.alert_count = count;
}

void boot_set_complete(void) {
    s_boot.boot_complete = true;
    s_boot.total_time_ms = hexos_time_ms() - s_boot.boot_start_ms;
    
    snprintf(s_boot.detail_line1, sizeof(s_boot.detail_line1),
             "Boot complete in %.2fs", s_boot.total_time_ms / 1000.0f);
    strcpy(s_boot.detail_line2, "Press [Enter] to continue to HEXOS");
}
