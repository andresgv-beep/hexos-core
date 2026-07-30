/*
 * MEMORY CORE v3.0 - Test Program
 * HELIOS Cognitive Ecosystem
 * 
 * Demonstrates Memory Core functionality and HEXOS integration
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "../include/memory_core.h"

/* ANSI colors */
#define ANSI_GREEN   "\033[32m"
#define ANSI_YELLOW  "\033[33m"
#define ANSI_CYAN    "\033[36m"
#define ANSI_RESET   "\033[0m"
#define ANSI_BOLD    "\033[1m"

static void print_header(const char *title) {
    printf("\n%s%s=== %s ===%s\n\n", ANSI_BOLD, ANSI_CYAN, title, ANSI_RESET);
}

static void print_ok(const char *msg) {
    printf("  %s✓%s %s\n", ANSI_GREEN, ANSI_RESET, msg);
}

static void print_info(const char *msg) {
    printf("  %s→%s %s\n", ANSI_YELLOW, ANSI_RESET, msg);
}

static void print_stats(mc_stats_t *stats) {
    const char *pressure_str[] = {"LOW", "MEDIUM", "HIGH", "CRITICAL"};
    
    printf("\n  ┌─────────────────────────────────────────┐\n");
    printf("  │ MEMORY CORE STATISTICS                  │\n");
    printf("  ├─────────────────────────────────────────┤\n");
    printf("  │ Active Items:     %8lu              │\n", stats->active_items);
    printf("  │ Active Size:      %8lu MB           │\n", stats->active_size_mb);
    printf("  │ Active Limit:     %8lu MB           │\n", stats->active_limit_mb);
    printf("  │ Index Items:      %8lu              │\n", stats->index_items);
    printf("  │ Candidates:       %8u              │\n", stats->candidates_pending);
    printf("  │ Pressure:         %8s              │\n", pressure_str[stats->pressure_level]);
    printf("  │ Avg Query:        %8.2f ms          │\n", stats->avg_query_ms);
    printf("  └─────────────────────────────────────────┘\n");
}

int main(int argc, char *argv[]) {
    (void)argc;
    (void)argv;
    
    printf("\n");
    printf("╔══════════════════════════════════════════════════════════════════════╗\n");
    printf("║                                                                      ║\n");
    printf("║    ███╗   ███╗███████╗███╗   ███╗ ██████╗ ██████╗ ██╗   ██╗         ║\n");
    printf("║    ████╗ ████║██╔════╝████╗ ████║██╔═══██╗██╔══██╗╚██╗ ██╔╝         ║\n");
    printf("║    ██╔████╔██║█████╗  ██╔████╔██║██║   ██║██████╔╝ ╚████╔╝          ║\n");
    printf("║    ██║╚██╔╝██║██╔══╝  ██║╚██╔╝██║██║   ██║██╔══██╗  ╚██╔╝           ║\n");
    printf("║    ██║ ╚═╝ ██║███████╗██║ ╚═╝ ██║╚██████╔╝██║  ██║   ██║            ║\n");
    printf("║    ╚═╝     ╚═╝╚══════╝╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝            ║\n");
    printf("║                                                                      ║\n");
    printf("║    CORE v3.0 - HELIOS Cognitive Ecosystem                           ║\n");
    printf("║    \"Los recuerdos viven aquí\"                                        ║\n");
    printf("║                                                                      ║\n");
    printf("╚══════════════════════════════════════════════════════════════════════╝\n");
    
    /* ======================================================================== */
    print_header("INITIALIZATION");
    /* ======================================================================== */
    
    mc_config_t config = {
        .ram_active_limit_mb = 100,
        .daily_episodic_limit = 1000,
        .daily_semantic_limit = 500,
        .max_query_results = 50,
        .embedding_dimension = 384,
        .auto_archive = true,
        .enable_embeddings = false,
        .archive_hour = 3
    };
    strncpy(config.base_path, ".", sizeof(config.base_path) - 1);
    strncpy(config.memory_path, "./test_memory", sizeof(config.memory_path) - 1);
    
    mc_result_t res = mc_init(&config);
    if (res != MC_OK) {
        fprintf(stderr, "Failed to initialize Memory Core: %d\n", res);
        return 1;
    }
    print_ok("Memory Core initialized");
    
    /* Try to connect to HEXOS */
    res = mc_connect_hexos();
    if (res == MC_OK) {
        print_ok("Connected to HEXOS IPC");
    }
    
    /* ======================================================================== */
    print_header("EPISODIC MEMORY TEST");
    /* ======================================================================== */
    
    /* Store some episodic events */
    mc_episodic_event_t events[] = {
        {
            .type = "conversation",
            .text = "Usuario explicó el proyecto Helios y su arquitectura modular.",
            .relevance = 0.85f,
            .tag_count = 3,
            .entity_count = 2
        },
        {
            .type = "observation",
            .text = "El usuario prefiere respuestas técnicas y detalladas.",
            .relevance = 0.75f,
            .tag_count = 2,
            .entity_count = 1
        },
        {
            .type = "conversation", 
            .text = "Discutimos sobre Memory Core y cómo almacena recuerdos episódicos.",
            .relevance = 0.90f,
            .tag_count = 2,
            .entity_count = 2
        },
        {
            .type = "task",
            .text = "Implementar el módulo HERA para coordinar la memoria.",
            .relevance = 0.95f,
            .tag_count = 1,
            .entity_count = 1
        },
        {
            .type = "observation",
            .text = "El sistema HEXOS ya está funcionando y monitoreando recursos.",
            .relevance = 0.80f,
            .tag_count = 2,
            .entity_count = 1
        }
    };
    
    strcpy(events[0].tags[0], "helios");
    strcpy(events[0].tags[1], "arquitectura");
    strcpy(events[0].tags[2], "modular");
    strcpy(events[0].entities[0], "Helios");
    strcpy(events[0].entities[1], "HEXOS");
    strcpy(events[0].context_id, "session_test_001");
    
    uint64_t stored_ids[5];
    for (int i = 0; i < 5; i++) {
        res = mc_store_episodic(&events[i], &stored_ids[i]);
        if (res == MC_OK) {
            char buf[64];
            snprintf(buf, sizeof(buf), "Stored event %d (ID: %lu)", i + 1, stored_ids[i]);
            print_ok(buf);
        }
    }
    
    /* Retrieve an event */
    mc_episodic_event_t retrieved;
    res = mc_get_episodic(stored_ids[0], &retrieved);
    if (res == MC_OK) {
        printf("\n  Retrieved event:\n");
        printf("    Type: %s\n", retrieved.type);
        printf("    Text: %.60s...\n", retrieved.text);
        printf("    Relevance: %.2f\n", retrieved.relevance);
    }
    
    /* Get recent events */
    mc_episodic_event_t recent[3];
    uint32_t recent_count;
    res = mc_get_recent_episodic(3, recent, &recent_count);
    if (res == MC_OK) {
        printf("\n  Recent events (%u):\n", recent_count);
        for (uint32_t i = 0; i < recent_count; i++) {
            printf("    %u. [%s] %.50s...\n", i + 1, recent[i].type, recent[i].text);
        }
    }
    
    /* ======================================================================== */
    print_header("SEMANTIC MEMORY TEST");
    /* ======================================================================== */
    
    /* Store some concepts */
    mc_concept_t concepts[] = {
        { .name = "HEXOS", .category = "system", .importance = 0.95f },
        { .name = "Memory Core", .category = "module", .importance = 0.90f },
        { .name = "HERA", .category = "module", .importance = 0.90f },
        { .name = "HNF-EXT", .category = "format", .importance = 0.85f },
        { .name = "Cognitive Kernel", .category = "module", .importance = 0.88f },
        { .name = "IPC Bus", .category = "infrastructure", .importance = 0.80f }
    };
    
    uint64_t concept_ids[6];
    for (int i = 0; i < 6; i++) {
        res = mc_store_concept(&concepts[i], &concept_ids[i]);
        if (res == MC_OK) {
            char buf[64];
            snprintf(buf, sizeof(buf), "Stored concept: %s (ID: %lu)", 
                     concepts[i].name, concept_ids[i]);
            print_ok(buf);
        }
    }
    
    /* Store some relations */
    mc_relation_t relations[] = {
        { .source_id = concept_ids[0], .target_id = concept_ids[1], 
          .relation_type = "supervises", .strength = 0.9f },
        { .source_id = concept_ids[0], .target_id = concept_ids[2], 
          .relation_type = "supervises", .strength = 0.9f },
        { .source_id = concept_ids[2], .target_id = concept_ids[1], 
          .relation_type = "uses", .strength = 0.85f },
        { .source_id = concept_ids[1], .target_id = concept_ids[3], 
          .relation_type = "writes_to", .strength = 0.8f },
        { .source_id = concept_ids[0], .target_id = concept_ids[5], 
          .relation_type = "provides", .strength = 0.95f }
    };
    
    for (int i = 0; i < 5; i++) {
        mc_store_relation(&relations[i]);
    }
    print_ok("Stored 5 relations between concepts");
    
    /* Find concept by name */
    mc_concept_t found;
    res = mc_find_concept("HEXOS", &found);
    if (res == MC_OK) {
        printf("\n  Found concept:\n");
        printf("    Name: %s\n", found.name);
        printf("    Category: %s\n", found.category);
        printf("    Importance: %.2f\n", found.importance);
        printf("    Frequency: %u\n", found.frequency);
    }
    
    /* Get relations */
    mc_relation_t found_rels[10];
    uint32_t rel_count;
    res = mc_get_relations(concept_ids[0], found_rels, 10, &rel_count);
    if (res == MC_OK) {
        printf("\n  Relations for HEXOS (%u):\n", rel_count);
        for (uint32_t i = 0; i < rel_count; i++) {
            printf("    → %s (strength: %.2f)\n", 
                   found_rels[i].relation_type, found_rels[i].strength);
        }
    }
    
    /* ======================================================================== */
    print_header("QUERY ENGINE TEST");
    /* ======================================================================== */
    
    mc_query_t query = {
        .text = "Memory",
        .type_filter = -1,  /* All types */
        .min_relevance = 0.0f,
        .max_results = 10,
        .semantic_search = false
    };
    
    mc_query_result_t result;
    res = mc_query(&query, &result);
    if (res == MC_OK) {
        printf("  Query: \"%s\"\n", query.text);
        printf("  Results: %u (in %.2f ms)\n\n", result.count, result.query_time_ms);
        
        for (uint32_t i = 0; i < result.count; i++) {
            const char *type_str[] = {"EPISODIC", "SEMANTIC", "PROJECT", "IDENTITY"};
            printf("    %u. [%s] ID=%lu relevance=%.2f\n", 
                   i + 1, type_str[result.items[i].type],
                   result.items[i].id, result.items[i].relevance);
        }
        
        mc_free_query_result(&result);
    }
    
    /* ======================================================================== */
    print_header("HNF-EXT CANDIDATE PREPARATION");
    /* ======================================================================== */
    
    /* Mark high-relevance item as candidate */
    mc_index_mark_candidate(stored_ids[3]);  /* The task about HERA */
    print_ok("Marked task as HNF-EXT candidate");
    
    /* Prepare proposal */
    mc_core_proposal_t proposal;
    res = mc_prepare_proposal(stored_ids[3], &proposal);
    if (res == MC_OK) {
        printf("\n  Core Memory Proposal:\n");
        printf("    Summary: %.60s...\n", proposal.summary);
        printf("    Category: %s\n", proposal.category);
        printf("    Relevance: %.2f\n", proposal.relevance_absolute);
        printf("    Identity Weight: %.2f\n", proposal.identity_weight);
        printf("    Justification: %s\n", proposal.justification);
    }
    
    /* ======================================================================== */
    print_header("CHECKPOINT TEST");
    /* ======================================================================== */
    
    mc_checkpoint_t checkpoint;
    res = mc_prepare_checkpoint(&checkpoint);
    if (res == MC_OK) {
        char ts_buf[32];
        mc_format_timestamp(checkpoint.timestamp, ts_buf, sizeof(ts_buf));
        printf("  Checkpoint created: %s\n", ts_buf);
        printf("  Hot items: %lu\n", checkpoint.hot_item_count);
        printf("  Pending candidates: %u\n", checkpoint.pending_candidate_count);
        mc_free_checkpoint(&checkpoint);
        print_ok("Checkpoint prepared and freed");
    }
    
    /* ======================================================================== */
    print_header("STATISTICS");
    /* ======================================================================== */
    
    mc_stats_t stats;
    mc_get_stats(&stats);
    print_stats(&stats);
    
    /* ======================================================================== */
    print_header("INTEGRITY CHECK");
    /* ======================================================================== */
    
    uint32_t errors;
    res = mc_verify_integrity(false, &errors);
    if (res == MC_OK) {
        char buf[64];
        snprintf(buf, sizeof(buf), "Integrity check: %u errors found", errors);
        print_info(buf);
    }
    
    /* ======================================================================== */
    print_header("ARCHIVE TEST");
    /* ======================================================================== */
    
    res = mc_archive_day();
    if (res == MC_OK) {
        print_ok("Day archived to disk");
    }
    
    /* ======================================================================== */
    print_header("SHUTDOWN");
    /* ======================================================================== */
    
    mc_disconnect_hexos();
    mc_shutdown();
    print_ok("Memory Core shut down cleanly");
    
    printf("\n");
    printf("╔══════════════════════════════════════════════════════════════════════╗\n");
    printf("║  TEST COMPLETE - All Memory Core features demonstrated              ║\n");
    printf("╚══════════════════════════════════════════════════════════════════════╝\n");
    printf("\n");
    
    return 0;
}
