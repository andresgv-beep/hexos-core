# E1 — Protocolo de `helios_runtime`

**Estado:** propuesto · **Fase:** E1 del [plan de evacuación](PLAN_EVACUACION_COGNITIVA.md)
**Base congelada:** `hector@1bca9b5`, oráculo en `informes/e0_base_qwen8b.json`

Hoy HexOS lanza `helios_chat` y deduce el estado leyendo `tú>` y `helios>` de
su salida de terminal. Funciona, pero cualquier cambio de color, de saludo o
de idioma en el REPL rompe el transporte, y el estado real (posición del KV,
razón de parada, tokens) hay que adivinarlo de una línea de estadísticas.

`helios_runtime` es la ruta paralela: **mismo motor, eventos tipados**.

## Alcance, tajante

Este ejecutable **no tiene mente**. No conoce identidad, memoria, perfiles,
actos, registro social ni presupuestos cognitivos. Recibe mensajes con rol,
aplica la plantilla del modelo, genera y emite eventos. Todo lo demás sigue
viviendo en `helios_chat` hasta las fases E2-E5.

Lo que **sí** es suyo, según la tabla de propiedad del plan: HNF, tokenizer,
plantillas del modelo (ChatML/Gemma), KV, prefill, decode, sampling y
adaptadores multimodales.

Lo que **nunca** debe aparecer en este protocolo: `acto`, `registro`,
`contrato`, `perfil`, `memoria`, `identidad`. Hay una prueba automática que lo
comprueba (§5) porque una frontera que no se verifica se erosiona sola.

## 1. Transporte

JSONL en ambos sentidos: **una petición por línea** en `stdin`, **un evento
por línea** en `stdout`. `stderr` queda para el log humano del motor (carga,
CUDA Graph, avisos de arranque) y nunca lleva protocolo.

La codificación es lo intercambiable; el contrato no. Si mañana conviene
protobuf o un socket, los tipos de abajo no cambian.

## 2. Peticiones

```jsonc
{"type":"turn","request_id":"r1",
 "messages":[{"role":"user","content":"hola"}],
 "generation":{"temperature":0.7,"max_visible_tokens":150,"max_thinking_tokens":400}}

{"type":"reset","request_id":"r2"}          // vacía el KV; la sesión sigue viva
{"type":"status","request_id":"r3"}         // estado sin generar
{"type":"shutdown"}
```

**`messages` son los mensajes NUEVOS**, no la conversación entera: el KV
mantiene la historia igual que hoy hace `helios_chat`, y re-enviarlo todo
obligaría a reprocesar el contexto en cada turno. Quien quiera empezar de
cero manda `reset`.

Los roles son los del modelo (`system`, `user`, `assistant`). El runtime los
pasa por la plantilla que corresponda al HNF y no interpreta su contenido: un
contrato del CK viaja como un `system` normal y corriente.

### Adjuntos binarios

El payload no cabe en JSON sin pagar base64, así que va crudo detrás de su
cabecera, igual que el `/adjunto-rgb8` que ya usa HexOS:

```text
{"type":"attachment","request_id":"r1","kind":"rgb8","width":192,"height":192,"stride":576,"bytes":110592}\n
<110592 bytes crudos>\n
```

El adjunto queda pendiente y lo consume el siguiente `turn` con el mismo
`request_id`. Un solo adjunto pendiente, como el contrato visual v1.

## 3. Eventos

```jsonc
{"type":"ready","protocol":1,
 "model":{"architecture":"qwen2","max_seq_len":4096,"multimodal":false,
          "vision_adapter":null}}

{"type":"prefill","request_id":"r1","tokens":12,"ms":45.2}
{"type":"thinking","request_id":"r1","tokens":40}        // latido, no contenido
{"type":"token","request_id":"r1","text":"Hola"}         // SOLO texto visible
{"type":"notice","request_id":"r1","text":"texto truncado a 8192 caracteres"}

{"type":"completed","request_id":"r1",
 "visible_text":"Hola, ¿qué tal?",
 "finish_reason":"eos",                                  // eos|max_tokens|stop|cancelled
 "usage":{"prefill_tokens":12,"generated_tokens":9,"thinking_tokens":3},
 "timings":{"prefill_ms":45.2,"decode_ms":180.0,"tokens_per_second":50.1},
 "model_state":{"cache_position":231,"max_seq_len":4096}}

{"type":"error","request_id":"r1","code":"context_full","message":"..."}
```

El contenido del pensamiento **no se emite**: `thinking` es un latido con el
contador, igual que el `(pensando…)` de hoy. Si algún día hace falta el
contenido, será un campo nuevo y opt-in, no un cambio silencioso.

## 4. Invariantes

Son la especificación real, y las verifica la prueba de conformidad:

1. `ready` aparece **exactamente una vez** y antes que cualquier otro evento.
2. Cada `turn` produce **exactamente un evento terminal** (`completed` o
   `error`) con su mismo `request_id`.
3. Los `token` de un `request_id` van entre su `prefill` y su terminal.
4. **Concatenar los `token.text` da exactamente `completed.visible_text`.**
   Sin esto, un cliente que renderiza en streaming y otro que espera al final
   verían cosas distintas.
5. `model_state.cache_position` no decrece dentro de una sesión, salvo tras
   `reset` o compactación (que emite `notice`).
6. `usage.generated_tokens > 0` o `finish_reason` explica por qué no
   (un turno mudo es `completed` con texto vacío, nunca silencio).
7. Ningún evento contiene claves ni valores de dominio cognitivo.
8. Todo `request_id` de un evento corresponde a una petición recibida.

## 5. Pruebas antes de implementar

`tools/protocolo_test.py` valida las ocho invariantes sobre una traza JSONL.
Corre sin GPU sobre fixtures sintéticas —incluidas trazas deliberadamente
rotas, para comprobar que la prueba sabe fallar— y después sobre trazas reales
del ejecutable.

Una prueba que solo se ejecuta sobre datos buenos no demuestra nada: cada
invariante tiene su fixture que la viola.

## 6. Criterio de salida de E1

- Texto y visión funcionan por las dos rutas.
- La batería del oráculo **no detecta diferencias atribuibles al transporte**
  (`tools/oraculo.py --diff` devuelve 0 en política, estructura y memoria).
- La UI conserva streaming, avisos, cancelación y estado.
- `helios_chat` sigue **intacto**: es el oráculo, no se toca.

Cualquier diferencia del oráculo bloquea la fase.
