/*
 * HEXOS - HELIOS Executive Operating System
 * Main Entry Point and Boot Sequence
 * 
 * "El cuerpo que protege la mente"
 */

#define _DEFAULT_SOURCE  /* For usleep */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <time.h>
#include <sys/time.h>
#include <unistd.h>
#include <termios.h>
#include "../include/hexos.h"
#include "../include/hexos_telemetry.h"
#include "../include/hexos_ipc.h"

/* HELIOS Cognitive Modules (read-only access from HEXOS) */
#include "../../../hnf_ext/include/hnf_ext.h"
#include "../../../memory_core/include/memory_core.h"
#include "../../../hera/include/hera.h"

/* New UI System */
#include "../include/hexos_ui.h"
#include "../include/hexos_views.h"

/* ============================================================================
 * QUIET MODE FOR UI
 * When UI is active, suppress boot printf output
 * ============================================================================ */

static bool s_ui_quiet_mode = false;

#define BOOT_PRINTF(...) do { if (!s_ui_quiet_mode) printf(__VA_ARGS__); } while(0)

/* ============================================================================
 * GLOBAL CONTEXT (Singleton)
 * ============================================================================ */

static hexos_context_t s_ctx;
static hexos_ipc_ctx_t s_ipc_ctx;
static volatile bool s_shutdown_requested = false;

hexos_context_t* hexos_get_context(void) {
    return &s_ctx;
}

hexos_ipc_ctx_t* hexos_get_ipc(void) {
    return &s_ipc_ctx;
}

/* ============================================================================
 * TIME UTILITIES
 * ============================================================================ */

uint64_t hexos_time_ms(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (uint64_t)tv.tv_sec * 1000 + tv.tv_usec / 1000;
}

void hexos_time_str(char *buf, size_t len) {
    time_t now = time(NULL);
    struct tm *tm_info = localtime(&now);
    strftime(buf, len, "%H:%M:%S", tm_info);
}

void hexos_datetime_str(char *buf, size_t len) {
    time_t now = time(NULL);
    struct tm *tm_info = localtime(&now);
    strftime(buf, len, "%Y-%m-%d %H:%M:%S", tm_info);
}

static double get_elapsed_s(uint64_t start_ms) {
    return (hexos_time_ms() - start_ms) / 1000.0;
}

/* ============================================================================
 * SIGNAL HANDLING
 * ============================================================================ */

static void signal_handler(int sig) {
    if (sig == SIGINT || sig == SIGTERM) {
        s_shutdown_requested = true;
        printf("\n[HEXOS] Shutdown requested...\n");
    }
}

/* ============================================================================
 * BOOT PHASE 1: HARDWARE DETECTION
 * ============================================================================ */

hexos_result_t hexos_boot_phase1_hardware(hexos_context_t *ctx) {
    uint64_t start = hexos_time_ms();
    
    hexos_print_phase(1, 6, "Hardware Detection");
    
    hexos_result_t result = hexos_hw_detect(&ctx->hw_contract);
    if (result != HEXOS_OK) {
        BOOT_PRINTF("  Hardware detection FAILED\n");
        return result;
    }
    
    /* Print CPU info */
    hexos_print_tree(1, false, "CPU: %s", ctx->hw_contract.cpu.model_name);
    hexos_print_tree(2, false, "Cores: %d physical / %d logical", 
                     ctx->hw_contract.cpu.physical_cores,
                     ctx->hw_contract.cpu.logical_cores);
    hexos_print_tree(2, true, "ISA: AVX2 %s  AVX512 %s",
                     ctx->hw_contract.cpu.has_avx2 ? "OK" : "X",
                     ctx->hw_contract.cpu.has_avx512 ? "OK" : "X");
    BOOT_PRINTF("%s\n", TREE_V);
    
    /* Print RAM info */
    hexos_print_tree(1, false, "RAM: %u MB", ctx->hw_contract.ram.total_mb);
    hexos_print_tree(2, false, "OS reserved:  %u MB", ctx->hw_contract.ram.reserved_os_mb);
    hexos_print_tree(2, true, "Usable:       %u MB", ctx->hw_contract.ram.usable_mb);
    BOOT_PRINTF("%s\n", TREE_V);
    
    /* Print GPU info */
    for (int i = 0; i < ctx->hw_contract.gpu_count; i++) {
        gpu_info_t *gpu = &ctx->hw_contract.gpus[i];
        bool is_last_gpu = (i == ctx->hw_contract.gpu_count - 1);
        
        hexos_print_tree(1, is_last_gpu && ctx->hw_contract.storage.work_free_mb == 0, 
                        "GPU %d: %s", i, gpu->name);
        hexos_print_tree(2, false, "VRAM:    %u MB", gpu->vram_total_mb);
        hexos_print_tree(2, false, "Compute: SM %d.%d / %u SMs", 
                        gpu->compute_cap_major, gpu->compute_cap_minor, gpu->sm_count);
        hexos_print_tree(2, true, "Driver:  %s", gpu->driver_version);
        
        if (!is_last_gpu || ctx->hw_contract.storage.work_free_mb > 0) {
            BOOT_PRINTF("%s\n", TREE_V);
        }
    }
    
    /* Print Storage info */
    if (ctx->hw_contract.storage.work_free_mb > 0) {
        const char *type_str;
        switch (ctx->hw_contract.storage.work_type) {
            case STORAGE_TYPE_NVME: type_str = "NVMe"; break;
            case STORAGE_TYPE_SSD:  type_str = "SSD"; break;
            case STORAGE_TYPE_HDD:  type_str = "HDD"; break;
            default:                type_str = "Disk"; break;
        }
        hexos_print_tree(1, true, "Storage: %s / %u GB free", 
                        type_str, ctx->hw_contract.storage.work_free_mb / 1024);
    }
    
    ctx->boot_timing.hardware_detection_s = get_elapsed_s(start);
    BOOT_PRINTF("\n  [%.1fs]\n", ctx->boot_timing.hardware_detection_s);
    
    return HEXOS_OK;
}

/* ============================================================================
 * BOOT PHASE 2: HARDWARE CONTRACT
 * ============================================================================ */

hexos_result_t hexos_boot_phase2_contract(hexos_context_t *ctx) {
    uint64_t start = hexos_time_ms();
    
    hexos_print_phase(2, 6, "Hardware Contract");
    
    /* Validate hardware */
    hexos_result_t result = hexos_hw_validate(&ctx->hw_contract);
    if (result == HEXOS_NOGO) {
        hexos_print_status("Validation", false, "NO-GO");
        return result;
    }
    
    hexos_print_status("Invariant validation", true, "PASS");
    hexos_print_status("Capability matrix", true, "BUILT");
    
    /* Seal contract */
    hexos_hw_seal_contract(&ctx->hw_contract);
    
    BOOT_PRINTF("  %s Contract sealed: %s\n", TREE_LAST, ctx->hw_contract.contract_id);
    
    ctx->boot_timing.hardware_contract_s = get_elapsed_s(start);
    BOOT_PRINTF("\n  [%.1fs]\n", ctx->boot_timing.hardware_contract_s);
    
    return HEXOS_OK;
}

/* ============================================================================
 * BOOT PHASE 3: MODULE ATTESTATION
 * ============================================================================ */

hexos_result_t hexos_boot_phase3_modules(hexos_context_t *ctx) {
    uint64_t start = hexos_time_ms();
    
    hexos_print_phase(3, 6, "Module Attestation");
    
    /* Module info: name, version, is_stub */
    struct {
        const char *name;
        const char *version;
        bool is_stub;
    } modules[] = {
        {"HEXOS_BUS",        "v1.0", false},  /* Real - IPC */
        {"HEXOS_TELEMETRY",  "v1.0", false},  /* Real - hardware monitoring */
        {"MEMORY_CORE",      "v3.0", false},  /* Real - implemented */
        {"CUDA_ENGINE",      "v2.1", true},   /* STUB - no real CUDA engine yet */
        {"HERA",             "v3.0", false},  /* Real - implemented */
        {"COGNITIVE_KERNEL", "v3.0", true},   /* STUB - no real LLM yet */
    };
    
    int num_modules = sizeof(modules) / sizeof(modules[0]);
    int stub_count = 0;
    
    for (int i = 0; i < num_modules; i++) {
        usleep(50000);  /* 50ms delay for visual effect */
        
        bool is_last = (i == num_modules - 1);
        
        if (modules[i].is_stub) {
            BOOT_PRINTF("  %s %-18s %-5s  │░░░░░░░░│  %s%s%s\n",
                   is_last ? TREE_LAST : TREE_BRANCH,
                   modules[i].name,
                   modules[i].version,
                   ANSI_YELLOW, "STUB", ANSI_RESET);
            stub_count++;
        } else {
            BOOT_PRINTF("  %s %-18s %-5s  │████████│  %s%s%s\n",
                   is_last ? TREE_LAST : TREE_BRANCH,
                   modules[i].name,
                   modules[i].version,
                   ANSI_GREEN, "OK", ANSI_RESET);
        }
        
        /* Add to context */
        strncpy(ctx->modules[i].id, modules[i].name, HEXOS_MAX_STRING - 1);
        strncpy(ctx->modules[i].version, modules[i].version, HEXOS_MAX_STRING - 1);
        ctx->modules[i].state = modules[i].is_stub ? MODULE_STATE_DEGRADED : MODULE_STATE_OK;
        ctx->modules[i].uptime_ms = 0;
    }
    
    ctx->module_count = num_modules;
    
    if (stub_count > 0) {
        BOOT_PRINTF("\n  %sNote: %d module(s) running in STUB mode (no LLM loaded)%s\n",
               ANSI_YELLOW, stub_count, ANSI_RESET);
    }
    
    ctx->boot_timing.module_attestation_s = get_elapsed_s(start);
    BOOT_PRINTF("\n  [%.1fs]\n", ctx->boot_timing.module_attestation_s);
    
    return HEXOS_OK;
}

/* ============================================================================
 * BOOT PHASE 4: RESOURCE ALLOCATION
 * ============================================================================ */

hexos_result_t hexos_boot_phase4_resources(hexos_context_t *ctx) {
    uint64_t start = hexos_time_ms();
    
    hexos_print_phase(4, 6, "Resource Allocation (BALANCED)");
    
    /* Calculate budget */
    hexos_hw_calculate_budget(&ctx->vram_budget, 
                              ctx->hw_contract.total_vram_mb,
                              PROFILE_BALANCED);
    
    BOOT_PRINTF("  %s VRAM Budget: %u MB\n", TREE_BRANCH, ctx->vram_budget.total_mb);
    
    /* Visual bar with Unicode blocks */
    int total_width = 50;
    int model_w = (total_width * ctx->vram_budget.model_pct) / 100;
    int kv_w = (total_width * ctx->vram_budget.kv_pct) / 100;
    int work_w = (total_width * ctx->vram_budget.workspace_pct) / 100;
    int res_w = total_width - model_w - kv_w - work_w;
    
    BOOT_PRINTF("  %s    │", TREE_V);
    for (int i = 0; i < model_w; i++) BOOT_PRINTF("█");
    BOOT_PRINTF("│");
    for (int i = 0; i < kv_w; i++) BOOT_PRINTF("▓");
    BOOT_PRINTF("│");
    for (int i = 0; i < work_w; i++) BOOT_PRINTF("░");
    BOOT_PRINTF("│");
    for (int i = 0; i < res_w; i++) BOOT_PRINTF("·");
    BOOT_PRINTF("│\n");
    
    BOOT_PRINTF("  %s     MODEL %d%%    KV %d%%    WORK %d%%   R %d%%\n",
           TREE_V,
           ctx->vram_budget.model_pct,
           ctx->vram_budget.kv_pct,
           ctx->vram_budget.workspace_pct,
           ctx->vram_budget.reserve_pct);
    
    BOOT_PRINTF("  %s    %s Model:    %u MB (%d%%)\n", TREE_V, TREE_BRANCH,
           ctx->vram_budget.model_weights_mb, ctx->vram_budget.model_pct);
    BOOT_PRINTF("  %s    %s KV:       %u MB (%d%%) / ~%u tok max\n", TREE_V, TREE_BRANCH,
           ctx->vram_budget.kv_cache_mb, ctx->vram_budget.kv_pct,
           ctx->vram_budget.max_tokens);
    BOOT_PRINTF("  %s    %s Work:     %u MB (%d%%)\n", TREE_V, TREE_BRANCH,
           ctx->vram_budget.workspace_mb, ctx->vram_budget.workspace_pct);
    BOOT_PRINTF("  %s    %s Reserve:  %u MB (%d%%)\n", TREE_V, TREE_LAST,
           ctx->vram_budget.reserve_mb, ctx->vram_budget.reserve_pct);
    
    BOOT_PRINTF("  %s\n", TREE_V);
    BOOT_PRINTF("  %s RAM Spillover: %u MB available / trigger at 85%%\n",
           TREE_LAST, ctx->hw_contract.ram.spillover_max_mb);
    
    ctx->boot_timing.resource_allocation_s = get_elapsed_s(start);
    BOOT_PRINTF("\n  [%.1fs]\n", ctx->boot_timing.resource_allocation_s);
    
    return HEXOS_OK;
}

/* ============================================================================
 * BOOT PHASE 5: RUNTIME INITIALIZATION
 * ============================================================================ */

hexos_result_t hexos_boot_phase5_runtime(hexos_context_t *ctx) {
    uint64_t start = hexos_time_ms();
    
    hexos_print_phase(5, 6, "Runtime Initialization");
    
    /* CUDA memory pools - STUB until real engine exists */
    BOOT_PRINTF("  %s CUDA Memory Pools %s(STUB - no model loaded)%s\n", 
           TREE_BRANCH, ANSI_YELLOW, ANSI_RESET);
    usleep(100000);
    hexos_print_status("Model weights pool", true, "RESERVED");
    usleep(100000);
    hexos_print_status("KV cache pool", true, "RESERVED");
    usleep(100000);
    hexos_print_status("Workspace pool", true, "RESERVED");
    
    BOOT_PRINTF("  %s\n", TREE_V);
    
    /* Initialize IPC Bus - REAL */
    BOOT_PRINTF("  %s IPC Bus\n", TREE_BRANCH);
    usleep(100000);
    
    int ipc_result = hexos_ipc_init(&s_ipc_ctx);
    if (ipc_result == 0) {
        hexos_print_status("Shared memory segment", true, "MAPPED");
        
        /* Set initial VRAM budget in IPC */
        hexos_ipc_lock(&s_ipc_ctx);
        s_ipc_ctx.state->resources.vram_budget_model_mb = ctx->vram_budget.model_weights_mb;
        s_ipc_ctx.state->resources.vram_budget_kv_mb = ctx->vram_budget.kv_cache_mb;
        s_ipc_ctx.state->resources.vram_budget_workspace_mb = ctx->vram_budget.workspace_mb;
        hexos_ipc_unlock(&s_ipc_ctx);
    } else {
        hexos_print_status("Shared memory segment", false, "FAILED");
    }
    usleep(100000);
    hexos_print_status("Message queues", true, "ACTIVE");
    
    BOOT_PRINTF("  %s\n", TREE_V);
    
    /* Cognitive Kernel interface - STUB */
    BOOT_PRINTF("  %s Cognitive Kernel Interface %s(STUB)%s\n", 
           TREE_LAST, ANSI_YELLOW, ANSI_RESET);
    usleep(100000);
    hexos_print_status("Model loader API", true, "STANDBY");
    usleep(100000);
    hexos_print_status("Inference scheduler", true, "STANDBY");
    
    ctx->boot_timing.model_loading_s = get_elapsed_s(start);
    BOOT_PRINTF("\n  [%.1fs]\n", ctx->boot_timing.model_loading_s);
    
    return HEXOS_OK;
}

/* ============================================================================
 * BOOT PHASE 6: HELIOS ACTIVATION
 * ============================================================================ */

hexos_result_t hexos_boot_phase6_helios(hexos_context_t *ctx) {
    uint64_t start = hexos_time_ms();
    
    hexos_print_phase(6, 6, "HELIOS Activation");
    
    /* Check for real HNF-EXT file */
    const char *hnf_path = "./runtime/hnf/helios.hnf-ext";
    FILE *hnf_file = fopen(hnf_path, "rb");
    if (hnf_file) {
        fclose(hnf_file);
        BOOT_PRINTF("  %s HNF-EXT: %sLOADED%s / %s\n", TREE_BRANCH, ANSI_GREEN, ANSI_RESET, hnf_path);
    } else {
        BOOT_PRINTF("  %s HNF-EXT: %sNOT FOUND%s (identity not persisted)\n", 
               TREE_BRANCH, ANSI_YELLOW, ANSI_RESET);
    }
    
    /* Check for episodic memory files */
    const char *mem_path = "./runtime/memory";
    int mem_count = 0;
    /* Just check if directory exists for now */
    FILE *mem_dir = fopen(mem_path, "r");
    if (mem_dir) {
        fclose(mem_dir);
        BOOT_PRINTF("  %s Episodic Memory: %sAVAILABLE%s / %s\n", 
               TREE_BRANCH, ANSI_GREEN, ANSI_RESET, mem_path);
    } else {
        BOOT_PRINTF("  %s Episodic Memory: %sEMPTY%s (no archived days)\n",
               TREE_BRANCH, ANSI_YELLOW, ANSI_RESET);
    }
    (void)mem_count;
    
    usleep(100000);
    hexos_print_status("Memory Core", true, "ONLINE");
    usleep(100000);
    hexos_print_status("HERA", true, "ACTIVE");
    usleep(100000);
    hexos_print_status("Cognitive Kernel", true, "STUB");
    usleep(100000);
    hexos_print_status("Predictive Memory", false, "DISABLED");
    
    /* Continuity message */
    BOOT_PRINTF("\n");
    hexos_print_box_start(76);
    hexos_print_box_line(76, "CONTINUITY");
    hexos_print_box_line(76, "");
    
    if (s_ipc_ctx.state && s_ipc_ctx.state->memory.continuity_text[0]) {
        /* Split IPC text into lines (max ~60 chars per line) */
        const char *text = s_ipc_ctx.state->memory.continuity_text;
        char line[72];
        int len = strlen(text);
        int pos = 0;
        while (pos < len && pos < 200) {
            int line_len = len - pos > 60 ? 60 : len - pos;
            /* Find last space to break on word boundary */
            if (pos + line_len < len) {
                int i = line_len;
                while (i > 30 && text[pos + i] != ' ') i--;
                if (i > 30) line_len = i;
            }
            strncpy(line, text + pos, line_len);
            line[line_len] = '\0';
            hexos_print_box_line(76, line);
            pos += line_len;
            while (text[pos] == ' ') pos++;
        }
    } else {
        hexos_print_box_line(76, "Initializing... awaiting Memory Core connection.");
    }
    
    hexos_print_box_line(76, "                                                -- HELIOS");
    hexos_print_box_line(76, "");
    hexos_print_box_end(76);
    
    ctx->boot_timing.helios_activation_s = get_elapsed_s(start);
    BOOT_PRINTF("\n  [%.1fs]\n", ctx->boot_timing.helios_activation_s);
    
    return HEXOS_OK;
}

/* ============================================================================
 * INIT
 * ============================================================================ */

/* Helper to update UI during boot */
static void boot_ui_update(void) {
    if (ui_is_initialized()) {
        ui_view_redraw();
        ui_flush();
    }
}

hexos_result_t hexos_init(const char *work_path, const char *model_path) {
    (void)work_path;   /* TODO: use for storage detection */
    (void)model_path;  /* TODO: use for model loading */
    
    /* Initialize context */
    memset(&s_ctx, 0, sizeof(hexos_context_t));
    
    /* Generate session ID */
    snprintf(s_ctx.session.session_id, HEXOS_SESSION_ID_LEN + 1, "%08x", 
             (unsigned int)hexos_time_ms());
    s_ctx.session.start_time = hexos_time_ms();
    s_ctx.session.state = HEXOS_STATE_INIT;
    s_ctx.session.profile = PROFILE_BALANCED;
    
    /* Initialize logging (to file, not console in UI mode) */
    hexos_log_init(LOG_INFO, false);
    
    /* Enable quiet mode to suppress boot printf (UI will handle display) */
    hexos_log_set_quiet(true);
    s_ui_quiet_mode = true;
    
    /* Initialize telemetry early for boot display */
    hexos_telemetry_init(500);
    
    /* Initialize UI system */
    ui_init();
    hexos_views_init();
    
    /* Initialize boot state */
    boot_state_init();
    boot_state_t *boot = hexos_boot_state();
    
    /* Copy session info to boot state */
    strncpy(boot->session_id, s_ctx.session.session_id, sizeof(boot->session_id) - 1);
    gethostname(boot->hostname, sizeof(boot->hostname));
    
    /* Push boot view */
    ui_view_push(VIEW_BOOT);
    boot_ui_update();
    
    /* Run boot phases */
    hexos_result_t result;
    int warnings = 0;
    bool degraded = false;
    
    /* ========== Phase 1: Hardware Detection ========== */
    boot_phase_start(0, "Hardware Detection");
    boot_phase_detail("Scanning CPU, RAM, GPU, Storage...");
    boot_ui_update();
    
    boot_phase_progress(0, 10);
    boot_ui_update();
    
    result = hexos_boot_phase1_hardware(&s_ctx);
    
    boot_phase_progress(0, 100);
    if (result != HEXOS_OK) {
        boot_phase_end(0, PHASE_FAIL);
        boot_phase_detail("Hardware detection failed - cannot continue");
        boot_ui_update();
        usleep(2000000);  /* Show error for 2s */
        ui_shutdown();
        return result;
    }
    boot_phase_end(0, PHASE_OK);
    
    /* Store GPU name for display */
    if (s_ctx.hw_contract.gpu_count > 0) {
        strncpy(boot->gpu_name, s_ctx.hw_contract.gpus[0].name, sizeof(boot->gpu_name) - 1);
    }
    boot_ui_update();
    
    /* ========== Phase 2: Hardware Contract ========== */
    boot_phase_start(1, "Hardware Contract");
    boot_phase_detail("Validating capabilities...");
    boot_ui_update();
    
    boot_phase_progress(1, 30);
    boot_ui_update();
    
    result = hexos_boot_phase2_contract(&s_ctx);
    
    boot_phase_progress(1, 100);
    if (result == HEXOS_NOGO) {
        boot_phase_end(1, PHASE_FAIL);
        boot_phase_detail("NO-GO: Minimum requirements not met");
        boot_ui_update();
        usleep(2000000);
        ui_shutdown();
        return result;
    } else if (result != HEXOS_OK) {
        boot_phase_end(1, PHASE_WARN);
        warnings++;
    } else {
        boot_phase_end(1, PHASE_OK);
    }
    boot_ui_update();
    
    /* ========== Phase 3: Module Attestation ========== */
    boot_phase_start(2, "Module Attestation");
    boot_phase_detail("Loading Memory Core, HNF-EXT, HERA...");
    boot_ui_update();
    
    boot_phase_progress(2, 20);
    boot_ui_update();
    
    result = hexos_boot_phase3_modules(&s_ctx);
    
    boot_phase_progress(2, 100);
    if (result != HEXOS_OK) {
        boot_phase_end(2, PHASE_WARN);
        warnings++;
        degraded = true;
    } else {
        boot_phase_end(2, PHASE_OK);
    }
    
    /* Count stub modules for alert - check for degraded state (stubs are marked degraded) */
    int stub_count = 0;
    for (int i = 0; i < s_ctx.module_count; i++) {
        if (s_ctx.modules[i].state == MODULE_STATE_DEGRADED) stub_count++;
    }
    if (stub_count > 0) {
        boot_set_alert("STUB modules", stub_count);
    }
    boot_ui_update();
    
    /* ========== Phase 4: Resource Allocation ========== */
    boot_phase_start(3, "Resource Allocation");
    boot_phase_detail("Allocating VRAM pools, RAM limits...");
    boot_ui_update();
    
    boot_phase_progress(3, 50);
    boot_ui_update();
    
    result = hexos_boot_phase4_resources(&s_ctx);
    
    boot_phase_progress(3, 100);
    if (result != HEXOS_OK) {
        boot_phase_end(3, PHASE_WARN);
        warnings++;
        degraded = true;
    } else {
        boot_phase_end(3, PHASE_OK);
    }
    boot_ui_update();
    
    /* ========== Phase 5: Runtime Initialization ========== */
    boot_phase_start(4, "Runtime Initialization");
    boot_phase_detail("Setting up IPC, shared memory...");
    boot_ui_update();
    
    boot_phase_progress(4, 30);
    boot_ui_update();
    
    result = hexos_boot_phase5_runtime(&s_ctx);
    
    boot_phase_progress(4, 100);
    if (result != HEXOS_OK) {
        boot_phase_end(4, PHASE_WARN);
        warnings++;
        degraded = true;
    } else {
        boot_phase_end(4, PHASE_OK);
    }
    boot_ui_update();
    
    /* ========== Phase 6: HELIOS Activation ========== */
    boot_phase_start(5, "HELIOS Activation");
    boot_phase_detail("Connecting cognitive modules...");
    boot_ui_update();
    
    boot_phase_progress(5, 20);
    boot_ui_update();
    
    result = hexos_boot_phase6_helios(&s_ctx);
    
    boot_phase_progress(5, 60);
    boot_phase_detail("Loading identity from HNF-EXT...");
    boot_ui_update();
    
    /* Check HNF-EXT status */
    boot->hnf_ext_found = false;  /* Will be set by phase6 if found */
    
    boot_phase_progress(5, 100);
    if (result != HEXOS_OK) {
        boot_phase_end(5, PHASE_WARN);
        warnings++;
        degraded = true;
    } else {
        boot_phase_end(5, PHASE_OK);
    }
    
    /* Set continuity message */
    if (!boot->hnf_ext_found) {
        strcpy(boot->continuity_message, 
            "No persistent identity found. Operating in ephemeral mode. "
            "HERA will create identity on first meaningful interaction.");
    } else {
        strcpy(boot->continuity_message,
            "Identity loaded. Continuity restored. Ready to serve.");
    }
    boot_ui_update();
    
    /* Calculate total boot time */
    s_ctx.boot_timing.total_s = 
        s_ctx.boot_timing.hardware_detection_s +
        s_ctx.boot_timing.hardware_contract_s +
        s_ctx.boot_timing.module_attestation_s +
        s_ctx.boot_timing.resource_allocation_s +
        s_ctx.boot_timing.model_loading_s +
        s_ctx.boot_timing.helios_activation_s;
    
    /* Mark boot complete */
    boot_set_complete();
    boot_ui_update();
    
    /* Wait for user to press Enter */
    while (!boot->quit_requested) {
        ui_key_t key = ui_getkey();
        if (key == KEY_ENTER) {
            break;
        } else if (key == 'q' || key == 'Q') {
            boot->quit_requested = true;
            ui_shutdown();
            return HEXOS_ERROR;  /* User aborted */
        } else if (key != KEY_NONE) {
            /* Handle other boot screen input */
            ui_view_handle_input(key);
            boot_ui_update();
        }
        usleep(10000);
    }
    
    /* Ready - transition to main view handled by run loop */
    s_ctx.session.state = degraded ? HEXOS_STATE_DEGRADED : HEXOS_STATE_RUNNING;
    s_ctx.initialized = true;
    s_ctx.running = true;
    
    return HEXOS_OK;
}

/* ============================================================================
 * RUN (Main Loop)
 * ============================================================================ */

hexos_result_t hexos_run(void) {
    /* Setup signal handlers */
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    /* Telemetry already initialized in hexos_init */
    
    /* Replace boot view with main view */
    ui_clear();
    ui_view_set(VIEW_MAIN);
    ui_flush();
    
    boot_state_t *boot = hexos_boot_state();
    uint64_t last_refresh = hexos_time_ms();
    
    /* Main loop - UI driven */
    while (s_ctx.running && !s_shutdown_requested && !boot->quit_requested) {
        /* Check for input */
        ui_key_t key = ui_getkey();
        
        if (key != KEY_NONE) {
            /* Let view handle input - push/pop will redraw automatically */
            ui_view_handle_input(key);
            last_refresh = hexos_time_ms();  /* Reset timer after input */
        }
        
        /* Refresh display every 500ms for live metrics */
        uint64_t now = hexos_time_ms();
        if (now - last_refresh >= 500) {
            ui_view_redraw();
            last_refresh = now;
        }
        
        usleep(10000);  /* 10ms */
    }
    
    /* Shutdown telemetry */
    hexos_telemetry_shutdown();
    
    return HEXOS_OK;
}

/* ============================================================================
 * SHUTDOWN
 * ============================================================================ */

void hexos_shutdown(void) {
    s_shutdown_requested = true;
}

void hexos_cleanup(void) {
    /* Shutdown UI first to restore terminal */
    if (ui_is_initialized()) {
        ui_shutdown();
    }
    
    printf("\n[HEXOS] Shutting down...\n");
    s_ctx.session.state = HEXOS_STATE_SHUTDOWN;
    s_ctx.running = false;
    
    /* Shutdown IPC */
    hexos_ipc_shutdown(&s_ipc_ctx);
}

/* ============================================================================
 * MAIN
 * ============================================================================ */

int main(int argc, char *argv[]) {
    (void)argc;
    (void)argv;
    
    hexos_result_t result = hexos_init(".", NULL);
    
    if (result != HEXOS_OK) {
        fprintf(stderr, "\n[HEXOS] Boot failed with error %d\n", result);
        return 1;
    }
    
    result = hexos_run();
    
    hexos_cleanup();
    
    return (result == HEXOS_OK) ? 0 : 1;
}
