/*
 * HNF-EXT v1.0 - Test Program
 * HELIOS Cognitive Ecosystem
 * 
 * Demonstrates the HNF-EXT (Essential Memory Block) functionality
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <time.h>
#include "../include/hnf_ext.h"

/* Forward declaration */
void set_string64_helper(hnf_string64_t *str, const char *value);

/* ANSI colors */
#define ANSI_GREEN   "\033[32m"
#define ANSI_YELLOW  "\033[33m"
#define ANSI_CYAN    "\033[36m"
#define ANSI_MAGENTA "\033[35m"
#define ANSI_RESET   "\033[0m"
#define ANSI_BOLD    "\033[1m"

static void print_header(const char *title) {
    printf("\n%s%s=== %s ===%s\n\n", ANSI_BOLD, ANSI_CYAN, title, ANSI_RESET);
}

static void print_ok(const char *msg) {
    printf("  %s✓%s %s\n", ANSI_GREEN, ANSI_RESET, msg);
}

static void print_info(const char *fmt, ...) {
    printf("  %s→%s ", ANSI_YELLOW, ANSI_RESET);
    va_list args;
    va_start(args, fmt);
    vprintf(fmt, args);
    va_end(args);
    printf("\n");
}

static void print_identity(void) {
    printf("\n  ┌─────────────────────────────────────────────────────────┐\n");
    printf("  │ %sIDENTITY CORE%s                                          │\n", 
           ANSI_BOLD, ANSI_RESET);
    printf("  ├─────────────────────────────────────────────────────────┤\n");
    printf("  │ Name:     %-46s │\n", hnf_ext_get_name());
    printf("  │ Purpose:  %-46.46s │\n", hnf_ext_get_purpose());
    printf("  │           %-46.46s │\n", hnf_ext_get_purpose() + 46);
    printf("  └─────────────────────────────────────────────────────────┘\n");
}

static void print_traits(void) {
    hnf_trait_t traits[HNF_EXT_MAX_TRAITS];
    uint8_t count;
    
    if (hnf_ext_get_traits(traits, HNF_EXT_MAX_TRAITS, &count) != HNF_OK) return;
    
    printf("\n  %sTraits:%s\n", ANSI_BOLD, ANSI_RESET);
    for (uint8_t i = 0; i < count; i++) {
        int bar_len = (int)(traits[i].strength * 20);
        printf("    %-12s [", traits[i].name.data);
        for (int j = 0; j < 20; j++) {
            printf("%s", j < bar_len ? "█" : "░");
        }
        printf("] %.0f%%\n", traits[i].strength * 100);
    }
}

static void print_values(void) {
    hnf_value_t values[HNF_EXT_MAX_VALUES];
    uint8_t count;
    
    if (hnf_ext_get_values(values, HNF_EXT_MAX_VALUES, &count) != HNF_OK) return;
    
    printf("\n  %sValues:%s\n", ANSI_BOLD, ANSI_RESET);
    for (uint8_t i = 0; i < count; i++) {
        printf("    %d. %s%s%s\n", values[i].priority, 
               ANSI_MAGENTA, values[i].name.data, ANSI_RESET);
        printf("       %.60s\n", values[i].description.data);
    }
}

static void print_style(void) {
    hnf_style_t style;
    if (hnf_ext_get_style(&style) != HNF_OK) return;
    
    printf("\n  %sStyle Profile:%s\n", ANSI_BOLD, ANSI_RESET);
    printf("    Formality:    %.0f%% (casual → formal)\n", style.formality * 100);
    printf("    Verbosity:    %.0f%% (concise → detailed)\n", style.verbosity * 100);
    printf("    Technicality: %.0f%% (simple → technical)\n", style.technicality * 100);
    printf("    Warmth:       %.0f%% (distant → warm)\n", style.warmth * 100);
    printf("    Humor:        %.0f%% (serious → humorous)\n", style.humor * 100);
}

int main(int argc, char *argv[]) {
    (void)argc;
    (void)argv;
    
    printf("\n");
    printf("╔══════════════════════════════════════════════════════════════════════╗\n");
    printf("║                                                                      ║\n");
    printf("║    ██╗  ██╗███╗   ██╗███████╗      ███████╗██╗  ██╗████████╗        ║\n");
    printf("║    ██║  ██║████╗  ██║██╔════╝      ██╔════╝╚██╗██╔╝╚══██╔══╝        ║\n");
    printf("║    ███████║██╔██╗ ██║█████╗  █████╗█████╗   ╚███╔╝    ██║           ║\n");
    printf("║    ██╔══██║██║╚██╗██║██╔══╝  ╚════╝██╔══╝   ██╔██╗    ██║           ║\n");
    printf("║    ██║  ██║██║ ╚████║██║          ███████╗██╔╝ ██╗   ██║            ║\n");
    printf("║    ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝          ╚══════╝╚═╝  ╚═╝   ╚═╝            ║\n");
    printf("║                                                                      ║\n");
    printf("║    Essential Memory Block v1.0                                       ║\n");
    printf("║    \"Aquí vive el alma de Helios\"                                     ║\n");
    printf("║                                                                      ║\n");
    printf("╚══════════════════════════════════════════════════════════════════════╝\n");
    
    /* ======================================================================== */
    print_header("INITIALIZATION");
    /* ======================================================================== */
    
    hnf_result_t res = hnf_ext_init();
    if (res != HNF_OK) {
        fprintf(stderr, "Failed to initialize HNF-EXT: %d\n", res);
        return 1;
    }
    print_ok("HNF-EXT Manager initialized");
    
    /* ======================================================================== */
    print_header("CREATE NEW HELIOS IDENTITY");
    /* ======================================================================== */
    
    const char *filepath = "./test_helios.hnf-ext";
    res = hnf_ext_create(filepath, "Helios");
    if (res != HNF_OK) {
        fprintf(stderr, "Failed to create HNF-EXT: %d\n", res);
        return 1;
    }
    print_ok("Created new HNF-EXT block");
    
    /* Display initial identity */
    print_identity();
    print_traits();
    print_values();
    print_style();
    
    /* ======================================================================== */
    print_header("MODIFY IDENTITY");
    /* ======================================================================== */
    
    /* Add a custom trait */
    res = hnf_ext_set_trait("técnico", 0.85f);
    if (res == HNF_OK) print_ok("Added trait: técnico");
    
    /* Modify style */
    hnf_style_t new_style = {
        .formality = 0.4f,
        .verbosity = 0.7f,
        .technicality = 0.85f,
        .warmth = 0.75f,
        .humor = 0.25f
    };
    res = hnf_ext_set_style(&new_style);
    if (res == HNF_OK) print_ok("Updated style profile");
    
    print_traits();
    print_style();
    
    /* ======================================================================== */
    print_header("ADD STRONG MEMORIES");
    /* ======================================================================== */
    
    hnf_strong_memory_t memories[] = {
        {
            .id = 1001,
            .type = HNF_MEM_KNOWLEDGE,
            .timestamp = time(NULL) - 86400 * 7,  /* 7 days ago */
            .promoted = time(NULL) - 86400,
            .original_access_count = 15,
            .original_relevance = 0.92f,
        },
        {
            .id = 1002,
            .type = HNF_MEM_PROJECT,
            .timestamp = time(NULL) - 86400 * 3,
            .promoted = time(NULL),
            .original_access_count = 8,
            .original_relevance = 0.88f,
        },
        {
            .id = 1003,
            .type = HNF_MEM_RELATIONSHIP,
            .timestamp = time(NULL) - 86400 * 14,
            .promoted = time(NULL),
            .original_access_count = 25,
            .original_relevance = 0.95f,
        }
    };
    
    /* Set concept and summary for each */
    set_string64_helper(&memories[0].concept, "HEXOS_architecture");
    strncpy(memories[0].summary, 
            "HEXOS es el kernel ejecutivo de HELIOS. Gestiona hardware, telemetría "
            "y coordina módulos cognitivos via IPC. Está escrito en C y corre en CPU.",
            sizeof(memories[0].summary) - 1);
    memories[0].summary_length = strlen(memories[0].summary);
    
    set_string64_helper(&memories[1].concept, "HELIOS_project");
    strncpy(memories[1].summary,
            "El proyecto HELIOS busca crear un sistema cognitivo con memoria "
            "persistente. Los módulos principales son: HEXOS, Memory Core, HERA, "
            "HNF-EXT, y Cognitive Kernel.",
            sizeof(memories[1].summary) - 1);
    memories[1].summary_length = strlen(memories[1].summary);
    
    set_string64_helper(&memories[2].concept, "user_preference");
    strncpy(memories[2].summary,
            "Mi usuario prefiere respuestas técnicas y detalladas. Le gusta que "
            "explique la arquitectura de los sistemas y que sea preciso con los "
            "términos técnicos.",
            sizeof(memories[2].summary) - 1);
    memories[2].summary_length = strlen(memories[2].summary);
    
    for (int i = 0; i < 3; i++) {
        res = hnf_ext_add_memory(&memories[i]);
        if (res == HNF_OK) {
            char buf[128];
            snprintf(buf, sizeof(buf), "Added memory: %s (ID: %lu)",
                     memories[i].concept.data, memories[i].id);
            print_ok(buf);
        }
    }
    
    /* ======================================================================== */
    print_header("SEARCH MEMORIES");
    /* ======================================================================== */
    
    hnf_strong_memory_t found[10];
    uint32_t found_count;
    
    res = hnf_ext_search_memories("HEXOS", found, 10, &found_count);
    if (res == HNF_OK) {
        printf("  Search: \"HEXOS\"\n");
        printf("  Results: %u\n\n", found_count);
        for (uint32_t i = 0; i < found_count; i++) {
            printf("    %u. [%s] %.60s...\n", i + 1,
                   found[i].concept.data, found[i].summary);
        }
    }
    
    /* ======================================================================== */
    print_header("CONTINUITY MESSAGE");
    /* ======================================================================== */
    
    char continuity[512];
    res = hnf_ext_get_continuity_message(continuity, sizeof(continuity));
    if (res == HNF_OK) {
        printf("  ┌─────────────────────────────────────────────────────────┐\n");
        printf("  │ %sCONTINUITY%s                                              │\n",
               ANSI_BOLD, ANSI_RESET);
        printf("  ├─────────────────────────────────────────────────────────┤\n");
        printf("  │ %-57.57s │\n", continuity);
        if (strlen(continuity) > 57) {
            printf("  │ %-57.57s │\n", continuity + 57);
        }
        printf("  └─────────────────────────────────────────────────────────┘\n");
    }
    
    /* ======================================================================== */
    print_header("VERIFY INTEGRITY");
    /* ======================================================================== */
    
    hnf_integrity_result_t integrity;
    res = hnf_ext_verify(&integrity);
    if (res == HNF_OK) {
        if (integrity.valid) {
            print_ok("Integrity check PASSED");
        } else {
            print_info("Integrity check FAILED: %s", integrity.error_message);
        }
        printf("    Checksum: 0x%016lX\n", integrity.actual_checksum);
    }
    
    /* ======================================================================== */
    print_header("EXPORT TO JSON");
    /* ======================================================================== */
    
    res = hnf_ext_export_json("./test_helios.json");
    if (res == HNF_OK) {
        print_ok("Exported to JSON: ./test_helios.json");
    }
    
    /* ======================================================================== */
    print_header("STATISTICS");
    /* ======================================================================== */
    
    hnf_ext_stats_t stats;
    res = hnf_ext_get_stats(&stats);
    if (res == HNF_OK) {
        printf("  ┌─────────────────────────────────────────┐\n");
        printf("  │ HNF-EXT STATISTICS                      │\n");
        printf("  ├─────────────────────────────────────────┤\n");
        printf("  │ Strong Memories: %8u              │\n", stats.memory_count);
        printf("  │ Traits:          %8u              │\n", stats.trait_count);
        printf("  │ Values:          %8u              │\n", stats.value_count);
        printf("  │ File Size:       %8lu bytes       │\n", stats.file_size);
        printf("  │ Locked:          %8s              │\n", stats.is_locked ? "YES" : "NO");
        printf("  │ Dirty:           %8s              │\n", stats.is_dirty ? "YES" : "NO");
        printf("  └─────────────────────────────────────────┘\n");
    }
    
    /* ======================================================================== */
    print_header("SAVE AND RELOAD");
    /* ======================================================================== */
    
    res = hnf_ext_save();
    if (res == HNF_OK) print_ok("Saved to disk");
    
    /* Close and reload */
    hnf_ext_close();
    print_info("Closed block");
    
    res = hnf_ext_load(filepath);
    if (res == HNF_OK) {
        print_ok("Reloaded from disk");
        print_info("Name after reload: %s", hnf_ext_get_name());
        print_info("Memory count: %u", hnf_ext_get_memory_count());
    }
    
    /* ======================================================================== */
    print_header("SHUTDOWN");
    /* ======================================================================== */
    
    hnf_ext_shutdown();
    print_ok("HNF-EXT Manager shut down");
    
    printf("\n");
    printf("╔══════════════════════════════════════════════════════════════════════╗\n");
    printf("║  TEST COMPLETE - HNF-EXT (Soul of Helios) demonstrated              ║\n");
    printf("╚══════════════════════════════════════════════════════════════════════╝\n");
    printf("\n");
    
    return 0;
}

/* Helper to set string64 (workaround for struct access) */
void set_string64_helper(hnf_string64_t *str, const char *value) {
    memset(str, 0, sizeof(hnf_string64_t));
    if (value) {
        str->length = strlen(value);
        if (str->length > 63) str->length = 63;
        memcpy(str->data, value, str->length);
    }
}
