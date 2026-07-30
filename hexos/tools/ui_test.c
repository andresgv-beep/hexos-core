/*
 * HEXOS UI Test Program
 * Tests the new panel-based UI system
 */

#include <stdio.h>
#include <unistd.h>
#include "../include/hexos_ui.h"
#include "../include/hexos_log.h"

/* Test view draw function */
static void draw_test_view(void) {
    /* Header */
    ui_header_bar("HEXOS UI TEST · Press keys to test · Q to quit");
    
    /* Main panel - left side */
    ui_panel_t main_panel = {0, 1, 50, 15, "BOOT PIPELINE", false};
    ui_panel_draw(&main_panel);
    
    ui_panel_print(&main_panel, 1, 0, "1 Hardware Detection   [");
    ui_progress_bar(27, 2, 10, 100);
    ui_goto(39, 2);
    printf("] %sOK%s", ANSI_GREEN, ANSI_RESET);
    
    ui_panel_print(&main_panel, 1, 1, "2 Hardware Contract    [");
    ui_progress_bar(27, 3, 10, 100);
    ui_goto(39, 3);
    printf("] %sOK%s", ANSI_GREEN, ANSI_RESET);
    
    ui_panel_print(&main_panel, 1, 2, "3 Module Attestation   [");
    ui_progress_bar(27, 4, 10, 75);
    ui_goto(39, 4);
    printf("] %sRUN%s", ANSI_YELLOW, ANSI_RESET);
    
    ui_panel_print(&main_panel, 1, 3, "4 Resource Allocation  [");
    ui_progress_bar(27, 5, 10, 0);
    ui_goto(39, 5);
    printf("] %s---%s", ANSI_BRIGHT_BLACK, ANSI_RESET);
    
    /* Telemetry panel - right side */
    ui_panel_t tele_panel = {51, 1, 28, 10, "LIVE TELEMETRY", false};
    ui_panel_draw(&tele_panel);
    
    ui_panel_print(&tele_panel, 1, 0, "CPU   %s12%%%s", ANSI_GREEN, ANSI_RESET);
    ui_panel_print(&tele_panel, 12, 0, "RAM  8/32 GB");
    ui_panel_print(&tele_panel, 1, 1, "GPU   %s--%s", ANSI_BRIGHT_BLACK, ANSI_RESET);
    ui_panel_print(&tele_panel, 12, 1, "VRAM 0/12 GB");
    ui_panel_print(&tele_panel, 1, 2, "Temp  --C");
    ui_panel_print(&tele_panel, 12, 2, "Fans --");
    ui_panel_print(&tele_panel, 1, 4, "Alerts: %s2 STUB%s", ANSI_YELLOW, ANSI_RESET);
    
    /* Details panel - bottom */
    ui_panel_t detail_panel = {0, 16, 79, 5, "DETAILS", false};
    ui_panel_draw(&detail_panel);
    
    ui_panel_print(&detail_panel, 1, 0, 
        "HNF-EXT: %sNOT FOUND%s  | Predictive Memory: %sDISABLED%s", 
        ANSI_YELLOW, ANSI_RESET, ANSI_BRIGHT_BLACK, ANSI_RESET);
    ui_panel_print(&detail_panel, 1, 1, 
        "Next: connect Memory Core -> seal continuity -> expose control socket");
    
    /* Action bar */
    ui_action_bar("[F1]Help  [F2]Logs  [F3]Safe  [Enter]Continue  [D]Dump  [Q]Quit");
}

static void handle_test_input(ui_key_t key) {
    /* Just for testing key detection */
    ui_goto(0, 22);
    printf("Last key: %d    ", key);
    
    if (key == KEY_F1) {
        ui_dialog_message("HELP", "This is a test of the UI system.");
    } else if (key == KEY_F2) {
        ui_dialog_message("LOGS", "Log viewer would open here.");
    } else if (key == 'y' || key == 'Y') {
        if (ui_dialog_confirm("CONFIRM", "Do you want to proceed?")) {
            ui_goto(0, 22);
            printf("User confirmed!            ");
        } else {
            ui_goto(0, 22);
            printf("User cancelled!            ");
        }
    } else if (key == 'd' || key == 'D') {
        if (ui_dialog_confirm_dangerous("DANGEROUS ACTION", 
            "This will delete all data!", "DELETE ALL")) {
            ui_goto(0, 22);
            printf("DANGEROUS ACTION CONFIRMED!");
        }
    } else if (key == 'a' || key == 'A') {
        char user[32], pass[32];
        if (ui_dialog_auth(user, sizeof(user), pass, sizeof(pass))) {
            ui_goto(0, 22);
            printf("Auth: user=%s pass=%s      ", user, "***");
        }
    }
    
    ui_flush();
}

int main(void) {
    printf("Starting UI test...\n");
    printf("Press any key to enter UI mode.\n");
    getchar();
    
    /* Initialize UI */
    ui_init();
    
    /* Register test view */
    ui_view_register(VIEW_BOOT, draw_test_view, handle_test_input);
    
    /* Push initial view */
    ui_view_push(VIEW_BOOT);
    
    /* Main loop */
    bool running = true;
    while (running) {
        ui_key_t key = ui_getkey();
        
        if (key != KEY_NONE) {
            if (key == 'q' || key == 'Q') {
                running = false;
            } else {
                ui_view_handle_input(key);
            }
        }
        
        usleep(10000);  /* 10ms */
    }
    
    /* Shutdown */
    ui_shutdown();
    
    printf("UI test complete.\n");
    return 0;
}
