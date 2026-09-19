# Protocolo de helios_runtime: estado vigente

**Implementado y ampliado; revisión 2026-09-19.** La propuesta E1 original se
conserva en [archivo histórico](historico/E1_PROTOCOLO_PROPUESTA.md).
La especificación contrastada con el motor vive en
`Hector-engine/tools/RUNTIME_PROTOCOL.md` (código `b822e1b`).

## Cambios respecto a la propuesta inicial

- NDJSON ya se usa en la ruta nativa del agente con `--native-template`.
  El ejecutable es `helios_runtime`; `helios_formatted` queda como compatibilidad.
- Existen `session_open`, `session_close` y eventos de sesión. Las sesiones
  comparten pesos y serializan cómputo. `max_seq_len` puede limitar cada sesión.
- Existen `attachment_drop`, `turn_started` y `prefill_progress`. Los dos eventos
  de progreso se solicitan con `generation.prefill_progress=true`.
- `generation` acepta `preformatted`, `reuse_prefix`, `close_turn`, `stop_tokens`,
  temperatura y límites de tokens. Un prompt preformateado completo permite
  reutilizar el prefijo válido; no siempre deben enviarse solo mensajes nuevos.
- `completed` añade prefijo reutilizado, espera y primer fragmento; la terminación
  puede ser `context_full`, además de EOS, límite, stop y cancelación.
- La cancelación apunta al ID activo. Un objetivo en cola/no activo devuelve
  `not_active`; se puede repetir al recibir `turn_started`.
- En prefill cancelado puede retroceder el KV o vaciarse si se perdió el anillo.
  La reutilización de prefijo también puede retroceder. No existe el evento
  `context_compacted` que preveía E1; la posición publicada es la referencia.
- En modo preformateado `text_delta` puede incluir pensamiento/marcadores del
  modelo. `native_transport.visible_preview` los filtra antes de mostrar texto.

`ready.protocol` sigue siendo 2. Las fixtures de `tools/protocolo_test.py`
corresponden al esquema inicial: no son una validación completa de las extensiones.
Las pruebas recientes son `Hector-engine/tests/test_runtime_cancellation.py`,
`tools/native_progress_test.py` y `tools/progressive_chat_live_test.py`.

## Conexión HTTP actual

React consulta `/api/status` cada 450 ms durante la generación y mantiene POST
`/api/chat` para el resultado final. POST `/api/cancel` transmite la parada por
ID. Esto pertenece al agente Python; el SSE del servidor C es otra ruta.
[Detalles, arranque, cancelación y evidencia](PROGRESSIVE_NATIVE_RUNTIME.md).
