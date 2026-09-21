# Agentes especialistas locales — propuesta posterior a E6

> Aparcado desde 2026-09-12. La dirección vigente es el
> [agente doméstico de un solo modelo y un chat](AGENTE_DOMESTICO_PLAN.md).
> Se conserva este documento como antecedente, no como trabajo pendiente.

> Actualización 2026-09-21: el nuevo alcance limitado se documenta en
> [Tareas internas y contextos aislados](INTERNAL_TASKS_ARCHITECTURE.md).
> Empieza por supervisión de películas; no reactiva las propuestas de este documento.

## Propósito y alcance

Helios mantiene una sola identidad visible, aunque varios modelos o sesiones
especializadas colaboren internamente. El primer experimento será un agente de
código; Cortex podrá decidir cuándo proponerle una tarea, pero nunca responderá
al usuario ni ejecutará cambios por sí mismo.

El alcance sigue siendo una instalación local y un propietario. No implica
multiusuario ni ejecución CUDA simultánea. En una sola GPU las sesiones están
vivas lógicamente, pero generan en secuencia.

## Responsabilidades

| Pieza | Responsabilidad |
|---|---|
| Modelo de texto | conversación, aclaraciones y voz final de Helios |
| CK | acto, alcance, permisos y decisión determinista de delegar |
| Cortex pequeño | proponer una transición cerrada; CK conserva el fallback |
| Coder | producir código, artefactos y resultados verificables |
| HexOS | secuencia, sesiones, herramientas, GPU y eventos para la UI |
| HERA | memoria y autoridad; el coder no escribe recuerdos |

Cortex solo puede proponer valores cerrados, inicialmente:

```text
continuar_tema | cambiar_tema | retomar_tema | corregir
referir_artefacto | cerrar | delegar_codigo
```

## Contratos tipados

El modelo conversacional no entrega prosa ambigua al coder. HexOS construye un
`CodeTask` con el objetivo y los límites que CK haya determinado:

```text
CodeTask
  request_id
  chat_id
  objective
  relevant_context_refs[]
  constraints[]
  expected_artifacts[]
  permissions
  budget
```

El coder devuelve hechos observables, no razonamiento interno:

```text
CodeResult
  status: success | partial | failed | cancelled
  artifacts[]
  changed_files[]
  checks[]
  warnings[]
  summary
```

El modelo de texto solo puede afirmar que algo fue creado o probado a partir de
este resultado. No recibe ni muestra cadena de pensamiento del coder.

## Secuencia con una sola GPU

```text
persona pide un script o una UI
  -> CK decide responder, aclarar o delegar
  -> UI muestra un estado mecánico: preparando / generando / comprobando
  -> sesión de texto queda pausada, conservando KV y sampler
  -> sesión coder genera el artefacto y ejecuta las comprobaciones permitidas
  -> HexOS recibe CodeResult
  -> sesión coder queda pausada
  -> sesión de texto recibe CodeResult como un nuevo mensaje estructurado
  -> Helios redacta una única respuesta visible
  -> UI coloca debajo el código, diff, archivos o vista previa
```

No se emite una explicación final antes de tener el resultado: evitaría que el
modelo conversacional prometiera archivos o pruebas que todavía no existen.
Si falta una decisión material, el modelo de texto pregunta antes y el coder no
arranca.

La prioridad de ejecución es:

```text
chat visible > coder solicitado por la persona > reflexión de fondo
```

Si texto y coder usan los mismos pesos, son sesiones aisladas de un mismo
`Model`. Si necesitan modelos distintos, primero se mide si ambos caben y el
coste de conmutación. No se diseñará intercambio de residencia ni duplicación
de pesos hasta tener esa medida.

## Presentación en la UI

- Un archivo pequeño: explicación breve y bloque de código debajo.
- Varios archivos: artefacto con árbol, diff y descarga.
- UI web: explicación, vista previa renderizada y archivos.
- Cambio sobre un proyecto: resumen, archivos modificados y comprobaciones.

Para la persona todo pertenece al mismo turno de Helios. Los estados de trabajo
son telemetría mecánica; no se muestra «pensamiento» inventado.

## Barreras antes de producción

1. Cortex mejora una batería de continuidad y delegación frente al fallback
   determinista; si no mejora, no entra.
2. Cambiar texto -> coder -> texto no altera el KV de ninguna otra sesión.
3. Un `CodeResult` fallido o cancelado nunca se presenta como éxito.
4. El coder no adquiere autoridad de memoria ni amplía permisos del `CodeTask`.
5. La UI recibe una respuesta coherente y artefactos ligados al mismo turno.
6. Se mide VRAM, tiempo de conmutación y latencia total con una sola GPU.
7. El primer banco incluye scripts de un archivo, una UI pequeña, una tarea que
   necesita aclaración, cancelación y un fallo de pruebas.

Esta propuesta no forma parte de la evacuación E0-E6. Se conserva aquí para no
perderla y solo se implementa cuando la ruta cognitiva nueva sea la estable.
