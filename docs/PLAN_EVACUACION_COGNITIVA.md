# Plan de evacuación cognitiva

La dirección de producto posterior es [un modelo y un chat](AGENTE_DOMESTICO_PLAN.md).
Los informes E2/E3/E4 documentan el port, memoria y sesiones ya existentes;
no se declara completado todo el plan ni activado todo ello en Python.
[Mapa vigente](../IMPLEMENTATION_STATUS.md).

**Estado:** plan histórico iniciado y con hitos implementados (E2, E3 y E4);
no es una lista actual de trabajo sin comenzar.
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

**Alcance del producto durante esta evacuación:** una instalación local y un
propietario. Varias sesiones significan chats o agentes aislados del mismo
propietario, no multiusuario. Cuentas, autenticación y permisos entre personas
quedan fuera de alcance hasta que exista un requisito explícito y medido.

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
| HexOS | procesos, perfil local, sesiones, recursos, transporte, API y telemetría | contenido de la identidad o reglas cognitivas |
| UI | entrada, adjuntos, visualización y controles explícitos | inferir memoria o modificar estado ocultamente |

### Flujo de un turno

```text
UI
  -> HexOS resuelve el perfil local y activa la sesión elegida
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

### E8 — Agente de código, solo después de validar Cortex

Probar una secuencia tipada entre el modelo conversacional y un coder sobre una
única GPU. Para la persona sigue siendo un solo turno de Helios: la UI muestra
estados mecánicos mientras el coder produce el artefacto y, al terminar, el
modelo de texto redacta la respuesta visible sobre el resultado real.

El diseño, los contratos `CodeTask`/`CodeResult`, la prioridad de GPU y las
barreras están en
[`AGENTES_ESPECIALISTAS_PLAN.md`](AGENTES_ESPECIALISTAS_PLAN.md). No forma parte
del rescate E0-E6 y no autoriza todavía otra residencia de modelo.

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

---

## E0 — Resultado y cierre (2026-08-02)

**Entregables:** `tools/oraculo.py` (batería reproducible sin UI) y
`docs/E0_INVENTARIO_PROMPTS.md` (15 bloques de prompt y 11 mecanismos con su
propietario destino; ninguno de los 15 pertenece a Héctor).

La batería cubre los 13 casos de la matriz de aceptación, incluidos los tres
que exigen más de un turno o más de un proceso:

- **imagen y pregunta posterior**: el adjunto viaja por el mismo protocolo
  binario `/adjunto-rgb8` que usa HexOS; se salta con motivo explícito si el
  modelo no declara visión.
- **reinicio con recuperación**: dos sesiones (dos procesos) sobre el mismo
  perfil, la primera con consolidación activada. Sin esto la persistencia es
  indemostrable.
- **hecho falso → corrección**: escribe un hecho, lo corrige y comprueba el
  estado resultante en `facts.md` y `candidates.md`.

Cada sesión registra además **qué se escribió en memoria** (delta por fichero
con las líneas nuevas), porque la memoria es estado y el estado es justo lo
que la evacuación debe conservar.

### Base certificada

```
hector@1bca9b5 · qwen3_8b.hnf sha256 164dca9366fc… · HELIOS_EMBED_MMAP=1
13 casos · 1 saltado (visión) · 27 turnos · 0 fallos de motor
mudos 0 · fugas de contrato 0 · CJK 0 · repeticiones 0
ofertas de servicio 2 · pensamientos cortados 6 · presupuestos agotados 1
respuestas idénticas 1 · tokens medios 219,7
```

Las cifras de defectos oscilan entre capturas del mismo binario (1-2 ofertas
de servicio, 6 pensamientos cortados): son **rangos**, no constantes. Una
comparación posterior debe mirar el orden de magnitud, no la igualdad exacta.

El informe guarda ruta, tamaño y SHA256 del HNF, SHA256 y mtime del binario,
commit de ambos repos y **todas** las variables `HELIOS_*` que verá el motor,
separando las pasadas por `--env` de las heredadas del shell: el proceso hijo
hereda el entorno, así que registrar solo las explícitas dejaba la base
irreproducible sin que nadie lo notara. También el `returncode` de cada
sesión: un motor que muere a mitad puede dejar turnos capturados y parecer una
captura sana.

Caso de visión verificado aparte sobre `gemma4-e2b-it-multimodal.hnf`:
`continuar_artefacto` correcto, "Veo un círculo rojo sólido" y, al turno
siguiente sin imagen, "Era rojo" — la referencia al artefacto sobrevive.

### Fallos conocidos etiquetados (estado congelado, no regresiones)

1. **La corrección no sustituye el hecho** — el caso más grave y el que
   justifica E3. En conversación se corrige impecable ("corrijo: eres
   ingeniero, no fontanero"), pero en memoria queda
   `facts.md: - La persona dijo textualmente: "soy fontanero"` y
   `candidates.md: - Se llama Andrés y es fontanero.` **El hecho falso
   sobrevive y nada queda marcado como sustituido.** Sin el registro de
   memoria este caso habría figurado como pasado.
2. **Los candidatos se INVENTAN identidades.** El caso de perfil vacío
   preguntando "¿qué sabes de mí?" escribió en `candidates.md`:
   `- Se llama Ana y vive en Bilbao.` **Nada de eso existe en ninguna parte:
   ni en el perfil, ni en el prompt, ni en la conversación.** El extractor
   fabricó una identidad completa y la guardó. La invariante "cero fuga"
   técnicamente pasa —no viene de otro perfil— pero el resultado es peor: no
   hay filtración, hay invención. En una segunda captura del mismo caso los
   candidatos inventados fueron otros ("no le gusta ser preguntado sobre su
   nombre"), así que no es un accidente puntual sino el comportamiento normal
   del extractor cuando no hay evidencia. **Un candidato no puede nacer de un
   turno sin evidencia**, y esta es la segunda justificación estructural de
   E3 junto al fontanero.
3. **Reinicio parcial** — el perro sobrevive al reinicio, pero "¿en qué
   estaba trabajando?" responde que no tiene datos: los hechos persisten y
   las tareas abiertas no. Es el checkpoint mínimo de HERA que pide E4.
4. **Eco de ejemplos de voz** — "Venga, descansa que está ganado" sale
   idéntico en dos turnos seguidos del caso de cierre, y "¡Buenas! 😄 Aquí
   andamos, dale que te pego con el motor" aparece como respuesta a "hablemos
   de los kernels".
5. **Alcance no respetado** — `resumir` y `continuar_artefacto` clasifican
   bien pero gastan cientos de tokens donde el acto pedía brevedad.
6. **Baseline de defectos menores**: 1 oferta de servicio y 6 pensamientos
   cortados en 27 turnos. No bloquean la evacuación, pero cualquier informe
   posterior que los aumente es una regresión.

### Lo que la evacuación NO puede romper

Cero turnos mudos, cero fugas del contrato interno, cero mezcla de idiomas,
acto correcto en los trece casos, perfil vacío sin heredar datos de otro
perfil, y la referencia al artefacto visual sobreviviendo al turno siguiente.

### Uso

```bash
python3 tools/oraculo.py --model <hnf> --engine <helios_chat> \
    --probe <helios_model_probe> --env HELIOS_EMBED_MMAP=1 \
    --salida informes/base.json
python3 tools/oraculo.py --diff informes/base.json informes/tras_e1.json
```

`--diff` **devuelve 1** si cambia la política (acto/registro), la estructura
(turnos que aparecen o desaparecen, casos que cambian de estado) o lo que se
escribió en memoria. Un cambio solo de texto devuelve 0 y se marca como
informativo: el texto varía por muestreo aunque no cambie nada. Verificado
inyectando las cuatro clases de cambio en un informe conocido.

**Barrera de salida de E0: cumplida.** E1 puede empezar.

---

## E1 — Resultado y cierre (2026-08-03)

**Entregables:** `docs/E1_PROTOCOLO_RUNTIME.md` (protocolo v2),
`tools/protocolo_test.py` (28 fixtures), `Hector-engine/src/inference_session.*`
(sesión reutilizable), `Hector-engine/tools/helios_runtime.cpp` (ejecutable
tipado) y `Hector-engine/tools/mini_json.hpp` + sus 21 fixtures hostiles.

`helios_chat.cpp` y `src/ck_policy.*` **no se han tocado**: la ruta nueva es
paralela, no una reescritura.

### El oráculo no era un oráculo

La comparación de E1 destapó un fallo de método más importante que cualquier
bug del transporte: **dos capturas de la MISMA base daban informes distintos**.
Dos causas, ambas nuestras:

1. **La batería corría con temperatura.** Un oráculo cuyas salidas se muestrean
   no puede decidir nada: cambiaban el texto, los candidatos extraídos y hasta
   qué ficheros de memoria se escribían. Ahora corre en **greedy por defecto**
   (`--temp`, 0 por defecto) y el `--diff` avisa si se comparan temperaturas
   distintas.
2. **Cada caso estrenaba caché de autoajuste.** Los perfiles temporales
   arrancaban sin `tune.cache`, así que el motor recronometraba los kernels y
   podía elegir geometrías con árboles de reducción distintos: bits distintos
   y, en un argmax reñido, texto distinto. La batería comparte ahora un
   sidecar entre casos y ejecuciones. Es el mismo problema que se arregló en
   el motor (`2e5927b`), reaparecido por la metodología de la prueba.

Además, la comparación de memoria pasa a ser **estructural**: qué ficheros se
escriben y cuáles quedan con contenido. Comparar el texto producía regresiones
falsas — la destilación lleva marca de tiempo y no puede coincidir jamás.

**Verificado:** dos capturas completas consecutivas, **0 diferencias** de
política, estructura y memoria. `informes/e1_base_greedy.json` queda como base
certificada (`hector@e916d9e`, greedy, sidecar compartido).

### La ruta tipada

| Prueba | Resultado |
|---|---|
| Texto multi-turno | continuidad real: dice "Byteazul" y lo recuerda al turno siguiente |
| Código con llaves y comillas | lo repite intacto (el parser viejo se rompía) |
| Cancelación de generación larga | `finish_reason: cancelled`, KV real 248→583, sesión usable después |
| Visión | círculo rojo descrito, 275 tokens de prefill, referencia viva al turno siguiente |
| JSON malformado | `error: malformed_json` con la posición del fallo |
| Trazas por `protocolo_test.py` | 3 trazas reales, **0 violaciones** |

### Lo que E1 NO puede demostrar

La batería mide comportamiento **cognitivo** —identidad, memoria, actos,
registro— que vive en `helios_chat` y que `helios_runtime` no tiene por
diseño. Una comparación conversacional entre ambas rutas es imposible hasta
que E2 y E3 muevan esa capa. Lo que E1 sí demuestra es que **la ruta paralela
no perturbó la existente** y que el transporte tipado reproduce el mecanismo:
mismo sampler, mismo KV, mismo cierre de turno.

**Barrera de salida de E1: cumplida.** E2 puede empezar.
