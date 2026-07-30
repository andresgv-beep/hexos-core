/*
 * HEXOS UI System v1.0
 * Panel-based Terminal User Interface
 * 
 * "Información clara, acciones obvias"
 */

#define _DEFAULT_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <unistd.h>
#include <termios.h>
#include <sys/ioctl.h>
#include <sys/select.h>

#include "../include/hexos_ui.h"
#include "../include/hexos_log.h"

/* ============================================================================
 * STATIC STATE
 * ============================================================================ */

static struct {
    bool initialized;
    struct termios orig_termios;
    
    /* View stack */
    ui_view_t view_stack[16];
    int view_depth;
    
    /* View callbacks */
    ui_view_draw_fn view_draw[VIEW_MAX];
    ui_view_input_fn view_input[VIEW_MAX];
    
} s_ui = {0};

/* ============================================================================
 * TERMINAL CONTROL
 * ============================================================================ */

void ui_init(void) {
    if (s_ui.initialized) return;
    
    /* Save original terminal settings */
    tcgetattr(STDIN_FILENO, &s_ui.orig_termios);
    
    /* Set raw mode */
    struct termios raw = s_ui.orig_termios;
    raw.c_lflag &= ~(ICANON | ECHO | ISIG);
    raw.c_iflag &= ~(IXON | ICRNL | BRKINT | INPCK | ISTRIP);
    raw.c_cflag |= CS8;
    raw.c_cc[VMIN] = 0;
    raw.c_cc[VTIME] = 0;
    tcsetattr(STDIN_FILENO, TCSAFLUSH, &raw);
    
    /* Enter alternate screen buffer */
    printf("\033[?1049h");
    
    /* Hide cursor */
    printf("\033[?25l");
    
    /* Clear screen */
    printf("\033[2J");
    
    fflush(stdout);
    
    s_ui.view_depth = 0;
    s_ui.initialized = true;
}

void ui_shutdown(void) {
    if (!s_ui.initialized) return;
    
    /* Show cursor */
    printf("\033[?25h");
    
    /* Exit alternate screen buffer */
    printf("\033[?1049l");
    
    fflush(stdout);
    
    /* Restore terminal */
    tcsetattr(STDIN_FILENO, TCSAFLUSH, &s_ui.orig_termios);
    
    s_ui.initialized = false;
}

bool ui_is_initialized(void) {
    return s_ui.initialized;
}

void ui_clear(void) {
    printf("\033[2J");
    printf("\033[H");
}

void ui_goto(int x, int y) {
    /* Terminal uses 1-based coordinates */
    printf("\033[%d;%dH", y + 1, x + 1);
}

void ui_cursor_show(bool show) {
    if (show) {
        printf("\033[?25h");
    } else {
        printf("\033[?25l");
    }
}

void ui_flush(void) {
    fflush(stdout);
}

/* ============================================================================
 * INPUT
 * ============================================================================ */

static bool key_available(void) {
    fd_set fds;
    struct timeval tv = {0, 0};
    
    FD_ZERO(&fds);
    FD_SET(STDIN_FILENO, &fds);
    
    return select(STDIN_FILENO + 1, &fds, NULL, NULL, &tv) > 0;
}

ui_key_t ui_getkey(void) {
    if (!key_available()) {
        return KEY_NONE;
    }
    
    int c = getchar();
    if (c == EOF) return KEY_NONE;
    
    /* Handle ESC sequences */
    if (c == 27) {
        if (!key_available()) {
            return KEY_ESC;
        }
        
        int c2 = getchar();
        if (c2 == '[') {
            /* CSI sequence */
            int c3 = getchar();
            
            switch (c3) {
                case 'A': return KEY_UP;
                case 'B': return KEY_DOWN;
                case 'C': return KEY_RIGHT;
                case 'D': return KEY_LEFT;
                case 'H': return KEY_HOME;
                case 'F': return KEY_END;
                case '1':
                    if (key_available()) {
                        int c4 = getchar();
                        if (c4 == '~') return KEY_HOME;
                        if (c4 == '5' && key_available() && getchar() == '~') return KEY_F5;
                        if (c4 == '7' && key_available() && getchar() == '~') return KEY_F6;
                        if (c4 == '8' && key_available() && getchar() == '~') return KEY_F7;
                        if (c4 == '9' && key_available() && getchar() == '~') return KEY_F8;
                    }
                    break;
                case '2':
                    if (key_available()) {
                        int c4 = getchar();
                        if (c4 == '~') return KEY_INSERT;
                        if (c4 == '0' && key_available() && getchar() == '~') return KEY_F9;
                        if (c4 == '1' && key_available() && getchar() == '~') return KEY_F10;
                        if (c4 == '3' && key_available() && getchar() == '~') return KEY_F11;
                        if (c4 == '4' && key_available() && getchar() == '~') return KEY_F12;
                    }
                    break;
                case '3':
                    if (key_available() && getchar() == '~') return KEY_DELETE;
                    break;
                case '4':
                    if (key_available() && getchar() == '~') return KEY_END;
                    break;
                case '5':
                    if (key_available() && getchar() == '~') return KEY_PGUP;
                    break;
                case '6':
                    if (key_available() && getchar() == '~') return KEY_PGDOWN;
                    break;
                default:
                    break;
            }
        } else if (c2 == 'O') {
            /* SS3 sequence (function keys) */
            int c3 = getchar();
            switch (c3) {
                case 'P': return KEY_F1;
                case 'Q': return KEY_F2;
                case 'R': return KEY_F3;
                case 'S': return KEY_F4;
                default: break;
            }
        }
        
        /* Unknown sequence, return ESC */
        return KEY_ESC;
    }
    
    /* Handle backspace (different terminals send different codes) */
    if (c == 127 || c == 8) {
        return KEY_BACKSPACE;
    }
    
    /* Handle Enter (terminals send \r in raw mode) */
    if (c == '\r') {
        return KEY_ENTER;
    }
    
    return (ui_key_t)c;
}

ui_key_t ui_getkey_wait(void) {
    ui_key_t key;
    while ((key = ui_getkey()) == KEY_NONE) {
        usleep(10000);  /* 10ms */
    }
    return key;
}

bool ui_readline(char *buf, int maxlen, bool hidden) {
    int pos = 0;
    buf[0] = '\0';
    
    ui_cursor_show(true);
    ui_flush();
    
    while (1) {
        ui_key_t key = ui_getkey_wait();
        
        if (key == KEY_ESC) {
            ui_cursor_show(false);
            return false;
        }
        
        if (key == KEY_ENTER) {
            ui_cursor_show(false);
            return true;
        }
        
        if (key == KEY_BACKSPACE) {
            if (pos > 0) {
                pos--;
                buf[pos] = '\0';
                printf("\b \b");
                ui_flush();
            }
            continue;
        }
        
        /* Printable character */
        if (key >= 32 && key < 127 && pos < maxlen - 1) {
            buf[pos++] = (char)key;
            buf[pos] = '\0';
            if (hidden) {
                putchar('*');
            } else {
                putchar((char)key);
            }
            ui_flush();
        }
    }
}

/* ============================================================================
 * PANEL DRAWING
 * ============================================================================ */

void ui_panel_draw(const ui_panel_t *panel) {
    const char *h = panel->double_border ? DBOX_H : BOX_H;
    const char *v = panel->double_border ? DBOX_V : BOX_V;
    const char *tl = panel->double_border ? DBOX_TL : BOX_TL;
    const char *tr = panel->double_border ? DBOX_TR : BOX_TR;
    const char *bl = panel->double_border ? DBOX_BL : BOX_BL;
    const char *br = panel->double_border ? DBOX_BR : BOX_BR;
    
    int inner_width = panel->width - 2;
    
    /* Top border with title */
    ui_goto(panel->x, panel->y);
    printf("%s", tl);
    
    if (panel->title && strlen(panel->title) > 0) {
        /* Title format: ─ TITLE ─── */
        printf("%s %s ", h, panel->title);
        int title_len = strlen(panel->title) + 4;  /* " TITLE " + 2 for h chars */
        for (int i = title_len; i < inner_width; i++) {
            printf("%s", h);
        }
    } else {
        for (int i = 0; i < inner_width; i++) {
            printf("%s", h);
        }
    }
    printf("%s", tr);
    
    /* Sides */
    for (int y = 1; y < panel->height - 1; y++) {
        ui_goto(panel->x, panel->y + y);
        printf("%s", v);
        for (int x = 0; x < inner_width; x++) {
            putchar(' ');
        }
        printf("%s", v);
    }
    
    /* Bottom border */
    ui_goto(panel->x, panel->y + panel->height - 1);
    printf("%s", bl);
    for (int i = 0; i < inner_width; i++) {
        printf("%s", h);
    }
    printf("%s", br);
}

void ui_panel_print(const ui_panel_t *panel, int x, int y, const char *fmt, ...) {
    /* Content area starts at (panel->x + 1, panel->y + 1) */
    ui_goto(panel->x + 1 + x, panel->y + 1 + y);
    
    va_list args;
    va_start(args, fmt);
    vprintf(fmt, args);
    va_end(args);
}

void ui_panel_separator(const ui_panel_t *panel, int y) {
    const char *h = panel->double_border ? DBOX_H : BOX_H;
    const char *vr = panel->double_border ? "╠" : BOX_VR;
    const char *vl = panel->double_border ? "╣" : BOX_VL;
    
    ui_goto(panel->x, panel->y + 1 + y);
    printf("%s", vr);
    for (int i = 0; i < panel->width - 2; i++) {
        printf("%s", h);
    }
    printf("%s", vl);
}

void ui_panel_clear(const ui_panel_t *panel) {
    for (int y = 1; y < panel->height - 1; y++) {
        ui_goto(panel->x + 1, panel->y + y);
        for (int x = 0; x < panel->width - 2; x++) {
            putchar(' ');
        }
    }
}

/* ============================================================================
 * COMMON UI ELEMENTS
 * ============================================================================ */

int ui_progress_bar(int x, int y, int width, float percent) {
    if (percent < 0) percent = 0;
    if (percent > 100) percent = 100;
    
    int filled = (int)(width * percent / 100.0f);
    
    ui_goto(x, y);
    putchar('[');
    for (int i = 0; i < width; i++) {
        if (i < filled) {
            printf("%s", BAR_FULL);
        } else {
            printf("%s", BAR_EMPTY);
        }
    }
    putchar(']');
    
    return width + 2;  /* Width including brackets */
}

void ui_label_value(int x, int y, int width, const char *label, const char *value) {
    ui_goto(x, y);
    
    int label_len = strlen(label);
    int value_len = strlen(value);
    int dots = width - label_len - value_len - 2;  /* -2 for ": " */
    if (dots < 1) dots = 1;
    
    printf("%s", label);
    for (int i = 0; i < dots; i++) {
        putchar('.');
    }
    printf(": %s", value);
}

void ui_status(int x, int y, const char *label, const char *status) {
    ui_goto(x, y);
    
    const char *color = ANSI_WHITE;
    if (strcmp(status, "OK") == 0 || strcmp(status, "PASS") == 0 || 
        strcmp(status, "ONLINE") == 0 || strcmp(status, "ACTIVE") == 0) {
        color = ANSI_GREEN;
    } else if (strcmp(status, "FAIL") == 0 || strcmp(status, "ERROR") == 0 ||
               strcmp(status, "OFFLINE") == 0) {
        color = ANSI_RED;
    } else if (strcmp(status, "WARN") == 0 || strcmp(status, "DEGRADED") == 0) {
        color = ANSI_YELLOW;
    } else if (strcmp(status, "STUB") == 0 || strcmp(status, "DISABLED") == 0) {
        color = ANSI_BRIGHT_BLACK;
    }
    
    printf("%s [%s%s%s]", label, color, status, ANSI_RESET);
}

void ui_action_bar(const char *actions) {
    ui_goto(0, UI_SCREEN_HEIGHT - 1);
    
    /* Clear line */
    for (int i = 0; i < UI_SCREEN_WIDTH; i++) {
        putchar(' ');
    }
    
    /* Print centered */
    int len = strlen(actions);
    int x = (UI_SCREEN_WIDTH - len) / 2;
    if (x < 0) x = 0;
    
    ui_goto(x, UI_SCREEN_HEIGHT - 1);
    printf("%s", actions);
}

void ui_header_bar(const char *text) {
    ui_goto(0, 0);
    
    /* Inverse video for header */
    printf("%s", ANSI_BG_BLUE);
    printf("%s", ANSI_BRIGHT_WHITE);
    
    /* Print text, pad to full width */
    int len = strlen(text);
    printf(" %s", text);
    for (int i = len + 1; i < UI_SCREEN_WIDTH; i++) {
        putchar(' ');
    }
    
    printf("%s", ANSI_RESET);
}

/* ============================================================================
 * VIEW MANAGEMENT
 * ============================================================================ */

void ui_view_push(ui_view_t view) {
    if (s_ui.view_depth < 15) {
        s_ui.view_stack[s_ui.view_depth++] = view;
        ui_view_redraw();
    }
}

void ui_view_pop(void) {
    if (s_ui.view_depth > 1) {
        s_ui.view_depth--;
        ui_view_redraw();
    }
}

void ui_view_set(ui_view_t view) {
    /* Replace current view (or set if empty) */
    if (s_ui.view_depth == 0) {
        s_ui.view_depth = 1;
    }
    s_ui.view_stack[s_ui.view_depth - 1] = view;
    ui_view_redraw();
}

ui_view_t ui_view_current(void) {
    if (s_ui.view_depth > 0) {
        return s_ui.view_stack[s_ui.view_depth - 1];
    }
    return VIEW_NONE;
}

void ui_view_register(ui_view_t view, ui_view_draw_fn draw, ui_view_input_fn input) {
    if (view < VIEW_MAX) {
        s_ui.view_draw[view] = draw;
        s_ui.view_input[view] = input;
    }
}

void ui_view_redraw(void) {
    ui_view_t view = ui_view_current();
    if (view < VIEW_MAX && s_ui.view_draw[view]) {
        ui_clear();
        s_ui.view_draw[view]();
        ui_flush();
    }
}

void ui_view_handle_input(ui_key_t key) {
    ui_view_t view = ui_view_current();
    if (view < VIEW_MAX && s_ui.view_input[view]) {
        s_ui.view_input[view](key);
    }
}

/* ============================================================================
 * DIALOGS
 * ============================================================================ */

void ui_dialog_message(const char *title, const char *message) {
    int msg_len = strlen(message);
    int title_len = title ? strlen(title) : 0;
    int width = msg_len + 4;
    if (title_len + 4 > width) width = title_len + 4;
    if (width > 60) width = 60;
    if (width < 30) width = 30;
    
    int x = (UI_SCREEN_WIDTH - width) / 2;
    int y = (UI_SCREEN_HEIGHT - 5) / 2;
    
    ui_panel_t panel = {x, y, width, 5, title, false};
    ui_panel_draw(&panel);
    ui_panel_print(&panel, 1, 1, "%s", message);
    ui_panel_print(&panel, (width - 18) / 2, 2, "[Enter] Continue");
    ui_flush();
    
    /* Wait for Enter or ESC */
    while (1) {
        ui_key_t key = ui_getkey_wait();
        if (key == KEY_ENTER || key == KEY_ESC) break;
    }
    
    ui_view_redraw();
}

bool ui_dialog_confirm(const char *title, const char *message) {
    int msg_len = strlen(message);
    int width = msg_len + 4;
    if (width > 60) width = 60;
    if (width < 40) width = 40;
    
    int x = (UI_SCREEN_WIDTH - width) / 2;
    int y = (UI_SCREEN_HEIGHT - 6) / 2;
    
    ui_panel_t panel = {x, y, width, 6, title, false};
    ui_panel_draw(&panel);
    ui_panel_print(&panel, 1, 1, "%s", message);
    ui_panel_print(&panel, (width - 24) / 2, 3, "[Y] Yes   [N/Esc] No");
    ui_flush();
    
    while (1) {
        ui_key_t key = ui_getkey_wait();
        if (key == 'y' || key == 'Y') {
            ui_view_redraw();
            return true;
        }
        if (key == 'n' || key == 'N' || key == KEY_ESC) {
            ui_view_redraw();
            return false;
        }
    }
}

bool ui_dialog_confirm_dangerous(const char *title, const char *message, 
                                  const char *confirm_text) {
    int width = 60;
    int x = (UI_SCREEN_WIDTH - width) / 2;
    int y = (UI_SCREEN_HEIGHT - 10) / 2;
    
    ui_panel_t panel = {x, y, width, 10, title, true};  /* Double border = dangerous */
    ui_panel_draw(&panel);
    
    /* Warning color */
    ui_panel_print(&panel, 1, 0, "%s%s%s", ANSI_YELLOW, message, ANSI_RESET);
    ui_panel_print(&panel, 1, 2, "To confirm, type: %s%s%s", 
                   ANSI_BRIGHT_WHITE, confirm_text, ANSI_RESET);
    ui_panel_print(&panel, 1, 4, "Confirm: ");
    ui_panel_print(&panel, 1, 6, "[Enter] Execute   [Esc] Cancel");
    ui_flush();
    
    /* Read confirmation */
    char buf[64];
    ui_goto(x + 11, y + 5);
    
    if (!ui_readline(buf, sizeof(buf), false)) {
        ui_view_redraw();
        return false;
    }
    
    bool confirmed = (strcmp(buf, confirm_text) == 0);
    ui_view_redraw();
    return confirmed;
}

bool ui_dialog_auth(char *out_user, int user_len, char *out_pass, int pass_len) {
    int width = 50;
    int x = (UI_SCREEN_WIDTH - width) / 2;
    int y = (UI_SCREEN_HEIGHT - 10) / 2;
    
    ui_panel_t panel = {x, y, width, 10, "AUTHENTICATION REQUIRED", true};
    ui_panel_draw(&panel);
    
    ui_panel_print(&panel, 1, 1, "User:   [                    ]");
    ui_panel_print(&panel, 1, 3, "Secret: [                    ]");
    ui_panel_print(&panel, 1, 5, "Rate limit: 3 attempts / 30s");
    ui_panel_print(&panel, 1, 7, "[Enter] Authenticate   [Esc] Cancel");
    ui_flush();
    
    /* Read username */
    ui_goto(x + 10, y + 2);
    if (!ui_readline(out_user, user_len, false)) {
        ui_view_redraw();
        return false;
    }
    
    /* Read password */
    ui_goto(x + 10, y + 4);
    if (!ui_readline(out_pass, pass_len, true)) {
        ui_view_redraw();
        return false;
    }
    
    ui_view_redraw();
    return true;
}
