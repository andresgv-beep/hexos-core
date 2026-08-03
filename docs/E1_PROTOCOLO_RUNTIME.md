# E1 — Protocolo de `helios_runtime`

**Estado:** propuesto, v2 tras revisión · **Fase:** E1 del [plan de evacuación](PLAN_EVACUACION_COGNITIVA.md)
**Base congelada:** `hector@1bca9b5`, oráculo en `informes/e0_base_qwen8b.json`

Hoy HexOS lanza `helios_chat` y deduce el estado leyendo `tú>` y `helios>` de
su salida de terminal. Funciona, pero cualquier cambio de color, de saludo o
de idioma rompe el transporte, y el estado real (posición del KV, razón de
parada, tokens) hay que adivinarlo de una línea de estadísticas.

`helios_runtime` es la ruta paralela: **mismo motor, eventos tipados**.

## Alcance, tajante

Este ejecutable **no tiene mente**. No conoce identidad, memoria, perfiles,
actos, registro social ni presupuestos cognitivos. Recibe mensajes con rol,
aplica la plantilla del modelo, genera y emite eventos. Todo lo demás sigue
viviendo en `helios_chat` hasta las fases E2-E5.

Lo que **sí** es suyo según la tabla de propiedad del plan: HNF, tokenizer,
plantillas del modelo, KV, prefill, decode, sampling y adaptadores
multimodales.

## 1. Transporte

JSONL: **una petición por línea** en `stdin`, **un evento por línea** en
`stdout`. `stderr` es log humano y nunca lleva protocolo.

La codificación es intercambiable; el contrato no.

## 2. Ciclo de vida: toda petición tiene un terminal

**Cada petición lleva un `request_id` único en la sesión y recibe exactamente
un evento terminal.** Sin esto el cliente no puede saber si algo se ejecutó,
y un adjunto que comparte id con su turno vuelve ambiguo qué terminó.

| Petición | Terminal |
|---|---|
| `turn` | `completed` \| `error` |
| `reset` | `result` \| `error` |
| `status` | `result` \| `error` |
| `attachment` | `result` \| `error` |
| `cancel` | `result` \| `error` |
| `shutdown` | `result`, y después el proceso termina |

```jsonc
{"type":"turn","request_id":"r1",
 "messages":[{"role":"user","content":"hola"}],
 "attachment_ids":[],
 "generation":{"temperature":0.7,"max_visible_tokens":150,"max_thinking_tokens":400}}

{"type":"attachment","request_id":"a1","kind":"rgb8",
 "width":192,"height":192,"stride":576,"bytes":110592}
// … seguido de 110592 bytes crudos y un \n

{"type":"cancel","request_id":"c1","target":"r1"}
{"type":"reset","request_id":"x1"}
{"type":"status","request_id":"s1"}
{"type":"shutdown","request_id":"q1"}
```

**`messages` son los mensajes NUEVOS**, no la conversación entera: el KV
mantiene la historia igual que hoy hace `helios_chat`, y reenviarla obligaría
a reprocesar el contexto en cada turno. Quien quiera empezar de cero manda
`reset`.

Un `attachment` se identifica por su **propio** `request_id` y el turno lo
referencia en `attachment_ids`. El adjunto se consume al usarlo; referenciar
uno inexistente o ya consumido es `error` con código `unknown_attachment`.

### Roles y plantillas

Los roles son los del modelo. **El runtime no promete que cualquier secuencia
de roles sea representable**: Gemma 4, por ejemplo, no admite un `system`
nuevo entre turnos. Héctor aplica únicamente lo que su plantilla soporta y,
si la secuencia no lo es, responde `error` con código
`unsupported_role_sequence` en vez de inventarse un encaje.

Cómo entregar instrucciones efímeras del CK sin contaminar el transporte lo
decide **E2**, no este documento.

## 3. Eventos

```jsonc
{"type":"ready","protocol":2,
 "model":{"architecture":"qwen2","max_seq_len":4096,"multimodal":false,
          "vision_adapter":null}}

{"type":"prefill","request_id":"r1","tokens":12,"ms":45.2}
{"type":"thinking","request_id":"r1","tokens":40}        // latido, sin contenido
{"type":"text_delta","request_id":"r1","text":"Hola"}    // solo texto visible
{"type":"notice","request_id":"r1","text":"texto truncado a 8192 caracteres"}
{"type":"context_compacted","request_id":"r1",
 "cache_position_before":3900,"cache_position_after":1200}

{"type":"completed","request_id":"r1",
 "visible_text":"Hola, ¿qué tal?",
 "finish_reason":"eos",                    // eos|max_tokens|stop|cancelled
 "usage":{"prefill_tokens":12,"generated_tokens":9,"thinking_tokens":3},
 "timings":{"prefill_ms":45.2,"decode_ms":180.0,"tokens_per_second":50.1},
 "model_state":{"cache_position_before":222,"cache_position":231,
                "max_seq_len":4096}}

{"type":"result","request_id":"x1","ok":true,
 "model_state":{"cache_position_before":231,"cache_position":0,"max_seq_len":4096}}

{"type":"error","request_id":"r1","code":"context_full","message":"…"}
```

Se llama **`text_delta`** y no `token` a propósito: una cadena JSON debe ser
UTF-8 válida, así que un fragmento puede agrupar varios tokens o esperar a
completar un carácter multibyte. El recuento real vive en `usage`.

El contenido del pensamiento **no se emite**: `thinking` es un latido con el
contador. Si algún día hace falta, será un campo nuevo y opt-in.

`context_compacted` es un evento estructurado, no un `notice` de texto: es la
**única** forma —junto a un `reset` confirmado— de que la posición del KV baje
legítimamente. Un aviso cualquiera no autoriza un retroceso.

## 4. Semántica del KV ante fallo y cancelación

Sin esto escrito, dos implementaciones razonables divergen:

- **Error antes de emitir texto visible:** el KV vuelve a
  `cache_position_before`. El turno no dejó rastro.
- **Error después de emitir texto:** se conserva lo emitido; `error` incluye
  `model_state` con la posición real.
- **Cancelación:** se conserva **exactamente el texto ya emitido**. El turno
  termina con `completed` y `finish_reason: cancelled`, no con `error`: hubo
  respuesta parcial y el cliente ya la pintó.
- `completed`, `error` y `result` llevan siempre `cache_position_before` y
  `cache_position`, para que el cliente pueda auditar el efecto de cada
  petición sin inferirlo.

## 5. Invariantes

Son la especificación real y las verifica `tools/protocolo_test.py` sobre una
traza **ordenada y con dirección**:

```jsonl
{"direction":"request","payload":{"type":"turn","request_id":"r1", …}}
{"direction":"event","payload":{"type":"prefill","request_id":"r1", …}}
```

Sin dirección ni orden no se puede comprobar causalidad — por ejemplo, que una
bajada del KV ocurrió *después* de su `reset` y no antes.

1. `ready` aparece exactamente una vez y es el primer evento.
2. Cada petición recibe **exactamente un terminal**, del tipo que le
   corresponde en la tabla de §2.
3. El terminal es el **último** evento de su `request_id`: nada después, ni
   siquiera un `notice`.
4. Los `text_delta` van entre el `prefill` de su petición y su terminal, y
   **todo turno que emite texto emite antes su `prefill`**.
5. Concatenar los `text_delta.text` da exactamente `completed.visible_text`.
6. `cache_position` no decrece salvo inmediatamente después de un `reset`
   confirmado o de un `context_compacted` del mismo `request_id`.
7. Todo evento con `request_id` corresponde a una petición **ya recibida** en
   la traza; los `request_id` no se repiten.
8. Solo se emiten tipos de evento conocidos, con sus campos obligatorios.
9. `completed` trae `finish_reason`, `usage`, `timings` y `model_state` con
   ambas posiciones.
10. **El protocolo no define campos ni tipos de evento de dominio cognitivo.**
    Se verifica sobre las **claves** del esquema, nunca sobre el texto que
    genera el modelo: una respuesta legítima puede hablar de memoria o de
    perfiles y eso no es una fuga.

## 6. Pruebas antes de implementar

`tools/protocolo_test.py` corre sin GPU sobre fixtures sintéticas y después
sobre trazas reales. **Cada invariante tiene al menos una fixture que lo
viola**, aislada para que la cace ese invariante y no otro: una prueba que
solo pasa con datos buenos no demuestra nada.

## 7. Criterio de salida de E1

- Texto y visión funcionan por las dos rutas.
- La batería del oráculo no detecta diferencias atribuibles al transporte
  (`tools/oraculo.py --diff` devuelve 0).
- La UI conserva streaming, avisos, **cancelación** y estado.
- `helios_chat` sigue intacto: es el oráculo, no se toca.

Cualquier diferencia del oráculo bloquea la fase.
