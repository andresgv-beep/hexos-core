#include "hexos_serve.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static volatile int attachment_event;
static volatile int saw_ok;

static void on_chunk(const char *text, size_t len, void *user)
{
    (void)user;
    if (len >= 2 && memmem(text, len, "ok", 2)) saw_ok = 1;
}

static void on_event(const char *event, void *user)
{
    (void)user;
    if (!strcmp(event, "attachment")) attachment_event = 1;
}

static void wait_idle(void)
{
    for (int i = 0; i < 500; i++) {
        if (engine_state() == ENGINE_IDLE) return;
        assert(engine_state() != ENGINE_DEAD);
        usleep(10000);
    }
    assert(!"timeout waiting for fake engine");
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    engine_set_callbacks(on_chunk, on_event, NULL);
    assert(engine_start(argv[1], "unused.hnf", "0"));
    wait_idle();

    unsigned char pixels[6 * 4];
    for (size_t i = 0; i < sizeof(pixels); i++) pixels[i] = (unsigned char)i;
    const engine_attachment_t attachment = {
        .kind = ENGINE_ATTACHMENT_RGB8,
        .data = pixels,
        .byte_size = sizeof(pixels),
        .width = 2,
        .height = 4,
        .row_stride_bytes = 6,
    };
    engine_attachment_t invalid = attachment;
    invalid.byte_size--;
    assert(!engine_attach(&invalid));
    assert(engine_state() == ENGINE_IDLE);
    assert(engine_attach(&attachment));
    wait_idle();
    assert(attachment_event);

    assert(engine_send("describe"));
    wait_idle();
    assert(saw_ok);
    engine_stop();
    puts("PASS: HexOS binary attachment bridge and staging state");
    return 0;
}
