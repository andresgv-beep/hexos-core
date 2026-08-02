# Plan de evacuación cognitiva

**Estado:** propuesto, pendiente de comenzar  
**Fecha:** 2026-08-02  
**Repos implicados:** `Hector-engine` y `hexos-core`  
**Bases auditadas:** `Hector-engine@1bca9b5`, `hexos-core@74b5741`

## 0. Motivo

El prototipo ya demuestra inferencia, conversación, memoria, compactación,
visión y UI, pero las responsabilidades cognitivas terminaron concentradas en
`Hector-engine/helios_chat.cpp` y `Hector-engine/src/ck_policy.*`.

`helios_chat.cpp` tiene actualmente 1.958 líneas y mezcla:

- carga del modelo, KV, prefill y decode;
- protocolo de terminal;
- identidad y perfil;
- memoria, hechos y candidatos;
- reflexión, destilación y consolidación;
- continuidad de artefactos;
- clasificación del turno y registro social;
- presupuestos de pensamiento y respuesta;
- comandos de usuario.

Además, HexOS no consume una API del motor: lanza `helios_chat` y deduce el
estado leyendo `tú>` y `helios>` de su salida. Esto permitió conectar la UI sin
romper el prototipo, pero no puede ser la interfaz definitiva.

El objetivo de este plan no es rediseñar la personalidad ni mejorar respuestas.
Es **evacuar el comportamiento existente hacia sus propietarios correctos sin
cambiarlo durante el traslado**.

## 1. Reglas de emergencia

Desde que empiece la evacuación:

1. No se añade lógica cognitiva nueva a `Hector-engine`.
2. No se corrige conducta añadiendo texto a un prompt sin identificar primero
   el estado o contrato que falta.
3. Extracción y mejora de comportamiento son trabajos separados.
4. Cada fase mantiene compilables ambos repos.
5. Nada se borra hasta que la ruta nueva alcance paridad y exista rollback.
6. Una fase cambia un solo eje: transporte, política, memoria o prompting.
7. `helios_chat` es el oráculo temporal, no la arquitectura destino.
8. Los contratos efímeros nunca se guardan en transcripción o memoria.
9. Los candidatos de memoria nunca adquieren autoridad sin confirmación.
10. E2B/E4B, cuantización y rendimiento quedan fuera de esta evacuación.

## 2. Propiedad definitiva

| Componente | Es propietario de | No puede decidir |
|---|---|---|
| Héctor | HNF, tokenizer, plantillas del modelo, tensores, KV, prefill, decode, sampling y adaptadores multimodales | identidad, relación, memoria, acto o registro |
| CK | `TurnFrame`, `ResponseContract`, alcance, parada y `MemoryDelta` propuesto | persistencia o verdad autoritativa |
| HERA | identidad, perfil, relación, continuidad, autoridad de hechos, correcciones, promoción y consolidación | kernels, VRAM o formato de conversación del modelo |
| Memory Core | almacenar, indexar, consultar, versionar y mover recuerdos | importancia, confirmación o personalidad |
| HexOS | procesos, perfiles activos, recursos, transporte, API y telemetría | contenido de la identidad o reglas cognitivas |
| UI | entrada, adjuntos, visualización y controles explícitos | inferir memoria o modificar estado ocultamente |

### Flujo de un turno

```text
UI
  -> HexOS selecciona profile_id y sesión
  -> HERA entrega estado autoritativo y recuerdos relevantes
  -> CK produce TurnFrame + ResponseContract
  -> adaptador convierte estado y contrato en mensajes tipados
  -> Héctor aplica la plantilla del modelo y genera
  -> UI recibe texto y telemetría
  -> CK propone MemoryDelta
  -> HERA valida y ordena persistencia a Memory Core
```

La reflexión y consolidación posteriores no bloquean el turno visible.

## 3. Tipos mínimos en la frontera

La evacuación no necesita implementar todo CK v3. Solo requiere una frontera
pequeña, observable y versionada.

```text
TurnRequest
  request_id
  session_id
  profile_id
  messages[]              # roles y contenido reales
  attachment_refs[]
  response_contract?      # efímero
  generation_config

TurnEvent
  ready | prefill | thinking | token | completed | notice | error
  request_id
  payload

TurnResult
  visible_text
  finish_reason
  usage
  timings
  model_state
```

Héctor puede recibir mensajes tipados y aplicar ChatML o Gemma según el HTF.
No recibe `UserProfile`, `Relationship` ni ficheros de memoria: recibe el
contexto ya seleccionado que necesita para esa generación.

## 4. Estrategia: ruta paralela, no gran reescritura

La ruta actual continúa funcionando mientras se construye esta ruta:

```text
HexOS -> helios_chat -> stdout con marcadores       # legacy/oráculo
HexOS -> helios_runtime -> eventos tipados          # nueva
```

`helios_runtime` es un nombre provisional para un ejecutable fino construido
sobre las mismas clases de Héctor. Puede usar JSONL inicialmente si facilita
la inspección; el contrato, no la codificación, es lo estable.

El proceso separado conserva aislamiento de fallos CUDA y evita enlazar de
golpe C, C++ y la UI en un solo binario. HexOS sigue siendo quien arranca,
vigila y reinicia el motor.

La selección legacy/nueva debe permanecer explícita durante la migración,
por ejemplo mediante una opción de desarrollo. No será una bifurcación
permanente.

## 5. Fases

### E0 — Congelar y medir el oráculo

**Trabajo**

- Congelar los casos de regresión de CK v5.
- Añadir conversaciones de corrección, cambio/retorno de tema, continuidad de
  artefacto, cierre breve, memoria y perfil vacío.
- Registrar salida visible, `act`, registro, memoria escrita, finish reason y
  eventos de compactación.
- Inventariar todos los prompts activos y asignarles propietario.

**No se hace**

- No se cambia ningún prompt.
- No se compara E2B contra E4B.
- No se corrigen respuestas que no gusten durante la captura.

**Barrera de salida**

- Un comando reproduce la batería sin UI y guarda un informe comparable.
- Los fallos conocidos quedan etiquetados; no se confunden con regresiones.

**Rollback:** no aplica; solo pruebas y telemetría.

### E1 — API tipada de Héctor en paralelo

**Trabajo en `Hector-engine`**

- Extraer de `helios_chat` una sesión de inferencia reutilizable: carga,
  mensajes, adjuntos, generación, reset y estadísticas.
- Crear el ejecutable fino `helios_runtime` con eventos tipados.
- Mantener plantillas ChatML/Gemma y peculiaridades de tokenizer en Héctor.
- Mantener `helios_chat` usando la misma sesión o, durante la transición, las
  mismas primitivas verificadas.

**Trabajo en `hexos-core`**

- Añadir un cliente del protocolo en paralelo al parser del REPL.
- Traducir eventos tipados a los mismos eventos SSE que ya consume la UI.

**Barrera de salida**

- Texto y visión funcionan por ambas rutas.
- La batería E0 no detecta diferencias atribuibles al transporte.
- La UI no pierde streaming, avisos, cancelación ni estado.

**Rollback:** HexOS vuelve a lanzar `helios_chat`.

### E2 — Evacuar CK sin cambiar su política

**Trabajo**

- Implementar en `hexos-core` los tipos reales de CK v5: `TurnFrame`,
  `ResponseContract` y estado de artefacto.
- Portar primero, literalmente, el comportamiento probado de
  `Hector-engine/src/ck_policy.*`.
- Ejecutar la misma batería sobre ambas implementaciones y comparar contratos.
- Hacer que HexOS entregue el contrato efímero a la ruta tipada.

**No se hace**

- No se crea todavía un Cortex aprendido.
- No se amplía la taxonomía de actos durante el port.
- No se ajustan presupuestos ni temperatura.

**Barrera de salida**

- Para todo el corpus E0, CK antiguo y nuevo producen el mismo frame/contrato.
- La ruta nueva conversa sin usar `ck_policy` de Héctor.

**Rollback:** seleccionar la política legacy sin cambiar el motor.

### E3 — Evacuar HERA con almacenamiento legacy compatible

**Trabajo**

- Portar desde `helios_chat` carga de recuerdos, hechos, candidatos,
  deduplicación y autoridad de correcciones.
- Mantener inicialmente compatibilidad de lectura con `facts.md`,
  `episodic.md` y `candidates.md`.
- Introducir `UserProfile`, `Relationship` y estados
  `candidate | confirmed | superseded`.
- Hacer que una corrección sea una transición auditable, no otra línea.
- Separar recuperación previa al turno de reflexión posterior.

**No se hace**

- No se cambia simultáneamente a embeddings o una base vectorial.
- No se escribe todavía en HNF-EXT.
- No se borra memoria legacy.

**Barrera de salida**

- Perfil vacío no recibe datos de otro perfil.
- Una corrección sustituye al hecho anterior y puede auditarse.
- Los candidatos no entran en el prompt como hechos.
- Reiniciar conserva exactamente el estado confirmado.

**Rollback:** almacén legacy en solo lectura más copia de seguridad previa a
cualquier migración.

### E4 — Sacar reflexión y consolidación del turno

**Trabajo**

- Convertir la salida posterior al turno en `MemoryDelta` estructurado.
- Validar el delta en HERA antes de persistir.
- Ejecutar reflexión y consolidación en cola, fuera del camino visible.
- Usar el checkpoint mínimo de HERA v3: hechos estables, tareas abiertas,
  proyectos activos, intención actual y referencias calientes.
- Introducir Memory Core como backend detrás de HERA, no como decisor.

**Barrera de salida**

- La latencia visible no incluye reflexión/destilación.
- Ninguna salida libre del modelo se escribe directamente como verdad.
- Cerrar o compactar no pierde tareas, proyecto activo ni correcciones.

**Rollback:** desactivar trabajadores posteriores; los turnos siguen
funcionando y la cola permanece recuperable.

### E5 — Centralizar el prompting y hacerlo derivado

**Trabajo**

- Mantener cuatro familias explícitas y versionadas:
  1. identidad estable;
  2. contexto autoritativo seleccionado por HERA;
  3. contrato efímero producido por CK;
  4. extracción/consolidación posterior de HERA.
- Registrar versión y hash de cada renderer en telemetría.
- Prohibir literales cognitivos en Héctor mediante una comprobación sencilla.
- Mantener en Héctor únicamente las plantillas sintácticas propias del modelo.

**Barrera de salida**

- Se puede explicar qué texto recibió el modelo y quién originó cada bloque.
- Ningún contrato efímero aparece después en memoria o transcripción.
- Cambiar de arquitectura de modelo no cambia las reglas cognitivas.

**Rollback:** seleccionar la versión anterior del renderer, no editar código
del motor.

### E6 — Cortar la ruta legacy y adelgazar `helios_chat`

**Trabajo**

- Promover el protocolo tipado como ruta normal de HexOS.
- Dejar `helios_chat` como cliente de diagnóstico de la API, sin memoria ni
  política propias.
- Eliminar el parser de marcadores `tú>`/`helios>` de producción.
- Eliminar de Héctor la política cognitiva solo después de una versión estable.

**Barrera de salida**

- La UI no lanza ni analiza un REPL.
- Buscar memoria, identidad, `colega`, consolidación o candidatos en el código
  de producción de Héctor no devuelve lógica cognitiva.
- Ambos repos compilan y pasan sus pruebas desde limpio.
- Una semana de uso real no requiere volver a la ruta legacy.

**Rollback:** conservar una versión etiquetada anterior; no mantener dos
arquitecturas activas indefinidamente.

### E7 — Cortex aprendido, solo después de evacuar

Cortex no forma parte del rescate. Se evalúa cuando CK y HERA tengan tipos y
telemetría estables.

Su primera función sería proponer transiciones cerradas —continuar, cambiar,
retomar, corregir, referir artefacto y cerrar—. HERA mantiene la autoridad y
las reglas deterministas conservan fallback. Nunca genera la respuesta ni
escribe memoria directamente.

## 6. Orden de commits

Cada fase se divide en commits pequeños y reversibles:

1. tipos y pruebas;
2. implementación paralela;
3. comparación contra legacy;
4. cutover opt-in;
5. promoción por defecto;
6. retirada del legacy en un commit separado.

Si una fase necesita ambos repos, primero se añade compatibilidad al productor
y después se consume desde el otro. Nunca se rompe un repo esperando un commit
futuro del segundo.

No se mezclan en un mismo commit:

- movimiento de código y cambio de conducta;
- migración de datos y cambio de esquema;
- transporte nuevo y prompting nuevo;
- mejora de calidad y optimización de rendimiento.

## 7. Matriz mínima de aceptación

| Caso | Invariante |
|---|---|
| saludo de perfil nuevo | sin familiaridad heredada ni oferta automática |
| charla de perfil conocido | conserva registro sin ampliar el acto |
| pregunta técnica | responde y termina |
| código + “velocidad” | continúa el artefacto, no lo trata como trivial |
| documento + “resume” | resume, no asesora ni reescribe |
| “no, me refiero a…” | corrige sin defenderse |
| profesión falsa -> corrección | anterior `superseded`, nueva `confirmed` |
| cambio de tema y retorno | conserva ambos estados sin mezclarlos |
| imagen + pregunta posterior | conserva referencia al artefacto |
| “todo listo” | reconocimiento breve, sin pregunta de servicio |
| reinicio | recupera hechos confirmados y tareas abiertas |
| segundo perfil | cero fuga de identidad, hechos o relación |

La comparación registra también latencia, tok/s, memoria, turnos mudos,
bucles, idioma y razón de terminación. La evacuación no se acepta si degrada
velocidad más de la variación normal medida o altera calidad sin autorización.

## 8. Definición de terminado

La evacuación termina cuando:

- HexOS orquesta turnos mediante una API tipada;
- Héctor no contiene política cognitiva ni acceso a perfiles/memoria;
- CK produce contratos observables y efímeros;
- HERA posee estado, autoridad y ciclo de memoria;
- Memory Core persiste sin decidir;
- los prompts son renderizaciones versionadas de estado estructurado;
- UI, texto y visión conservan el comportamiento verificado;
- cada dato puede responder: quién lo creó, con qué autoridad, dónde vive y
  qué lo sustituyó;
- añadir otro modelo no exige copiar la personalidad a otro prompt.

## 9. Primer paso autorizado

Comenzar únicamente por **E0**. Antes de extraer código hay que convertir el
comportamiento actual en un oráculo reproducible. Si no podemos demostrar qué
hace hoy, tampoco podremos demostrar que una evacuación lo conservó.


---

## E0 — Resultado (2026-08-02)

**Entregables:** `tools/oraculo.py` (batería reproducible sin UI) y
`docs/E0_INVENTARIO_PROMPTS.md` (15 bloques de prompt y 11 mecanismos, con su
propietario destino).

Primera captura sobre `qwen3_8b.hnf`, 10 casos y 20 turnos, perfiles
temporales desechables:

```
turnos 20 · mudos 0 · fugas de contrato 0 · CJK 0 · repeticiones 0
presupuestos agotados 0 · pensamientos cortados 8 · tokens medios 239,8
ofertas de servicio 4
```

**Fallos conocidos etiquetados** (no son regresiones; son el estado congelado):

1. *cambio_y_retorno_de_tema* — la respuesta al turno 1 y al 3 es **idéntica
   palabra por palabra** ("¿Y cómo te va con esos kernels? 😊"). No conserva
   los dos estados: los colapsa. Es el caso que la matriz de aceptación exige
   y hoy falla.
2. *cambio de tema* — "¿te gusta el mar?" produce tres ofertas de servicio
   ("¿En qué puedo ayudarte?"): el registro se pierde al salir del tema.
3. *memoria_confirmada* — recupera el nombre pero cierra con coletilla; y en
   el primer turno comenta el nombre en vez de responder.
4. *documento_y_resume* y *artefacto_y_velocidad* — el acto es correcto
   (`resumir`, `continuar_artefacto`) pero el alcance no se respeta: 490 y 319
   tokens para lo que debería ser breve.
5. *perfil_vacio* — correcto y sin fuga, pero responde "no tengo información
   en la base de datos del sistema", registro de máquina.

**Lo que la captura confirma que SÍ funciona hoy** y la evacuación no puede
romper: cero turnos mudos, cero fugas del contrato interno, cero mezcla de
idiomas, el acto se clasifica bien en los diez casos, el perfil vacío no
hereda datos de otro perfil, y la despedida sale limpia.

Uso:

```bash
python3 tools/oraculo.py --model <hnf> --engine <helios_chat> \
    --env HELIOS_EMBED_MMAP=1 --salida informes/base.json
python3 tools/oraculo.py --diff informes/base.json informes/tras_e1.json
```

El `--diff` compara **acto y registro** turno a turno además del texto: la
política es lo que la evacuación debe conservar; el texto varía por muestreo
aunque no cambie nada.

**Barrera de salida de E0: cumplida.** Un comando reproduce la batería sin UI,
guarda informe comparable y los fallos conocidos quedan etiquetados. E1 puede
empezar.
