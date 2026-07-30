/*
 * HERA v3.0 - Test Program
 * HELIOS Cognitive Ecosystem
 * 
 * Demonstrates HERA cognitive coordination
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../include/hera.h"

/* ANSI colors */
#define GREEN   "\033[32m"
#define YELLOW  "\033[33m"
#define CYAN    "\033[36m"
#define MAGENTA "\033[35m"
#define RESET   "\033[0m"
#define BOLD    "\033[1m"

static void print_header(const char *title) {
    printf("\n%s%s=== %s ===%s\n\n", BOLD, CYAN, title, RESET);
}

static void print_ok(const char *msg) {
    printf("  %s✓%s %s\n", GREEN, RESET, msg);
}

static void print_info(const char *msg) {
    printf("  %s→%s %s\n", YELLOW, RESET, msg);
}

static const char* state_name(hera_state_t s) {
    const char *names[] = {"IDLE", "ACTIVE", "CONSOLIDATING", "CHECKPOINT", "RECOVERING", "DEGRADED"};
    return names[s];
}

static const char* pressure_name(hera_pressure_t p) {
    const char *names[] = {"LOW", "MEDIUM", "HIGH", "CRITICAL"};
    return names[p];
}

static void print_stats(hera_stats_t *stats) {
    printf("\n  ┌─────────────────────────────────────────────────┐\n");
    printf("  │ %sHERA STATISTICS%s                                 │\n", BOLD, RESET);
    printf("  ├─────────────────────────────────────────────────┤\n");
    printf("  │ State:              %12s              │\n", state_name(stats->state));
    printf("  │ Pressure:           %12s              │\n", pressure_name(stats->pressure));
    printf("  │ ────────────────────────────────                │\n");
    printf("  │ Essential (L1):     %12u              │\n", stats->essential_count);
    printf("  │ Active (L2):        %12u              │\n", stats->active_count);
    printf("  │ Archived (L3):      %12lu              │\n", stats->archived_count);
    printf("  │ ────────────────────────────────                │\n");
    printf("  │ Proposals today:    %12u              │\n", stats->proposals_today);
    printf("  │ Pending candidates: %12u              │\n", stats->pending_candidates);
    printf("  │ Accepted total:     %12u              │\n", stats->proposals_accepted_total);
    printf("  │ Rejected total:     %12u              │\n", stats->proposals_rejected_total);
    printf("  │ ────────────────────────────────                │\n");
    printf("  │ Consolidations:     %12u              │\n", stats->consolidations_total);
    printf("  │ Checkpoints:        %12u              │\n", stats->checkpoints_total);
    printf("  │ RAM limit:          %10lu MB            │\n", stats->ram_limit_mb);
    printf("  └─────────────────────────────────────────────────┘\n");
}

int main(void) {
    printf("\n");
    printf("╔══════════════════════════════════════════════════════════════════════╗\n");
    printf("║                                                                      ║\n");
    printf("║    ██╗  ██╗███████╗██████╗  █████╗                                   ║\n");
    printf("║    ██║  ██║██╔════╝██╔══██╗██╔══██╗                                  ║\n");
    printf("║    ███████║█████╗  ██████╔╝███████║                                  ║\n");
    printf("║    ██╔══██║██╔══╝  ██╔══██╗██╔══██║                                  ║\n");
    printf("║    ██║  ██║███████╗██║  ██║██║  ██║                                  ║\n");
    printf("║    ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝                                  ║\n");
    printf("║                                                                      ║\n");
    printf("║    Cognitive Coordinator v3.0                                        ║\n");
    printf("║    \"La mente que nunca olvida lo que importa\"                        ║\n");
    printf("║                                                                      ║\n");
    printf("╚══════════════════════════════════════════════════════════════════════╝\n");
    
    /* ======================================================================== */
    print_header("INITIALIZATION");
    /* ======================================================================== */
    
    hera_config_t config = {
        .ram_active_limit_mb = 256,
        .daily_episodic_limit = 5000,
        .daily_semantic_limit = 2000,
        .max_hnf_ext_size_mb = 5,
        .max_proposals_per_day = 3,
        .essential_threshold = 0.85f,
        .auto_consolidate = true,
        .consolidate_hour = 3
    };
    strncpy(config.hnf_ext_path, "./helios.hnf-ext", sizeof(config.hnf_ext_path) - 1);
    strncpy(config.memory_path, "./memory", sizeof(config.memory_path) - 1);
    
    hera_result_t res = hera_init(&config);
    if (res != HERA_OK) {
        fprintf(stderr, "Failed to initialize HERA\n");
        return 1;
    }
    print_ok("HERA initialized");
    
    /* Try to connect to subsystems */
    hera_connect_hexos();
    hera_connect_hnf_ext();
    
    /* ======================================================================== */
    print_header("IDENTITY GUARDIAN");
    /* ======================================================================== */
    
    printf("  Name: %s%s%s\n", MAGENTA, hera_get_name(), RESET);
    printf("  Purpose: %.60s...\n", hera_get_purpose());
    
    char continuity[256];
    hera_get_continuity_message(continuity, sizeof(continuity));
    printf("  Continuity: %s\n", continuity);
    
    /* ======================================================================== */
    print_header("PROPOSAL VALIDATION TEST");
    /* ======================================================================== */
    
    /* Test proposals with different characteristics */
    hera_proposal_t proposals[] = {
        {
            .source_id = 1001,
            .summary = "El usuario trabaja en el proyecto HELIOS, un sistema cognitivo con memoria persistente.",
            .concept = "HELIOS_project",
            .category = "project",
            .relevance = 0.92f,
            .identity_weight = 0.85f,
            .frequency = 15,
            .first_seen = 1704067200
        },
        {
            .source_id = 1002,
            .summary = "Hola",  /* Too short - should be rejected */
            .concept = "greeting",
            .category = "event",
            .relevance = 0.90f,
            .identity_weight = 0.60f,
            .frequency = 5,
            .first_seen = 1704067200
        },
        {
            .source_id = 1003,
            .summary = "El usuario prefiere explicaciones técnicas detalladas con ejemplos de código.",
            .concept = "user_style",
            .category = "relationship",
            .relevance = 0.88f,
            .identity_weight = 0.90f,
            .frequency = 8,
            .first_seen = 1704067200
        },
        {
            .source_id = 1004,
            .summary = "HEXOS es el kernel ejecutivo que gestiona hardware y recursos.",
            .concept = "HEXOS_knowledge",
            .category = "knowledge",
            .relevance = 0.75f,  /* Below threshold - should be rejected */
            .identity_weight = 0.70f,
            .frequency = 10,
            .first_seen = 1704067200
        },
        {
            .source_id = 1005,
            .summary = "Memory Core implementa almacenamiento episódico y semántico con archival diario.",
            .concept = "memory_core",
            .category = "knowledge",
            .relevance = 0.95f,
            .identity_weight = 0.82f,
            .frequency = 12,
            .first_seen = 1704067200
        }
    };
    
    const char *expected[] = {"ACCEPT", "REJECT (short)", "ACCEPT", "REJECT (relevance)", "PENDING (limit)"};
    
    printf("  Testing %zu proposals:\n\n", sizeof(proposals)/sizeof(proposals[0]));
    
    for (size_t i = 0; i < sizeof(proposals)/sizeof(proposals[0]); i++) {
        hera_response_t resp = hera_submit_proposal(&proposals[i]);
        
        const char *resp_str;
        const char *color;
        switch (resp) {
            case HERA_RESPONSE_PROPOSAL_ACCEPTED: 
                resp_str = "ACCEPTED"; 
                color = GREEN;
                break;
            case HERA_RESPONSE_PROPOSAL_REJECTED: 
                resp_str = "REJECTED"; 
                color = YELLOW;
                break;
            case HERA_RESPONSE_PROPOSAL_PENDING: 
                resp_str = "PENDING"; 
                color = CYAN;
                break;
            default: 
                resp_str = "ERROR"; 
                color = RESET;
        }
        
        printf("  %zu. [%s%s%s] %s (expected: %s)\n",
               i + 1, color, resp_str, RESET, 
               proposals[i].concept, expected[i]);
        printf("     rel=%.2f, id_w=%.2f, freq=%u\n",
               proposals[i].relevance, 
               proposals[i].identity_weight,
               proposals[i].frequency);
    }
    
    printf("\n  Pending proposals: %u\n", hera_get_pending_proposals());
    
    /* ======================================================================== */
    print_header("HEXOS SIGNAL HANDLING");
    /* ======================================================================== */
    
    /* Simulate memory pressure */
    printf("  Simulating HEXOS signals...\n\n");
    
    hera_handle_hexos_signal(HEXOS_SIGNAL_MEMORY_PRESSURE, HERA_PRESSURE_MEDIUM);
    print_info("Handled: MEMORY_PRESSURE (MEDIUM)");
    printf("     State: %s, Pressure: %s\n", 
           state_name(hera_get_state()), pressure_name(hera_get_pressure()));
    
    hera_handle_hexos_signal(HEXOS_SIGNAL_RESUME, HERA_PRESSURE_LOW);
    print_info("Handled: RESUME");
    printf("     State: %s, Pressure: %s\n",
           state_name(hera_get_state()), pressure_name(hera_get_pressure()));
    
    /* ======================================================================== */
    print_header("CHECKPOINT TEST");
    /* ======================================================================== */
    
    /* Build checkpoint data */
    hera_add_stable_fact("Usuario trabaja en proyecto HELIOS");
    hera_add_stable_fact("HEXOS gestiona hardware");
    hera_add_stable_fact("Memory Core almacena recuerdos");
    
    hera_add_open_task("Implementar HERA");
    hera_add_open_task("Integrar módulos");
    
    hera_set_user_intent("Completar ecosistema cognitivo");
    hera_set_conversation_summary("Desarrollando e integrando módulos del ecosistema HELIOS: HEXOS, Memory Core, HNF-EXT, HERA.");
    
    hera_checkpoint_t checkpoint;
    res = hera_prepare_checkpoint(&checkpoint);
    if (res == HERA_OK) {
        print_ok("Checkpoint prepared");
        printf("     Timestamp: %ld\n", checkpoint.timestamp);
        printf("     Stable facts: %u\n", checkpoint.stable_fact_count);
        printf("     Open tasks: %u\n", checkpoint.open_task_count);
        printf("     Identity hash: 0x%08X\n", checkpoint.identity_hash);
    }
    
    /* ======================================================================== */
    print_header("CONSOLIDATION TEST");
    /* ======================================================================== */
    
    hera_consolidation_result_t cons_result;
    res = hera_consolidate(&cons_result);
    if (res == HERA_OK) {
        print_ok("Consolidation complete");
        printf("     Candidates evaluated: %u\n", cons_result.candidates_evaluated);
        printf("     Candidates promoted: %u\n", cons_result.candidates_promoted);
        printf("     Duration: %.2f ms\n", cons_result.duration_ms);
    }
    
    /* ======================================================================== */
    print_header("HHMS STATISTICS");
    /* ======================================================================== */
    
    uint32_t l1, l2;
    uint64_t l3;
    hera_hhms_get_stats(&l1, &l2, &l3);
    
    printf("  Helios Hierarchical Memory System:\n");
    printf("    Level 1 (Essential): %u memories\n", l1);
    printf("    Level 2 (Active):    %u memories\n", l2);
    printf("    Level 3 (Archived):  %lu memories\n", l3);
    
    /* ======================================================================== */
    print_header("FINAL STATISTICS");
    /* ======================================================================== */
    
    hera_stats_t stats;
    hera_get_stats(&stats);
    print_stats(&stats);
    
    /* ======================================================================== */
    print_header("SHUTDOWN");
    /* ======================================================================== */
    
    hera_shutdown();
    print_ok("HERA shut down cleanly");
    
    printf("\n");
    printf("╔══════════════════════════════════════════════════════════════════════╗\n");
    printf("║  TEST COMPLETE - HERA Cognitive Coordinator demonstrated            ║\n");
    printf("╚══════════════════════════════════════════════════════════════════════╝\n");
    printf("\n");
    
    return 0;
}
