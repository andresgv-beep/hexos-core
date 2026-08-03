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
#include <stdint.h>

#include "hexos_model.h"

/* ============================================================================
 * MOTOR (engine.c)
 * ============================================================================ */

/* Estado del turno, tal y como lo ve el puente. */
typedef enum {
    ENGINE_BOOTING = 0,   /* cargando modelo, aún sin prompt */
    ENGINE_IDLE,          /* listo, esperando mensaje */
    ENGINE_STAGING,       /* transfiriendo un adjunto para el próximo turno */
    ENGINE_THINKING,      /* mensaje enviado, respuesta sin empezar */
    ENGINE_SPEAKING,      /* emitiendo texto de la respuesta */
    ENGINE_DEAD           /* el proceso murió */
} engine_state_t;

/* Trozo de texto de la respuesta, ya sin códigos de color. */
typedef void (*engine_chunk_cb)(const char *text, size_t len, void *user);

/* Cambio de estado: "ready", "start", "end", "dead". */
typedef void (*engine_event_cb)(const char *event, void *user);

/* Aviso del motor entre paréntesis, de los que imprime antes de responder:
 * texto truncado, mensaje recortado, reorganización de memoria... No son
 * parte de la respuesta, pero sí cosas que el usuario necesita saber — si
 * se tiran con el resto del ruido, uno pega un documento de 16 KB, el motor
 * se queda con la mitad y nadie se entera. */
typedef void (*engine_notice_cb)(const char *text, size_t len, void *user);

/* Lanza helios_chat con tuberías. `temp` puede ser NULL (usa 0.7). */
bool engine_start(const char *binary, const char *model, const char *temp);

/* Envía un mensaje del usuario. Falla si el motor no está en IDLE. */
bool engine_send(const char *text);

typedef enum {
    ENGINE_ATTACHMENT_RGB8 = 0,
} engine_attachment_kind_t;

typedef struct {
    engine_attachment_kind_t kind;
    const void *data;
    size_t byte_size;
    uint32_t width;
    uint32_t height;
    size_t row_stride_bytes;
} engine_attachment_t;

/* Deja un adjunto pendiente para el siguiente engine_send(). */
bool engine_attach(const engine_attachment_t *attachment);

/* Envía un comando del REPL tal cual (/fast, /memoria, /salir...). */
bool engine_command(const char *cmd);

engine_state_t engine_state(void);
const char *engine_state_name(engine_state_t st);
void engine_set_notice_cb(engine_notice_cb on_notice);
void engine_set_callbacks(engine_chunk_cb on_chunk, engine_event_cb on_event,
                          void *user);
void engine_stop(void);

/* ============================================================================
 * RUTA TIPADA (runtime_client.c) — E2, opt-in
 * ============================================================================
 * Paralela a la legacy, no sustituta. HexOS clasifica el turno con el CK
 * portado, compone el contrato efimero y manda mensajes tipados a
 * helios_runtime. El contrato NUNCA se guarda: vive en la pila de rt_send y
 * muere al salir.
 *
 * Limite declarado de E2: esta ruta es cognitivamente incompleta a proposito.
 * Identidad, memoria, reflexion y consolidacion siguen en helios_chat y no se
 * copian aqui — eso es E3/E5.
 */

/* Telemetria del CK: acto, registro y presupuestos. El contrato NO viaja. */
typedef void (*rt_frame_cb)(const char *acto, const char *registro,
                            int visible_budget, int thinking_budget,
                            void *user);

bool rt_start(const char *binary, const char *model, const char *ctx,
              const char *temp);
bool rt_send(const char *text);
bool rt_attach(const engine_attachment_t *attachment);
void rt_set_registro(const char *registro);
engine_state_t rt_state(void);
void rt_set_callbacks(engine_chunk_cb on_chunk, engine_event_cb on_event,
                      engine_notice_cb on_notice, rt_frame_cb on_frame,
                      void *user);
void rt_stop(void);

/* Estado de la memoria para telemetría y auditoría. NO expone el bloque de
 * perfil: es contexto efímero y publicarlo sería un sitio más donde vive la
 * memoria sin reglas. */
size_t rt_memoria_json(char *out, size_t cap);

/* Ensayo de un MemoryDelta: veredictos SIN aplicar nada. En E3 no hay
 * aplicador y esto no lo es. */
size_t rt_memoria_ensayo(const char *json_delta, char *out, size_t cap);

/* Despacho: http.c no necesita saber que ruta esta activa. */
void ruta_usar_tipada(bool tipada);
bool ruta_activa_tipada(void);
bool ruta_send(const char *text);
bool ruta_attach(const engine_attachment_t *attachment);
bool ruta_command(const char *cmd);
engine_state_t ruta_state(void);

/* ============================================================================
 * SERVIDOR (http.c)
 * ============================================================================ */

/* Reserva el puerto. Se llama ANTES de arrancar el motor: si está ocupado,
 * el fallo es inmediato en vez de después de cargar gigabytes de modelo. */
bool serve_bind(const char *bind_addr, int port);

/* Published by /api/status. Must be called before serve_run(). */
void serve_set_model_report(const hexos_model_report_t *report);

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
