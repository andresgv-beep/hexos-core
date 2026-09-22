# Base ejecutable de tareas multimedia

Entrega 2026-09-22, rama `codex/handbrake-task-foundation`, basada en `a07a486`.
**Recorrido de archivos y encoder real probado con vídeo sintético en el NAS.
El disparador de inferencia interna y el lanzamiento desde el chat aún no están
conectados.** No incorpora la rama `frenos-y-silencios`.

## Qué funciona

- Registro SQLite independiente: lotes de 1–5 fichas, estados, revisiones,
  vencimientos, eventos e intenciones de operaciones.
- Selección de identidades existentes en `nas_files.sqlite`, limitada a
  bibliotecas configuradas por el operador como películas. No hay clasificador
  semántico automático: una biblioteca mixta necesita clasificación antes de usarla.
- Congelación del JSON de preset mediante hash; primer contrato x264/MKV.
- Una ficha activa por recurso, incluidas las operaciones de copia/publicación.
- Reloj inyectable, espera inicial de 2 min y política 30/20/1 según ETA.
- Pausar lote, reanudar, cancelar y seguir observando una conversión activa.
- Evidencia de progreso y bloqueo; parada específica, reinicio condicionado a
  exclusividad, un reintento máximo y pausa ante errores compartidos.
- Verificación antes de publicar; completar solo después de registrar la salida
  en el catálogo. Destino `.optimizada.mkv`, conservando el original.
- Intenciones durables y claves estables por acción. Leases y revisiones impiden
  aceptar respuestas de un trabajador expirado o de una ficha cancelada.
- Contrato de intervención interna con sesión fresca, evidencia, revisión y
  acciones enumeradas; exclusión de inferencia y prioridad del chat en pruebas.
- Herramientas de consulta `media.jobs` y `media.job` conectadas al catálogo y
  al despachador de Helios. No crean ni arrancan conversiones.

## Mapa del código

| Archivo | Responsabilidad |
|---|---|
| `hexos/agent/media_jobs/store.py` | SQLite, claims, control y registro de intenciones |
| `hexos/agent/media_jobs/policy.py` | Tiempos y señales de progreso, sin E/S |
| `hexos/agent/media_jobs/runner.py` | Una transición por tick; efectos inyectados |
| `hexos/agent/media_jobs/contracts.py` | Protocolos de archivos y encoder; errores tipados |
| `hexos/agent/media_jobs/files.py` | Identidades de película y resolución de destino |
| `hexos/agent/media_jobs/selection.py` | Lectura del catálogo y bibliotecas permitidas |
| `hexos/agent/media_jobs/profiles.py` | Validación mínima y hash del preset importado |
| `hexos/agent/media_jobs/service.py` | Tick sobre recursos, sin espera larga |
| `hexos/agent/media_jobs/simulation.py` | Efectos y procesos ficticios persistentes |
| `hexos/agent/media_jobs/handbrake.py` | Adaptador de producción explícitamente no configurado |
| `hexos/agent/media_jobs/nas_encoder.py` | Transporte SSH y adaptador real opt-in |
| `hexos/agent/media_jobs/remote/encoder_control.py` | Recibos, exclusión de lanzamiento y reconciliación remota |
| `hexos/agent/media_jobs/remote/encoder_worker.py` | Proceso independiente, JSON de progreso y parada propia |
| `hexos/agent/media_jobs/nas_files_adapter.py` | Configuración de archivos y actualización puntual del catálogo |
| `hexos/agent/media_jobs/nas_files_transport.py` | Despliegue versionado y llamadas SSH cortas |
| `hexos/agent/media_jobs/remote/file_control.py` | Intenciones, exclusión y cancelación de workers de archivos |
| `hexos/agent/media_jobs/remote/file_worker.py` | Ejecución de una acción, progreso y recibo final |
| `hexos/agent/media_jobs/remote/file_common.py` | Copia, hash, identidad y apertura sin seguir enlaces |
| `hexos/agent/media_jobs/remote/file_operations.py` | Copiar, verificar, publicar y observar el destino |
| `hexos/agent/media_jobs/remote/file_media.py` | FFprobe, reglas de pistas/duración y decodificación completa |
| `hexos/agent/internal_tasks/requests.py` | Construcción y validación de decisiones |
| `hexos/agent/internal_tasks/resources.py` | Slot de inferencia compartido con prioridad del chat |
| `hexos/agent/internal_tasks/executor.py` | Sesión aislada inyectada por intervención |
| `hexos/agent/chat_backend/media_tools.py` | Consulta acotada, sin ejecución ni espera |

## Probar sin NAS ni GPU

Desde la raíz del checkout, usando un directorio de demo separado:

```bash
python3 -m hexos.agent.media_jobs demo --workspace /tmp/helios-media-demo --count 5
python3 -m hexos.agent.media_jobs list --workspace /tmp/helios-media-demo
```

La demo usa nombres ficticios, un **preset de fixture** y un reloj virtual. No
importa el preset del usuario, no abre vídeos y no usa SSH. Imprime explícitamente
`simulation`. El registro queda en `media_jobs.sqlite` y el doble remoto durable
en `media_simulation.sqlite`. Una simulación no acredita calidad ni rendimiento.

Controles locales sobre un lote existente:

```bash
python3 -m hexos.agent.media_jobs pause --workspace /tmp/helios-media-demo --batch-id ID
python3 -m hexos.agent.media_jobs resume --workspace /tmp/helios-media-demo --batch-id ID
python3 -m hexos.agent.media_jobs cancel --workspace /tmp/helios-media-demo --batch-id ID
```

Los controles guardan intención; una cancelación activa necesita un siguiente
`tick` para reconciliar y comprobar parada. No hay daemon instalado por esta entrega.

## Contratos que debe cumplir el adaptador real

La cola local por sí sola no da exactamente una ejecución remota. Cada método
con efectos recibe una clave; el adaptador debe almacenarla en el NAS y consultar
su recibo antes de repetir. Una pérdida de conexión conserva estado y clave.
No basta con comprobar un PID reutilizable: verificar identidad del proceso.

Las operaciones retornan antes del lease (30 s por defecto). Copias,
verificaciones o publicaciones largas deben lanzarse de forma durable y devolver
`pending: true`; consultas posteriores continúan con la misma clave. Expirar
el lease no cancela el proceso remoto ni permite duplicarlo. El host del servicio
debe capturar conflictos de revisión y volver a consultar, sin aplicar respuestas viejas.

`stop` debe resolver también un arranque cuya respuesta no llegó a guardarse.
`restart` debe revalidar exclusividad en el momento de actuar, aunque un `stop`
anterior indicara que no había trabajos ajenos. La salida de un intento fallido
se conserva separada. No usar watch ni su preset automático distinto.

`verify` debe comprobar datos reales de origen y salida. El `valid` del simulador
solo permite probar el circuito. `publish` debe prohibir sobrescritura, comprobar
una copia entre discos y reconciliar una publicación anterior. `index` debe
actualizar el catálogo real antes de acreditar finalización.

## Contexto e inferencia: frontera actual

Decisión para las pruebas: `HANDBRAKE_TRIAL_BINDING` en
`internal_tasks/binding.py` fija dominio `text`, bloque HNF `0x0` y política
`reuse_resident`. El ejecutor pasa ese enlace a la fábrica de sesiones; no lo
elige el LLM ni procede del contenido de la ficha. Se reutilizarán los pesos
del principal, con contexto interno fresco y exclusión de inferencia.

Después de validar el recorrido, el adaptador podrá seleccionar `cortex` (`0x7`)
o `code` (`0x8`). Dos políticas posibles, todavía no conectadas: residencia en
paralelo si hay recursos, o descarga/carga serializada en la misma GPU. En este
último caso, al volver al chat debe restaurar/reconstruir su contexto con sus
pesos, tokenizer y execution hints correctos. No se cambia el bloque dentro del
archivo HNF: se cambia el dominio que se selecciona para ejecutar.

El ejecutor recibe una fábrica de sesiones frescas. No llama a reset sobre el
runtime del usuario ni comparte sus mensajes. La fábrica real aún no existe:
antes de conectarla debe demostrar aislamiento, liberación y cumplimiento de
presupuestos (256 tokens/30 s en el contrato inicial, ajustables después de medir).
El slot no interrumpe una inferencia ya iniciada. Las decisiones devueltas son
propuestas; aún no hay un despachador de efectos autorizado para aplicarlas.
Las solicitudes internas no disponen todavía de una cola persistente propia.

## Validación de esta entrega

30 pruebas nuevas en `tools/media_jobs_test.py`, `tools/media_selection_test.py`
y `tools/internal_tasks_test.py`; batería ampliada de **332 pruebas** correcta.
Demo de cinco películas: 45 transiciones, las cinco `completed` en simulación.

Casos: caída tras arranque/publicación, lease expirado, dos conexiones en
competencia, cancelación durante arranque, huecos en evidencia, salida inválida,
reintentos limitados, trabajo ajeno impidiendo reinicio, conflicto de destinos,
selección ajena al catálogo y propuesta interna obsoleta.

El encoder real se documenta en
[`HANDBRAKE_ENCODER_VALIDATION.md`](HANDBRAKE_ENCODER_VALIDATION.md). El recorrido
posterior completo, con 313 pruebas locales y prueba sintética NAS, está en
[`HANDBRAKE_FILES_VALIDATION.md`](HANDBRAKE_FILES_VALIDATION.md). No acredita aún
copias de decenas de GB, despertar del e4b, aislamiento CUDA, cambio de modelo,
calidad visual ni compatibilidad de reproducción en dispositivos del usuario.

## Siguiente entrega concreta

Conectar una cola persistente de despertares: incidencia o salida verificada abre
un turno interno aislado. Añadir espera de decisión antes de publicar, validación
de la propuesta y herramientas acotadas de continuación. Probar e4b en `text/0x0`
con fichas nuevas por turno, sin mezclar el chat. El recorrido de backend actual
publica automáticamente dentro de su arnés de pruebas: todavía no es ese circuito
dirigido por el modelo. Instalar después el servicio de vencimientos y herramientas
de creación/control de lotes. El reparto multi-GPU sigue siendo posterior.
