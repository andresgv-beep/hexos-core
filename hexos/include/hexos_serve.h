/*
 * HEXOS - HELIOS Executive Operating System
 * Serve - Puente HTTP/SSE entre la UI web y Héctor
 *
 * HEXOS es el escudo: es quien abre el puerto, lanza al motor y vigila que
 * siga vivo. Héctor no conoce la red; habla por tubería como si tuviera un
 * terminal delante. Por eso este puente NO necesita ni un cambio en
 * Hector-engine: conduce el REPL de helios_chat tal cual existe.
 */

#ifndef HEXOS_SERVE_H
#define HEXOS_SERVE_H

#include <stdbool.h>
#include <stddef.h>

/* ============================================================================
 * MOTOR (engine.c)
 * ============================================================================ */

/* Estado del turno, tal y como lo ve el puente. */
typedef enum {
    ENGINE_BOOTING = 0,   /* cargando modelo, aún sin prompt */
    ENGINE_IDLE,          /* listo, esperando mensaje */
    ENGINE_THINKING,      /* mensaje enviado, respuesta sin empezar */
    ENGINE_SPEAKING,      /* emitiendo texto de la respuesta */
    ENGINE_DEAD           /* el proceso murió */
} engine_state_t;

/* Trozo de texto de la respuesta, ya sin códigos de color. */
typedef void (*engine_chunk_cb)(const char *text, size_t len, void *user);

/* Cambio de estado: "ready", "start", "end", "dead". */
typedef void (*engine_event_cb)(const char *event, void *user);

/* Lanza helios_chat con tuberías. `temp` puede ser NULL (usa 0.7). */
bool engine_start(const char *binary, const char *model, const char *temp);

/* Envía un mensaje del usuario. Falla si el motor no está en IDLE. */
bool engine_send(const char *text);

/* Envía un comando del REPL tal cual (/fast, /memoria, /salir...). */
bool engine_command(const char *cmd);

engine_state_t engine_state(void);
const char *engine_state_name(engine_state_t st);
void engine_set_callbacks(engine_chunk_cb on_chunk, engine_event_cb on_event,
                          void *user);
void engine_stop(void);

/* ============================================================================
 * SERVIDOR (http.c)
 * ============================================================================ */

/* Reserva el puerto. Se llama ANTES de arrancar el motor: si está ocupado,
 * el fallo es inmediato en vez de después de cargar gigabytes de modelo. */
bool serve_bind(const char *bind_addr, int port);

/* Bucle de accept sobre el socket ya reservado. Bloquea hasta serve_stop(). */
bool serve_run(const char *web_root);
void serve_stop(void);

/* Empuja un evento SSE a todos los clientes conectados.
 * `json_payload` ya debe venir formado. */
void serve_broadcast(const char *event, const char *json_payload);

/* Escapa una cadena para meterla dentro de un string JSON. Devuelve la
 * longitud escrita (sin contar el terminador). */
size_t json_escape(const char *in, size_t in_len, char *out, size_t out_cap);

#endif /* HEXOS_SERVE_H */
