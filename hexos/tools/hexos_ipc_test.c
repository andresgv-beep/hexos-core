/*
 * HEXOS IPC Test Client
 * Simulates a Cognitive Kernel connecting to HEXOS IPC
 * 
 * Usage: ./hexos_ipc_test
 * (Run while HEXOS is running in another terminal)
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <math.h>
#include <signal.h>

#include "../include/hexos_ipc.h"

static volatile int running = 1;

void signal_handler(int sig) {
    (void)sig;
    running = 0;
}

int main(int argc, char *argv[]) {
    (void)argc;
    (void)argv;
    
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    printf("HEXOS IPC Test Client\n");
    printf("=====================\n\n");
    
    /* Connect to HEXOS IPC as Cognitive Kernel */
    hexos_ipc_ctx_t ipc;
    
    printf("Connecting to HEXOS shared memory...\n");
    if (hexos_ipc_connect(&ipc, HEXOS_MODULE_COGNITIVE) < 0) {
        fprintf(stderr, "ERROR: Could not connect to HEXOS IPC\n");
        fprintf(stderr, "Make sure HEXOS is running first.\n");
        return 1;
    }
    
    printf("Connected! Module registered as Cognitive Kernel.\n\n");
    printf("Simulating inference activity...\n");
    printf("(Watch the HEXOS dashboard to see values update)\n");
    printf("Press Ctrl+C to stop.\n\n");
    
    /* Update CONTINUITY message */
    hexos_ipc_update_memory(&ipc, false,
        "IPC Test: Cognitive Kernel connected and operational. "
        "This message was sent via shared memory.");
    
    float tokens_per_sec = 0.0f;
    uint32_t queue_depth = 0;
    int cycle = 0;
    
    while (running) {
        /* Simulate varying inference activity */
        cycle++;
        
        /* Simulate bursts of activity */
        bool engine_running = (cycle % 20) < 15;  /* 75% active */
        
        if (engine_running) {
            /* Simulate token generation with some variation */
            tokens_per_sec = 25.0f + 10.0f * sinf(cycle * 0.1f);
            if (tokens_per_sec < 0) tokens_per_sec = 0;
            queue_depth = (cycle / 5) % 5;
        } else {
            /* Idle periods */
            tokens_per_sec *= 0.8f;  /* Decay */
            if (tokens_per_sec < 0.5f) tokens_per_sec = 0.0f;
            queue_depth = 0;
        }
        
        /* Update IPC state */
        hexos_ipc_update_cognitive(&ipc, engine_running, tokens_per_sec, queue_depth);
        
        /* Simulate predictive memory */
        float hit_rate = 0.7f + 0.2f * sinf(cycle * 0.05f);
        hexos_ipc_update_predictive(&ipc, true, engine_running, hit_rate);
        
        /* Print status every few seconds */
        if (cycle % 10 == 0) {
            printf("  [%3d] Engine: %s  Tokens/s: %5.1f  Queue: %u  HitRate: %.0f%%\n",
                   cycle,
                   engine_running ? "RUNNING" : "IDLE   ",
                   tokens_per_sec,
                   queue_depth,
                   hit_rate * 100);
        }
        
        usleep(500000);  /* 500ms */
    }
    
    printf("\nDisconnecting...\n");
    
    /* Update state to show we're disconnecting */
    hexos_ipc_update_cognitive(&ipc, false, 0.0f, 0);
    hexos_ipc_update_memory(&ipc, false, "Cognitive Kernel disconnected.");
    
    hexos_ipc_shutdown(&ipc);
    
    printf("Done.\n");
    return 0;
}
