/*
 * HEXOS Boot UI Test
 * Tests the new panel-based boot sequence
 */

#define _DEFAULT_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <sys/time.h>

#include "../include/hexos_ui.h"
#include "../include/hexos_views.h"
#include "../include/hexos_telemetry.h"
#include "../include/hexos.h"
#include "../include/hexos_ipc.h"

/* Stub for hexos_time_ms */
uint64_t hexos_time_ms(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (uint64_t)tv.tv_sec * 1000 + tv.tv_usec / 1000;
}

/* Stub for hexos_get_ipc */
static hexos_ipc_ctx_t s_ipc_stub = {0};
hexos_ipc_ctx_t* hexos_get_ipc(void) {
    return &s_ipc_stub;
}

/* Simulate boot phases */
static void simulate_boot(void) {
    boot_state_t *boot = hexos_boot_state();
    
    /* Phase 1: Hardware Detection */
    boot_phase_start(0, "Detecting hardware...");
    boot_phase_detail("Scanning CPU, RAM, GPU...");
    ui_view_redraw();
    ui_flush();
    
    for (int i = 0; i <= 100; i += 10) {
        boot_phase_progress(0, (float)i);
        ui_view_redraw();
        ui_flush();
        usleep(50000);
    }
    boot_phase_end(0, PHASE_OK);
    strcpy(boot->gpu_name, "NVIDIA GeForce RTX 4070 Ti");
    
    /* Phase 2: Hardware Contract */
    boot_phase_start(1, "Validating hardware contract...");
    boot_phase_detail("Checking capabilities...");
    ui_view_redraw();
    ui_flush();
    
    for (int i = 0; i <= 100; i += 20) {
        boot_phase_progress(1, (float)i);
        ui_view_redraw();
        ui_flush();
        usleep(30000);
    }
    boot_phase_end(1, PHASE_OK);
    
    /* Phase 3: Module Attestation */
    boot_phase_start(2, "Attesting modules...");
    boot_phase_detail("Memory Core, HNF-EXT, HERA...");
    ui_view_redraw();
    ui_flush();
    
    for (int i = 0; i <= 100; i += 5) {
        boot_phase_progress(2, (float)i);
        ui_view_redraw();
        ui_flush();
        usleep(20000);
    }
    boot_phase_end(2, PHASE_OK);
    boot_set_alert("STUB modules", 2);
    
    /* Phase 4: Resource Allocation */
    boot_phase_start(3, "Allocating resources...");
    boot_phase_detail("VRAM pools, RAM limits...");
    ui_view_redraw();
    ui_flush();
    
    for (int i = 0; i <= 100; i += 15) {
        boot_phase_progress(3, (float)i);
        ui_view_redraw();
        ui_flush();
        usleep(40000);
    }
    boot_phase_end(3, PHASE_OK);
    
    /* Phase 5: Runtime Init */
    boot_phase_start(4, "Initializing runtime...");
    boot_phase_detail("IPC, shared memory...");
    ui_view_redraw();
    ui_flush();
    
    for (int i = 0; i <= 100; i += 8) {
        boot_phase_progress(4, (float)i);
        ui_view_redraw();
        ui_flush();
        usleep(60000);
    }
    boot_phase_end(4, PHASE_OK);
    
    /* Phase 6: HELIOS Activation */
    boot_phase_start(5, "Activating HELIOS...");
    boot_phase_detail("Connecting cognitive modules...");
    ui_view_redraw();
    ui_flush();
    
    for (int i = 0; i <= 100; i += 4) {
        boot_phase_progress(5, (float)i);
        
        if (i == 50) {
            boot_phase_detail("Loading identity from HNF-EXT...");
            boot->hnf_ext_found = false;  /* Simulate not found */
        }
        if (i == 75) {
            boot_phase_detail("Starting HERA coordinator...");
        }
        
        ui_view_redraw();
        ui_flush();
        usleep(30000);
    }
    boot_phase_end(5, PHASE_OK);
    
    /* Set continuity message */
    strcpy(boot->continuity_message, 
        "No persistent identity found. Operating in ephemeral mode. "
        "Use 'identity create' to establish persistent identity.");
    
    /* Boot complete */
    boot_set_complete();
    ui_view_redraw();
    ui_flush();
}

int main(void) {
    printf("HEXOS Boot UI Test\n");
    printf("==================\n\n");
    printf("This will simulate the boot sequence with the new UI.\n");
    printf("Press Enter to start...\n");
    getchar();
    
    /* Initialize telemetry (needed for display) */
    hexos_telemetry_init(500);
    
    /* Initialize UI system */
    ui_init();
    
    /* Initialize views */
    hexos_views_init();
    
    /* Initialize boot state */
    boot_state_init();
    
    /* Push boot view */
    ui_view_push(VIEW_BOOT);
    
    /* Simulate boot */
    simulate_boot();
    
    /* Wait for user to press Enter or Q */
    boot_state_t *boot = hexos_boot_state();
    
    while (!boot->quit_requested) {
        ui_key_t key = ui_getkey();
        
        if (key != KEY_NONE) {
            ui_view_handle_input(key);
            
            /* Check if we transitioned to main view */
            if (ui_view_current() == VIEW_MAIN) {
                /* Main view loop - refresh periodically */
                while (!boot->quit_requested) {
                    ui_view_redraw();
                    ui_flush();
                    
                    for (int i = 0; i < 100 && !boot->quit_requested; i++) {
                        key = ui_getkey();
                        if (key != KEY_NONE) {
                            ui_view_handle_input(key);
                            break;
                        }
                        usleep(10000);
                    }
                }
            }
            
            ui_view_redraw();
            ui_flush();
        }
        
        usleep(10000);
    }
    
    /* Cleanup */
    ui_shutdown();
    hexos_telemetry_shutdown();
    
    printf("\nBoot UI test complete.\n");
    return 0;
}
