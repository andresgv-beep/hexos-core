/*
 * COGNITIVE KERNEL v3.0 (STUB) - Test Program
 * HELIOS Cognitive Ecosystem
 * 
 * Demonstrates the cognitive processing flow
 */

#include <stdio.h>
#include <string.h>
#include "../include/cognitive_kernel.h"

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

static void print_turn_summary(ck_turn_t *turn) {
    printf("\n  ┌─────────────────────────────────────────────────────────────┐\n");
    printf("  │ %sTURN SUMMARY%s                                                │\n", BOLD, RESET);
    printf("  ├─────────────────────────────────────────────────────────────┤\n");
    printf("  │ Input tokens:    %5u    Output tokens:   %5u           │\n",
           turn->input.token_count, turn->response.token_count);
    printf("  │ Intent:          %-12s  Confidence:    %.2f           │\n",
           ck_intent_name(turn->intent.primary), turn->intent.confidence);
    printf("  │ Entities:        %5u    Topics:          %5u           │\n",
           turn->input.entity_count, turn->tags.topic_count);
    printf("  │ Memories used:   %5u    Reasoning steps: %5u           │\n",
           turn->context.memory_count, turn->reasoning_step_count);
    printf("  │ Learnings:       %5u    Has proposal:    %5s           │\n",
           turn->learning_count, turn->has_proposal ? "YES" : "NO");
    printf("  │ Coherence:       %.2f    Time:            %5ld ms        │\n",
           turn->response.coherence_score, turn->end_time - turn->start_time);
    printf("  └─────────────────────────────────────────────────────────────┘\n");
}

int main(void) {
    printf("\n");
    printf("╔══════════════════════════════════════════════════════════════════════╗\n");
    printf("║                                                                      ║\n");
    printf("║     ██████╗ ██████╗  ██████╗ ███╗   ██╗██╗████████╗██╗██╗   ██╗     ║\n");
    printf("║    ██╔════╝██╔═══██╗██╔════╝ ████╗  ██║██║╚══██╔══╝██║██║   ██║     ║\n");
    printf("║    ██║     ██║   ██║██║  ███╗██╔██╗ ██║██║   ██║   ██║██║   ██║     ║\n");
    printf("║    ██║     ██║   ██║██║   ██║██║╚██╗██║██║   ██║   ██║╚██╗ ██╔╝     ║\n");
    printf("║    ╚██████╗╚██████╔╝╚██████╔╝██║ ╚████║██║   ██║   ██║ ╚████╔╝      ║\n");
    printf("║     ╚═════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝╚═╝   ╚═╝   ╚═╝  ╚═══╝       ║\n");
    printf("║                                                                      ║\n");
    printf("║    KERNEL v3.0 (STUB)                                               ║\n");
    printf("║    \"Donde Helios piensa\"                                            ║\n");
    printf("║                                                                      ║\n");
    printf("╚══════════════════════════════════════════════════════════════════════╝\n");
    
    /* ======================================================================== */
    print_header("INITIALIZATION");
    /* ======================================================================== */
    
    ck_result_t res = ck_init(NULL);
    if (res != CK_OK) {
        fprintf(stderr, "Failed to initialize CK\n");
        return 1;
    }
    print_ok("Cognitive Kernel initialized (STUB MODE)");
    
    ck_connect_hera();
    ck_connect_hexos();
    
    /* ======================================================================== */
    print_header("IDENTITY");
    /* ======================================================================== */
    
    printf("  Name: %s%s%s\n", MAGENTA, ck_get_name(), RESET);
    printf("  Purpose: %s\n", ck_get_purpose());
    
    ck_style_t style;
    ck_get_style(&style);
    printf("\n  Style Profile:\n");
    printf("    Formality:    %.0f%%\n", style.formality * 100);
    printf("    Verbosity:    %.0f%%\n", style.verbosity * 100);
    printf("    Technicality: %.0f%%\n", style.technicality * 100);
    printf("    Warmth:       %.0f%%\n", style.warmth * 100);
    printf("    Humor:        %.0f%%\n", style.humor * 100);
    
    /* ======================================================================== */
    print_header("TURN PROCESSING TEST");
    /* ======================================================================== */
    
    const char *test_inputs[] = {
        "Hola, ¿cómo estás?",
        "¿Qué es HELIOS y cómo funciona su sistema de memoria?",
        "Cuéntame sobre el proyecto en el que estamos trabajando",
        "Recuerda que prefiero explicaciones técnicas detalladas",
        "Crea un resumen del ecosistema cognitivo"
    };
    
    for (size_t i = 0; i < sizeof(test_inputs)/sizeof(test_inputs[0]); i++) {
        printf("  %s─────────────────────────────────────────────────%s\n", CYAN, RESET);
        printf("  %sTurn %zu%s: \"%.50s%s\"\n", BOLD, i + 1, RESET, test_inputs[i],
               strlen(test_inputs[i]) > 50 ? "..." : "");
        
        ck_turn_t turn;
        res = ck_process_turn(test_inputs[i], &turn);
        
        if (res == CK_OK) {
            /* Show processing stages */
            printf("\n  %sProcessing:%s\n", BOLD, RESET);
            printf("    1. PERCEIVE  → Intent: %s (%.0f%% confidence)\n",
                   ck_intent_name(turn.intent.primary), turn.intent.confidence * 100);
            printf("    2. REMEMBER  → %u memories, %u tokens context\n",
                   turn.context.memory_count, turn.context.total_tokens);
            printf("    3. THINK     → %u reasoning steps\n", turn.reasoning_step_count);
            printf("    4. EXPRESS   → %u tokens, %.0f%% coherence\n",
                   turn.response.token_count, turn.response.coherence_score * 100);
            printf("    5. REFLECT   → %u learnings, proposal: %s\n",
                   turn.learning_count, turn.has_proposal ? "YES" : "NO");
            
            /* Show response */
            printf("\n  %sResponse:%s\n", BOLD, RESET);
            printf("    \"%.70s\n", turn.response.text);
            if (strlen(turn.response.text) > 70) {
                printf("     %.70s\n", turn.response.text + 70);
            }
            if (strlen(turn.response.text) > 140) {
                printf("     ...\"\n");
            } else {
                printf("    \"\n");
            }
            
            print_turn_summary(&turn);
        }
    }
    
    /* ======================================================================== */
    print_header("STATISTICS");
    /* ======================================================================== */
    
    ck_stats_t stats;
    ck_get_stats(&stats);
    
    printf("  ┌─────────────────────────────────────────────────┐\n");
    printf("  │ %sCOGNITIVE KERNEL STATISTICS%s                     │\n", BOLD, RESET);
    printf("  ├─────────────────────────────────────────────────┤\n");
    printf("  │ State:              %12s              │\n", ck_state_name(stats.state));
    printf("  │ Turns processed:    %12lu              │\n", stats.turns_processed);
    printf("  │ Input tokens:       %12lu              │\n", stats.total_input_tokens);
    printf("  │ Output tokens:      %12lu              │\n", stats.total_output_tokens);
    printf("  │ Proposals generated:%12u              │\n", stats.proposals_generated);
    printf("  │ Learnings recorded: %12u              │\n", stats.learnings_recorded);
    printf("  │ Avg response time:  %12.2f ms          │\n", stats.avg_response_time_ms);
    printf("  │ Avg coherence:      %12.2f              │\n", stats.avg_coherence_score);
    printf("  └─────────────────────────────────────────────────┘\n");
    
    /* ======================================================================== */
    print_header("SHUTDOWN");
    /* ======================================================================== */
    
    ck_shutdown();
    print_ok("Cognitive Kernel shut down cleanly");
    
    printf("\n");
    printf("╔══════════════════════════════════════════════════════════════════════╗\n");
    printf("║  TEST COMPLETE - Cognitive flow demonstrated (STUB MODE)            ║\n");
    printf("║                                                                      ║\n");
    printf("║  In production, the LLM would provide:                              ║\n");
    printf("║    • Real embeddings for semantic search                            ║\n");
    printf("║    • Actual language understanding                                  ║\n");
    printf("║    • Natural response generation                                    ║\n");
    printf("║    • Deep reasoning capabilities                                    ║\n");
    printf("╚══════════════════════════════════════════════════════════════════════╝\n");
    printf("\n");
    
    return 0;
}
