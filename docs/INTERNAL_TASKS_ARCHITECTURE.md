# Tareas internas y contextos aislados

Decisiones de diseño del 2026-09-21. Actualización 2026-09-22: **base modular
implementada y probada con simulador**, contratos de inferencia sin conexión al
runtime real. [Estado y límites de la entrega](MEDIA_JOBS_FOUNDATION.md).
Primer caso: [compresión secuencial de películas](HANDBRAKE_TASKS_PLAN.md).
No reactiva en bloque el antiguo plan de especialistas, ni implica multichat
visible, voz disponible o inferencia simultánea en el runtime actual.

## Principios

- HexOS posee la tarea y su memoria; el modelo propone decisiones acotadas.
- Una petición puede crear un lote de 1–5 fichas. Solo una película activa.
- Cada intervención interna parte de una plantilla y evidencia persistida,
  sin conversación acumulada, incluso entre consultas de una misma película.
- Las esperas, copias, verificaciones y recuperaciones definidas son código;
  no necesitan mantener un modelo generando o un turno de chat abierto.
- El chat del usuario conserva su contexto y tiene prioridad de inferencia.
- Primero un modelo/una GPU; selección de especialistas y segunda GPU después,
  mediante el mismo contrato de ejecución, sin reescribir el flujo de trabajo.

## Límites de los módulos

Nombres propuestos; los módulos se crean por etapa, no todos de antemano.

| Pieza | Posee | No debe conocer |
|---|---|---|
| `media_jobs/store.py` | Fichas, eventos, revisiones, claims y vencimientos SQLite | CUDA, SSH, prompts |
| `media_jobs/policy.py` | Transiciones puras, límites y esperas | E/S, procesos, SQL |
| `media_jobs/runner.py` | Una transición y reconciliación de sus efectos | Conversación del usuario |
| `media_jobs/handbrake.py` | Lanzamiento, observación y parada del proceso identificado | Priorización de chat, decisiones del LLM |
| `media_jobs/files.py` | Copia, identidad, staging y publicación verificada | Inferencia, selección de presets |
| `media_jobs/profiles.py` | Perfiles completos versionados y condiciones de uso | Comandos libres del modelo |
| `internal_tasks/requests.py` | Ficha mínima de inferencia, esquema y vigencia de respuesta | Transporte NAS |
| `internal_tasks/executor.py` | Sesión aislada, presupuesto y resultado estructurado | Autoridad para ejecutar efectos |
| `internal_tasks/resources.py` | Cola de inferencia, exclusión y prioridad por dispositivo | Semántica de HandBrake |
| `chat_backend/media_tools.py` | Validar solicitudes y entregar estados | Esperas largas y lógica de compresión |
| API/interfaz | Progreso, pausa/cancelación y notificaciones | Decidir si una salida es válida |

Las dependencias apuntan a contratos estrechos. El runner recibe repositorio,
reloj, adaptador y gestor de archivos inyectados. La política se prueba sin E/S.
El servicio de tareas llama al runner cuando vence un trabajo; no entra en el
bucle de conversación para ejecutar una operación determinista.

No añadir este servicio a `work.py`, `native.py` o `chat_backend/turn.py`.
`work.py` puede enlazar la ficha de producto mediante un identificador. El chat
solo crea/consulta/pausa/cancela; el transporte nativo solo transporta inferencia.
No construir todavía un framework universal para tareas hipotéticas.

## Persistencia y propiedad

El coordinador HexOS conserva el registro autoritativo del lote, selección,
fichas, revisiones, acciones solicitadas, eventos y `next_check_at` en SQLite.
El adaptador NAS conserva un registro durable por ejecución: identificador,
identidad de proceso, preset, salida, progreso, código de terminación y logs.
Ese registro remoto es evidencia del efecto, no una segunda cola independiente.

Si cae HexOS, la conversión remota debe poder continuar sin depender de SSH.
No se promete que las nuevas tareas o comprobaciones se ejecuten durante esa
caída. Al volver, el coordinador reconcilia los registros antes de avanzar.
Cerrar la interfaz no debe detener el servicio de tareas.

Cada acción tiene clave de idempotencia y revisión esperada. Se registra la
intención antes del efecto. Un lease local evita dos trabajadores concurrentes,
pero no evita por sí solo repetir un lanzamiento tras una caída: el adaptador
debe consultar la clave remota antes de ejecutar de nuevo. Resultado incierto
significa reconciliar, no reintentar a ciegas.

## Contrato del turno interno

Entrada construida por HexOS, no por texto libre de la conversación:

```json
{
  "schema_version": 1,
  "request_id": "identificador-unico",
  "job_id": "pelicula-1",
  "expected_revision": 7,
  "objective": "evaluar incidencia de compresion",
  "state": "compressing",
  "profile_id": "jellyfin-rf19-v1",
  "observations": [],
  "recovery_attempts": 0,
  "allowed_actions": ["wait", "request_stop", "report_incident"]
}
```

La ficha real incluye referencias de origen/destino y las últimas observaciones
con fecha y unidades, no historiales completos ni credenciales. Nombres de
archivos y logs se tratan como datos externos. El modelo devuelve request_id,
job_id, expected_revision, acción permitida, motivo breve y referencias de evidencia.
No devuelve shell, destinos nuevos ni cambios de estado ejecutables directamente.

Antes de aplicar: esquema válido, tarea vigente, revisión coincidente, evidencia
presente, acción permitida y precondiciones todavía ciertas. Si la ficha cambió
durante la inferencia, se descarta la propuesta antigua. Error de formato o
timeout deja la tarea en estado comprobable; no autoriza una acción por defecto.

Tras guardar la decisión y su resultado se libera el contexto interno. El chat
no recibe esos mensajes como instrucciones. Recibe una notificación enlazada al
job_id; los detalles quedan disponibles bajo consulta.

## Una GPU ahora; especialistas después

Primero el 12B atiende chat y solicitudes internas aisladas, con un único dueño
de la inferencia. No basta con insertar un reset en el runtime compartido: podría
borrar el contexto del chat. Antes de habilitarlo hay que verificar sesiones
independientes o guardar/reconstruir el contexto correcto bajo exclusión mutua.

La llegada del usuario impide iniciar otro turno interno. Si ya existe uno,
cancelarlo solo cuando el runtime soporte cancelación dirigida y aislamiento
comprobado; en caso contrario esperar a su fin con un presupuesto acotado.
No prometer preempción instantánea. El worker remoto sigue funcionando.

Evaluar después E4B, Qwen 8B y Qwen 2.5 Coder con las mismas fichas y decisiones
esperadas. Comparar validez de esquema, decisiones correctas, falsas terminaciones,
latencia y coste de cambio de modelo. Tener varios modelos en HNF no prueba
residencia simultánea, conmutación barata ni capacidad suficiente de VRAM.

La 4070 Ti se destinaría al texto principal y la 2080 Ti a especialistas, con
posible voz/escucha futura. Asignación, memoria y coexistencia requieren medidas.
Un límite de tokens/s es opcional y posterior; no demuestra por sí mismo ahorro
proporcional de energía. Voz/escucha, cuando existan, tendrán prioridad sobre
intervenciones internas aplazables.

## Entregas y criterios de aceptación

1. **Base simulada:** registro, política, runner y reloj falso. Una película
   recorre todos los estados. Reinicio y duplicación de eventos no duplican efectos.
2. **Una película real:** perfil fijo, staging en storage, lanzamiento identificado,
   observación, verificación y publicación sin sobrescribir originales.
3. **Lote secuencial:** 1–5 fichas, cancelación/pausa, recuperación acotada y
   clasificación de errores de archivo frente a errores compartidos.
4. **Contexto interno:** inferencia simulada y después 12B real. Una conversación
   simultánea no recibe mensajes internos, pierde contexto ni cancela otra tarea.
5. **Especialistas/recursos:** medir modelos alternativos; después asignación a
   segunda GPU mediante el mismo contrato, sin cambiar estados de compresión.

Cada entrega actualiza estado y evidencia. Pasar tests con adaptadores simulados
no acredita NAS, HandBrake, calidad del modelo ni aislamiento CUDA reales.

## Decisiones que requieren comprobación durante la implementación

- Transporte de lanzamiento durable y observación disponible en el contenedor.
- Aislamiento de sesiones y cancelación del runtime elegido.
- Umbrales de bloqueo por fase, tolerancias multimedia y presupuesto de inferencia.
- API y presentación de tareas; no inventar compatibilidad con endpoints actuales.

Estas comprobaciones no impiden comenzar por la base simulada.
