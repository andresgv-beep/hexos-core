# Plan: catálogo de herramientas por grupos

Propuesta del 2026-10-29, sobre `2673885`. Nada de esto está implementado.

## Problema

El modelo recibe las 49 herramientas de `catalog.model_tools()` en cada
generación, sea cual sea la intención: un saludo, una nota o una compresión de
película cargan lo mismo. Hay familias que se solapan (diez `nas.*`, seis
`note.*`, y `report`, `result`, `work`, `document` e `history` para cosas
cercanas). Con el 12B eso se nota como llamadas a la herramienta equivocada,
pseudollamadas en texto y respuestas que ignoran datos presentes.

Evidencia propia, no una medida general:

- [Auditoría del 2026-09-12](AUDITORIA_CONVERSACION_NATIVA.md): con el montaje y
  el historial originales, limitar el catálogo a `history.*` hizo que respondiera
  «Eres Andres.»; con el catálogo entero negaba saberlo o escribía una
  pseudollamada.
- `native.py`, `transcribe`: con unos 5.000 tokens de instrucciones y
  herramientas delante, el 12B dejaba de atender al audio; a solas, lo
  transcribía.
- `context.py` habla de «las 23 declaraciones de herramientas»: el catálogo ha
  doblado su tamaño desde entonces.

## Restricción que manda

Las declaraciones van en el bloque de sistema, al principio del prompt.
`recovery.py` lo dice: «El catálogo permanece estable para conservar el prefijo
KV». Cambiar el conjunto de herramientas invalida todo lo que viene detrás —la
conversación entera— y obliga a reprocesarlo. El diseño tiene que cambiar de
conjunto pocas veces y siempre igual para el mismo conjunto.

## Grupos propuestos

Cada herramienta ofrecida pertenece a un solo grupo. Reparto inicial, a revisar
contigo antes de cerrarlo:

| Grupo | Herramientas | Cuántas |
|---|---|---:|
| `nucleo` (siempre) | `history.recent`, `history.search`, `history.read`, `profile.recall`, `core.overview`, `task.current`, `task.focus`, `result.get`, `web.search`, `web.read` | 10 |
| `archivos` | `nas.locations`, `nas.directories`, `nas.directory_page`, `nas.shares`, `nas.find`, `nas.search`, `nas.browse`, `nas.file_open`, `nas.file_read` | 9 |
| `equipos` | `device.list`, `device.connect`, `device.forget`, `device.remote`, `device.identify`, `network.local`, `nas.read`, `nas.container` | 8 |
| `multimedia` (arrastra `archivos`) | `media.options`, `media.prepare`, `media.start`, `media.control`, `media.jobs`, `media.job` | 6 |
| `notas` | `note.save`, `note.list`, `note.get`, `note.show`, `note.hide`, `note.mark` | 6 |
| `informes` | `report.save`, `report.list`, `report.get`, `work.list`, `work.get`, `procedure.list`, `procedure.get`, `procedure.run`, `document.read`, `document.search` | 10 |

`multimedia` arrastra `archivos` porque `media.prepare` usa el `scan_id` de
`nas.find`. Las ocultas (`device.refresh`, `profile.remember`, `nas.index`)
siguen ocultas.

Las instrucciones de un grupo viajan con él. Hoy `POLICY` nombra `media_options`
y `media_prepare` aunque el turno no tenga nada que ver con multimedia; ese
párrafo pasa al grupo `multimedia` y entra en el bloque de sistema solo cuando
el grupo está activo. Como va en el mismo bloque que las declaraciones, no rompe
el prefijo más de lo que ya lo rompe el cambio de grupo.

## Cómo se eligen

1. **Al empezar el turno**, nunca a mitad: dentro del turno el conjunto queda
   fijo, salvo la vía de escape del punto 4.
2. **Un selector en la sesión auxiliar.** Ya existe (`send(..., auxiliar=True)`,
   marca `*`, con KV propio) y la usan `announce` y `extract_facts`. Prompt
   corto: la lista de grupos con una línea cada uno, la última respuesta del
   asistente y el mensaje nuevo; salida, un array JSON de nombres de grupo.
   Greedy y pocos tokens. Si la salida no es válida o nombra un grupo que no
   existe, se ofrece el catálogo entero en ese turno: el fallo del selector
   nunca deja al modelo sin una herramienta.
   No se eligen grupos por palabras clave: es el tipo de regla por frases que ya
   se retiró de Text.
3. **Grupos pegajosos.** Activo = `nucleo` + lo que pida el selector + los grupos
   de herramientas usadas en los últimos N turnos (de `tool_events`). Un grupo
   sale tras K turnos sin usarse. Las declaraciones se pintan siempre en el orden
   del catálogo, así que el mismo conjunto produce el mismo prompt byte a byte.
4. **Vía de escape.** Si el modelo llama a una herramienta de un grupo inactivo
   —puede pasar, porque el historial reinyecta llamadas antiguas—, la llamada se
   valida y se ejecuta igual que hoy: ofrecer no es autorizar, y los permisos no
   cambian. Su grupo se activa para el resto de la conversación. Si el turno
   acaba en pseudollamada o «no puedo», el reintento de formato usa el catálogo
   de lecturas completo, como ahora.
5. **Llamadas forzadas.** `require_read`, `begin_tool`, `listing_followup` y
   `explicit_read` añaden el grupo de su herramienta antes de pintar el prompt.

## Dónde va el código

- `catalog.py`: `GROUPS`, `GROUP_GUIDANCE` y un test que comprueba que cada
  herramienta ofrecida está en exactamente un grupo. Sin ese test, una
  herramienta nueva sin grupo desaparecería en silencio.
- `tool_groups.py` (nuevo): selector auxiliar y estado pegajoso por
  conversación. Se reinicia con `call({'type': 'reset'})`.
- `native.py`, `generate`: filtra `self.tools` por el conjunto activo antes de
  las reducciones que ya existen (solo lecturas al reparar, sin
  `profile_remember` al cosechar).
- `chat_backend/context.py`, `prepare`: llama al selector al empezar el turno.
- `chat_backend/turn.py` y `recovery.py`: los ganchos del punto 5 y la vía de
  escape.
- Héctor no cambia.

## Cómo se mide

Antes de activarlo por defecto, con el 12B, greedy y el mismo HNF:

- **Batería de intenciones**: los casos de la auditoría del 12 de septiembre y
  unas 30 peticiones repartidas por grupos, con mezclas («busca la película X y
  comprímela»: `archivos` + `multimedia`), continuaciones («¿y la otra?»),
  saludos y reproches.
- **Métricas**, catálogo entero frente a grupos:
  - acierto del selector: el grupo elegido contiene la herramienta necesaria;
  - primera llamada correcta;
  - pseudollamadas y reintentos de formato;
  - tokens y milisegundos de prefill por turno, en caliente y tras un cambio de
    grupo.
- Herramientas que ya existen: `tools/native_tools_audit.py`,
  `tools/native_conversation_audit.py` y `tools/prompt_audit.py`.
- Criterio: se activa si mejora la elección sin empeorar los casos que ya
  funcionaban, y si el coste de los cambios de grupo es asumible. Si no, se
  queda detrás de una opción.

## Después, por separado

- **Fusionar las que se pisan**, con la medida en la mano. Por ejemplo,
  `nas.find` con `nas.search`, o `nas.directories` con `nas.directory_page`.
  Toca ejecutores y pruebas, así que va en otro cambio.
- **Alternativa sin romper el prefijo**: un núcleo fijo y una herramienta
  `tools_open(grupo)` cuya respuesta trae las declaraciones del grupo. No toca
  el bloque de sistema, pero depende de que el 12B llame a herramientas que no
  están declaradas ahí. Solo si el coste de reprocesar en la medida sale alto.
- El adaptador de `experiments/lmstudio` puede usar los mismos grupos para
  comparar modelos con el mismo montaje.
