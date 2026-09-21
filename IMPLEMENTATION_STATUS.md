# Estado de implementación de Hexos

**Revisión: 2026-09-19; código `76a75c0`, Héctor `b822e1b`.** Contrastado con las
rutas Python/React actuales y la evidencia local del hito. Sustituye el informe
de enero que decía «motor inexistente»; aquel corte se conserva en
[archivo histórico](docs/historico/IMPLEMENTATION_STATUS_2026-01-18.md).

## Qué está conectado

| Capacidad | Estado real | Fuente |
|---|---|---|
| Inferencia real | Héctor CUDA por proceso NDJSON; plantilla nativa Gemma o ruta JSON distinta | [bootstrap](hexos/agent/chat_backend/bootstrap.py), [adaptador](hexos/agent/native.py) |
| Un chat persistente | Historial, herramientas y trabajo SQLite por workspace | [work](hexos/agent/work.py), [contexto](hexos/agent/chat_backend/context.py) |
| Texto progresivo y detener | Conectados a React por estado cada 450 ms y POST cancel dirigido | [integración](docs/PROGRESSIVE_NATIVE_RUNTIME.md) |
| Herramientas | Catálogo validado, despacho, límites, traza y evaluación de cierre | [catálogo](hexos/agent/catalog.py), [ciclo](hexos/agent/chat_backend/turn.py) |
| Verificación | Comprobación de informes/perfil/acciones declaradas y efectos desconocidos persistidos; no certifica todo objetivo arbitrario | [verification.py](hexos/agent/chat_backend/verification.py) |
| Notas/documentos/informes | Persistencia, recuperación, revisiones de notas y paneles de interfaz | [notes.py](hexos/agent/notes.py), [TRABAJOS](docs/TRABAJOS.md) |
| Dispositivos, NAS y SSH | Lecturas y acciones acotadas del catálogo con acceso configurado; no shell arbitraria del modelo | [inventario](docs/INVENTARIO_DISPOSITIVOS.md), [diagnóstico](docs/SSH_SYNOLOGY_DIAGNOSTICO.md) |
| Contenido NAS (2026-09-20) | Memoria local de directorios, navegación y buscador recursivo por extensiones, tamaños opcionales y páginas acotadas. Lecturas reales en ambos Synology; cobertura parcial donde faltan permisos. HandBrake no conectado | [arquitectura y límites](docs/NAS_CONTENIDO.md) |
| Base de archivos (2026-09-20) | Servicio con lector y repositorio inyectados; SSH, SQLite, validación y presentación separados. Compatibilidad con herramientas y catálogos existentes. Sincronización automática, lectura documental y pines pendientes | [contratos y etapas](docs/FILE_CATALOG_ARCHITECTURE.md) |
| Carpetas y recursos compartidos (2026-09-20) | Búsqueda actual de directorios incluidos vacíos; listado SMB configurado en Synology con acceso SSH separado; protección de nombres literales explícitos ante sustituciones del historial | [contrato NAS](docs/NAS_CONTENIDO.md) |
| Continuidad de listados e historial (2026-09-20) | «Muéstrame todas» retoma consultas recientes de directorios con páginas locales; historial visual paginado más allá de 100 mensajes. Reproducción real: 39 carpetas de Compartido y 1.726 mensajes recuperados | [evidencia y límites](docs/NAS_CONTENIDO.md) |
| Web pública | Búsqueda y lectura con límites de red/contenido | [WEB_PUBLICA](docs/WEB_PUBLICA.md) |
| Perfil HERA | Lectura, extracción de afirmaciones, guardado/corrección y relectura si se configura HERA | [memoria](hexos/agent/chat_backend/memory.py) |
| Contexto largo | Reutilización nativa, umbral por ocupación KV, archivo y traspaso literal al reconstruir | [context.py](hexos/agent/chat_backend/context.py) |
| Visión | Imagen base64 HTTP → Pillow/RGB8 → NDJSON; E4B real comprobado. HNF textual rechaza imágenes | [transporte](docs/MULTIMODAL_TRANSPORT.md) |
| Interfaz React | Chat conectado, telemetría, adjuntos, notas, ventana de código y preview HTML | [arquitectura UI](interfaz/docs/ARQUITECTURA.md) |
| Voz | Sin cadena de reconocimiento/síntesis conectada. La esfera no demuestra audio real | [arquitectura UI](interfaz/docs/ARQUITECTURA.md) |

## Memoria y continuidad: alcance concreto

HERA requiere `--hera /ruta/hera-cli --memory-home /ruta/perfil` juntos en
`python3 -m hexos.agent.chat`, además de workspace/runtime/model/template.
Sin ellos, el historial y las notas del workspace siguen funcionando, pero no
se activa el perfil HERA. `HELIOS_HOME` por sí solo no configura ese conector.
La extracción usa una sesión auxiliar del mismo modelo; propone hechos que el
agente contrasta con citas del usuario y relee tras guardarlos. No es memoria
infalible ni promoción libre de cualquier afirmación del modelo.

El contexto no es infinito. El agente conserva archivo, prepara un traspaso
literal y reconstruye cuando alcanza sus umbrales; combina presupuestos de
caracteres con la posición KV real. No existe aún un presupuesto exacto único
por tokens para todo prompt, herramienta y respuesta. La ruta nativa devuelve
`work: null`: no tiene paridad completa con la clasificación de fichas de la
ruta JSON. La autorización independiente y general de escrituras sigue siendo
un límite distinto de validar argumentos o comprobar un resultado.

## Fronteras que no deben mezclarse

- Agente Python: `/api/telemetry`, `/api/notes`, `/api/core`, `/api/cancel`,
  historial y respuestas finales JSON. Progreso provisional en `/api/status`.
- Servidor C: conserva SSE, multichat y endpoint RGB8 propios. Sus contratos no
  describen automáticamente el servidor Python.
- `helios_runtime`: stdin/stdout NDJSON; no es un servidor HTTP ni ejecuta herramientas.
- `helios_formatted`: compatibilidad antigua; acumula texto y no acepta cancelación.
- `cognitive_stub`: simulador específico; no describe al agente en uso.

## Pendientes vigentes

1. Reducir y presupuestar mejor el prompt/contexto; medir sesiones largas y calidad
   de recuperación, sin confundir archivo persistente con atención infinita.
2. Mejorar fiabilidad de planificación, autorización y verificación de tareas
   compuestas. Las regresiones de herramientas no garantizan autonomía general.
3. Completar visión del 12B encoder-free en Héctor/conversor; E4B visual no la certifica.
4. Integrar voz solo cuando haya un recorrido real de entrada/salida.
5. Unificar políticas entre transportes si se necesita paridad: la selección
   automática de mmap del servidor C no se aplica igual en NativeTransport.
6. La cancelación no mata una herramienta externa ya en ejecución: espera su
   resultado y evita iniciar nuevas tras comprobar la señal.

Multichat, modelos especialistas y reflexión en segundo plano pertenecen a
rutas históricas o alcance aparcado, no a una obligación pendiente de este producto.

## Evidencia y mantenimiento

### Punto de partida para comparar con el 12B — 2026-09-21

Se conserva la implementación actual con catálogo NAS modular, continuaciones de
listados, historial visual paginado y primera vista móvil. Validación del punto
de partida: 241 pruebas de backend, 78 de interfaz y comprobación TypeScript.
Las pruebas conversacionales NAS de esta entrega se hicieron con el E4B; no
certifican que ese modelo pueda coordinar de forma fiable todos los casos.

Pendiente: repetir en la otra máquina con el 12B las mismas conversaciones y
herramientas, registrando modelo, contexto, llamadas, nombres y filtros, cobertura,
latencia y necesidad de aclaraciones. Separar los resultados resueltos por código
sin inferencia de los que requieren interpretación del modelo. Este punto de
partida no cambia el modelo de arranque ni incluye pesos, credenciales o bases
locales de conversación.

Última integración: 72 pruebas de interfaz, tipos, build/render, contratos Python,
12B real con cancelación/continuación y herramienta, E4B real con imagen y sesión
auxiliar. Véanse [informe](docs/PROGRESSIVE_NATIVE_RUNTIME.md) y
[logs](informes/progressive-runtime-2026-09-19/). No se han repetido inferencias
para esta revisión exclusivamente documental.

Al cambiar una capacidad, actualizar esta tabla, el contrato concreto y las
instrucciones de arranque. Mantener los informes fechados como evidencia, con
una nota cuando sus pendientes se hayan resuelto. [Índice completo](docs/INDICE.md).
