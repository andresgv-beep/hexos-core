/*
 * HEXOS UI System v1.0
 * Panel-based Terminal User Interface
 * 
 * "Información clara, acciones obvias"
 */

#ifndef HEXOS_UI_H
#define HEXOS_UI_H

#include <stdbool.h>
#include <stdint.h>

/* ============================================================================
 * SCREEN DIMENSIONS
 * ============================================================================ */

#define UI_SCREEN_WIDTH     80      /* Standard terminal width */
#define UI_SCREEN_HEIGHT    24      /* Standard terminal height */
#define UI_PANEL_MARGIN     1       /* Space between panels */

/* ============================================================================
 * KEY CODES
 * ============================================================================ */

typedef enum {
    KEY_NONE = 0,
    KEY_ENTER = '\n',
    KEY_ESC = 27,
    KEY_BACKSPACE = 127,
    KEY_TAB = '\t',
    
    /* Special keys (after ESC sequence) */
    KEY_UP = 256,
    KEY_DOWN,
    KEY_LEFT,
    KEY_RIGHT,
    KEY_HOME,
    KEY_END,
    KEY_PGUP,
    KEY_PGDOWN,
    KEY_INSERT,
    KEY_DELETE,
    
    /* Function keys */
    KEY_F1,
    KEY_F2,
    KEY_F3,
    KEY_F4,
    KEY_F5,
    KEY_F6,
    KEY_F7,
    KEY_F8,
    KEY_F9,
    KEY_F10,
    KEY_F11,
    KEY_F12
} ui_key_t;

/* ============================================================================
 * PANEL STRUCTURE
 * ============================================================================ */

typedef struct {
    int x, y;           /* Top-left position (0-based) */
    int width, height;  /* Dimensions including borders */
    const char *title;  /* Panel title (NULL for no title) */
    bool double_border; /* Use double-line border (╔═╗) */
} ui_panel_t;

/* ============================================================================
 * VIEW SYSTEM
 * ============================================================================ */

typedef enum {
    VIEW_NONE = 0,
    VIEW_BOOT,          /* Boot sequence screen */
    VIEW_MAIN,          /* Main status screen (after boot) */
    VIEW_IDENTITY,      /* Identity details */
    VIEW_MEMORY,        /* Memory Core details */
    VIEW_GPU,           /* GPU details */
    VIEW_HERA,          /* HERA status */
    VIEW_LOGS,          /* Log viewer */
    VIEW_ADVANCED,      /* Advanced menu */
    VIEW_AUTH,          /* Authentication prompt */
    VIEW_CONFIRM,       /* Dangerous action confirmation */
    VIEW_MAX
} ui_view_t;

/* View callback function type */
typedef void (*ui_view_draw_fn)(void);
typedef void (*ui_view_input_fn)(ui_key_t key);

/* ============================================================================
 * TERMINAL CONTROL
 * ============================================================================ */

/*
 * Initialize UI system
 * Sets up terminal for raw mode, alternate buffer
 */
void ui_init(void);

/*
 * Shutdown UI system
 * Restores terminal to normal mode
 */
void ui_shutdown(void);

/*
 * Check if UI is initialized
 */
bool ui_is_initialized(void);

/*
 * Clear entire screen
 */
void ui_clear(void);

/*
 * Move cursor to position (0-based)
 */
void ui_goto(int x, int y);

/*
 * Show/hide cursor
 */
void ui_cursor_show(bool show);

/*
 * Flush output buffer
 */
void ui_flush(void);

/* ============================================================================
 * INPUT
 * ============================================================================ */

/*
 * Read a key (non-blocking)
 * Returns KEY_NONE if no key available
 */
ui_key_t ui_getkey(void);

/*
 * Read a key (blocking)
 */
ui_key_t ui_getkey_wait(void);

/*
 * Read a line of text (with echo)
 * Returns false if cancelled (ESC)
 */
bool ui_readline(char *buf, int maxlen, bool hidden);

/* ============================================================================
 * PANEL DRAWING
 * ============================================================================ */

/*
 * Draw a panel border with optional title
 */
void ui_panel_draw(const ui_panel_t *panel);

/*
 * Draw text inside a panel (relative to panel interior)
 * x, y are relative to panel content area (inside borders)
 */
void ui_panel_print(const ui_panel_t *panel, int x, int y, const char *fmt, ...);

/*
 * Draw a horizontal separator inside panel
 */
void ui_panel_separator(const ui_panel_t *panel, int y);

/*
 * Clear panel interior
 */
void ui_panel_clear(const ui_panel_t *panel);

/* ============================================================================
 * COMMON UI ELEMENTS
 * ============================================================================ */

/*
 * Draw a progress bar
 * Returns width used
 */
int ui_progress_bar(int x, int y, int width, float percent);

/*
 * Draw a labeled value
 * "Label: value" with dots padding
 */
void ui_label_value(int x, int y, int width, const char *label, const char *value);

/*
 * Draw a status indicator
 * [OK] green, [FAIL] red, [WARN] yellow, [STUB] gray
 */
void ui_status(int x, int y, const char *label, const char *status);

/*
 * Draw action bar at bottom
 * "[F1]Help  [F2]Logs  [Esc]Back"
 */
void ui_action_bar(const char *actions);

/*
 * Draw a header bar at top
 * "HEXOS · Build 1.0.247 · Session abc123"
 */
void ui_header_bar(const char *text);

/* ============================================================================
 * VIEW MANAGEMENT
 * ============================================================================ */

/*
 * Push a new view onto the stack
 */
void ui_view_push(ui_view_t view);

/*
 * Pop current view, return to previous
 */
void ui_view_pop(void);

/*
 * Replace current view (doesn't affect stack depth)
 */
void ui_view_set(ui_view_t view);

/*
 * Get current view
 */
ui_view_t ui_view_current(void);

/*
 * Register view callbacks
 */
void ui_view_register(ui_view_t view, ui_view_draw_fn draw, ui_view_input_fn input);

/*
 * Redraw current view
 */
void ui_view_redraw(void);

/*
 * Process input for current view
 */
void ui_view_handle_input(ui_key_t key);

/* ============================================================================
 * DIALOG HELPERS
 * ============================================================================ */

/*
 * Show a message dialog
 * Blocks until user presses a key
 */
void ui_dialog_message(const char *title, const char *message);

/*
 * Show a confirmation dialog
 * Returns true if confirmed
 */
bool ui_dialog_confirm(const char *title, const char *message);

/*
 * Show a dangerous action confirmation
 * User must type the confirmation text exactly
 */
bool ui_dialog_confirm_dangerous(const char *title, const char *message, 
                                  const char *confirm_text);

/*
 * Show authentication dialog
 * Returns true if authenticated
 */
bool ui_dialog_auth(char *out_user, int user_len, char *out_pass, int pass_len);

#endif /* HEXOS_UI_H */
