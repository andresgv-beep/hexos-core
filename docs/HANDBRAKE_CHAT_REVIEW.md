# Chat, servicio y revisión interna

## E4B en NAS real tras integración — 23 septiembre 2026

Prueba de conversación `tools.media_prepare_live`, modelo e4b en text/0x0,
contexto 16384: consulta perfiles y busca en la biblioteca correcta, pero **no
supera la preparación**. Interpreta GB como GiB, confunde los 16 resultados de
página con el total y mezcla paths con count/filtros. Las recuperaciones no han
conseguido completar un plan. No hubo media.start ni conversión de películas.
Evidencias: `/tmp/hexos-e4b-real-20260923-{a,b,c}`; conversación y work.sqlite.

Se corrigen dos obstáculos acotados: hasta tres recuperaciones de errores de
lectura distintos por turno, sin repetir el mismo error, y ejemplo de root como
cadena en el error de cobertura. No se deducen acciones de promesas de Text.
La prueba c sigue fallando; estas correcciones no acreditan autonomía.

Recorrido interno separado con vídeo sintético: completed,
`e5cde301b2f04a1ebde506ccb60cb794`; e4b decide publish, HexOS verifica, publica e
indexa. Original intacto mediante comprobación independiente. Evidencias en
`/tmp/hexos-e4b-cycle-20260923`. El arnés adelanta el reloj de las consultas y no
valida horas de ejecución, ahorro de espacio ni selección desde conversación.

459 pruebas automatizadas correctas. UI y backend locales se ejecutan desde este
checkout, con workspace separado y modelo e4b; no activan un especialista Cortex
ni conectan un perfil HERA automáticamente. La máquina del 12b no se ha tocado.

## Integración y corrección de memoria — 23 septiembre 2026

Integrados por avance directo 22ec1ae, 53576af, e26050e y 75a736a sobre la rama
HandBrake. La retirada de reescrituras descrita a continuación es el comportamiento
vigente; el apartado histórico de reintento/corrección de frases ya no se aplica.

Se valida cada candidato de memoria contra el mensaje original registrado antes
de agrupar claves. Un candidato inventado o demasiado largo ya no descarta otro
válido para la misma clave. La validación es compartida con el guardado explícito;
HERA conserva su comprobación final. Las pruebas incluyen candidatos inválidos
junto a uno respaldado y dos fragmentos respaldados del mismo nombre.

Actualizadas las cinco expectativas antiguas del bucle de chat: una afirmación o
promesa textual no genera llamadas ni fuerza otro turno. El diagnóstico de falta
de evidencia permanece. No se reinstalan las heurísticas retiradas.

Validación local: 456 pruebas correctas de memoria, chat, contratos, NAS, tareas,
encoder y sesiones internas. No es una nueva prueba de GPU o conversión real.
La protección de filtros sigue detectando omisiones, no cambios explícitos del
modelo; cerrar ese contrato requiere identificar la selección solicitada.

## Retirada de reescrituras por frases — 22 septiembre 2026

Las generaciones 292–293 y 296–297 demostraron falsos positivos: «sacar el
máximo provecho» se interpretó como note.show y una cita hipotética de Jarvis
como una escritura real. Se retira del cierre la recuperación por anuncios,
promesas y afirmaciones detectadas mediante patrones. También se retiran la
sustitución por un borrador anterior al mencionar HexOS, los añadidos por
negaciones y la corrección textual multimedia incorporada anteriormente.
Los helpers históricos permanecen para compatibilidad/diagnóstico, pero no
deciden regenerar o reescribir la respuesta por estas frases.

Se conservan validación estructurada de llamadas, errores reales de herramientas,
trazas, evidencia documental y persistencia. Esto no garantiza que el modelo
no haga afirmaciones falsas: el texto no acredita una operación; la traza sí.
No se añaden excepciones específicas para las metáforas ni para la persona.

## Corrección tras conectar HERA — 22 septiembre 2026

Las trazas reales mostraron que media.job devolvía `error: null` y el ejecutor
y la recuperación lo interpretaban como fallo por presencia del campo. Ahora
solo un error no vacío activa esa ruta; además la consulta separa `task_error`
(incidencia de la tarea) del error de la herramienta. Para tareas live running,
media.job observa el mismo run_id en el encoder, sin mutar la tarea ni ejecutar
el supervisor. Declara observation_source y antigüedad; ante fallo de lectura
conserva la observación guardada con advertencia. Verificar/publicar sigue
correspondiendo al trabajador y al revisor interno.

«He consultado el estado de los trabajos» ya no exige network.local: el anuncio
de esa herramienta requiere objeto de red. La extracción de memoria agrupa las
claves antes de guardar, descarta fragmentos sin referente y no elige por orden
entre valores incompatibles. Se incluye el ejemplo real de no usar el nombre
en cada turno sin interpretarlo como no usarlo nunca.

194 pruebas automatizadas correctas. Se restauró mediante HERA la preferencia
completa desde el mensaje original, manteniendo su historial. Helios reiniciado
con HERA conectado; la interpretación conversacional del 12B queda pendiente
de prueba por el usuario. No se enviaron mensajes de prueba a su conversación.

## Ajuste de Text pendiente de reinicio — 22 septiembre 2026

La sesión real mostró dos fallos adicionales: un saludo retomaba búsquedas
antiguas y «Pongo en cola la conversión de La Monja… Te avisaré…» cerraba sin
llamar a media.start. El aviso de recuperación agravaba el primero al ordenar
ejecutar la promesa del propio modelo, aunque la persona solo hubiera saludado.

Se aclara la política del saludo incluso con encargos pendientes, sin introducir
un clasificador de permisos por palabras. La recuperación remite a la petición
de la persona: el borrador no autoriza acciones. Una aceptación mantiene su
significado de continuación del plan propuesto.

Text recibe instrucciones de llamar a media.start al aceptar el plan y confirmar
solo su resultado. Las formas de primera persona comprobadas («pongo en cola»,
«he puesto en cola», «encolo», etc.) y promesas de avisos multimedia provocan un
reintento acotado; si persisten, el cierre las corrige sin ejecutar herramientas.
El registro debe contener media.start exitoso con batch_id y estado queued o
already_queued; preparar, una escritura ajena o un start fallido no sirven.
La corrección se aplica también tras recuperar un borrador anterior, se archiva
y reinicia el contexto del chat para no conservar una respuesta distinta en KV.
Estas reglas cubren formas concretas, no garantizan reconocer toda paráfrasis.

Validación offline: 152 pruebas correctas de Text, conversación, trazas,
contratos, multimedia y aislamiento de sesiones internas. Incluyen la respuesta
real fallida, reintento agotado, persistencia, saludo con propuesta pendiente y
aceptación con llamada start simulada. No prueban que el 12B haya cambiado su
conducta: esa comprobación real queda pendiente tras cargar los cambios.

Cambios solo en disco: no se reinició Helios, no se enviaron mensajes a la sesión
real ni se modificó el trabajador, el revisor interno o la conversión en curso.
No desplegar/reiniciar mientras pueda interferir con ese trabajo.

## Corrección y prueba 12B — 22 septiembre 2026

La prueba real posterior detectó un contrato inconsistente: `nas.find.query=""`
era rechazado por el catálogo aunque el lector admite no filtrar por nombre.
Ahora se acepta vacío solo en `query` de nas.find/nas.search/media.prepare;
identificadores y rutas conservan la restricción de cadena no vacía. El esquema
nativo expresa esa restricción y el reintento recibe el error y los argumentos
concretos, en vez de un aviso genérico.

El contexto incluye las bibliotecas configuradas como datos del operador, sin
presets completos ni autorización nueva. Las instrucciones distinguen filtros
de nombres de archivo, raíces observadas y consulta de perfiles con media.options.
Si media.prepare por count omite filtros presentes en la última vista entregada
de ese scan_id, se rechaza antes de seleccionar y se indican los campos que
faltan. No se aplican silenciosamente: el modelo debe reenviarlos. Puede cambiar
un filtro explícitamente; paths sigue siendo la alternativa de selección exacta.
Si falta root y el escaneo no cubre todas las bibliotecas, el error muestra las
bibliotecas cubiertas para corregir la llamada sin ampliar el encargo.

Validación: 203 pruebas automatizadas, más 12B HQ42/HQ52 real con contexto 16384
y NAS real, usando la configuración RF19/MKV del usuario en un workspace aislado.
En la ejecución final consultó media.options, buscó MKV entre 8 y 50 GB decimales
en `/volume1/multimedia 1/Multimedia/peliculas` (33 coincidencias, página inicial
de 16) y preparó los cinco mayores del catálogo completo filtrado. Tamaños GB:
39.287, 34.054, 27.183, 27.168, 26.346. La comprobación compara rutas y bytes por
SQL independiente, no por el texto del modelo.

Hubo dos llamadas de preparación rechazadas de forma recuperable: primero
faltaban filtros y después root; el modelo corrigió ambas y terminó con el plan
correcto. Cero llamadas media.start y cero lotes encolados. El arnés bloquea start
y no inicia worker: no hubo copias, conversiones ni publicaciones. El historial
habitual no se utilizó para introducir mensajes de prueba.

Evidencia local: `/tmp/hexos-12b-fix-real-20260922-d/{conversation.json,verdict.json,work.sqlite}`.
Reproducible con `python3 -m tools.media_prepare_live --help`.
Esto valida este recorrido con dos peticiones concretas; no certifica todas las
paráfrasis ni la conversión real, y no incorpora la rama frenos-y-silencios.

2026-09-22. Rama `codex/handbrake-task-foundation`.

## Recorrido desde Helios

1. `media.options`: bibliotecas de películas, perfiles y disponibilidad del servicio.
2. `nas.find`: búsqueda real recursiva, incluyendo subcarpetas, con un `scan_id`.
3. `media.prepare`: `paths` exactos para una película/selección concreta, o `count`
   entre 1 y 5 más `root`/`query` opcionales para un top por tamaño del catálogo.
   Ordena el backend, antes de limitar a cinco. El top requiere cobertura completa
   de las bibliotecas seleccionadas; una búsqueda parcial permite selección explícita,
   no afirmar que son las mayores de todo el alcance. Devuelve cobertura y fecha.
4. `media.start`: encola el `plan_id`. La misma clave no crea otro lote. Requiere
   configuración vigente y heartbeat reciente del servicio/revisor.
5. `media.jobs`/`media.job`: consulta sin despertar a cortex. `media.control` permite
   pausa, reanudación y cancelación del lote pedido por la persona.

Preparar no convierte; encolar no acredita éxito. Cada ficha se completa solo tras
publicación y catálogo. Los destinos son derivados del origen y los presets están
configurados por el operador; las herramientas no aceptan comandos libres.
El plan caduca a los 30 minutos y fija la configuración; los archivos se revalidan
antes de copiar y publicar. En producción se exige reducción de tamaño.

## Servicio y turnos

`chat_backend/bootstrap.py` inicia `MediaWorker` junto al servidor. Sin
`media_jobs.json` habilitado no opera. Las conexiones SQLite son propias de cada
hilo; el chat no espera copias, conversiones ni verificaciones. Los procesos
remotos ya iniciados pueden continuar si HexOS se cierra, pero las próximas
transiciones y revisiones requieren que el proceso HexOS vuelva a funcionar.
No es un servicio systemd independiente.

Las fichas lanzadas desde chat llevan `require_review=true`. Una salida verificada
queda en `awaiting_review` y bloquea el avance del siguiente archivo. La transición
y el despertar se guardan en la misma transacción SQLite. Un fallo o estancamiento
también genera una revisión; las consultas de progreso normales no usan el LLM.

El modelo puede pedir `publish`, `request_stop`, `wait` o `report_incident`, según
las acciones de esa ficha. No proporciona rutas ni parámetros nuevos. El backend
valida request_id, job_id, revisión y evidencia contra la petición persistida.
Una cancelación invalida una decisión que llegase tarde. Publicación y recuperación
siguen ejecutándose mediante los adaptadores verificados, no mediante shell del LLM.
Tras tres decisiones fallidas o esperas sin resolver queda `attention`, visible
en las consultas; no hay un bucle ilimitado de inferencia.

Los módulos de esta etapa separan configuración, planificación, servicio,
despertares y transporte de sesión. No se ha añadido lógica de NAS al runtime
ni esperas de conversión al bucle de conversación.

## Qué modelo se usa

Binding actual: **text / 0x0 / reuse_resident**. Se reutilizan los pesos que tenga
cargados esa instalación. En una instalación con 12b, el revisor también será
ese 12b; no carga mágicamente el e4b del otro equipo. La selección futura de cortex
o de otro especialista sigue pendiente, igual que el reparto entre GPUs.

Cada revisión abre una sesión NDJSON `media-<uuid>`, con 2048 tokens de contexto,
256 de salida y presupuesto de 30 s. Después la cierra. No utiliza `aux` ni borra
la sesión `0`. La cancelación/cierre tienen una gracia acotada adicional; si no
se confirma el cierre del protocolo, se bloquea su reutilización hasta reiniciar
el runtime, en lugar de mezclar respuestas.

`ModelLifecycle` arbitra el único motor: el chat pendiente tiene prioridad y una
revisión se aplaza cuando hay conversación. Si llega un mensaje durante una
revisión ya iniciada, espera ese turno corto; no recibe «ya hay un turno en curso»
por culpa del worker. No hay preempción de un kernel CUDA ni inferencia paralela.

## Evidencia real

HNF probado: `helios-gemma4-e4b_qwen3-8b_qwen25-coder-7b.hnf`, dominio text Gemma4
E4B. Motor local `helios_runtime`, GPU RTX 5070 Laptop de 8 GiB, contexto principal
de prueba 4096. No se modificó ni recompiló el motor.

- Salida técnicamente verificada → `publish`.
- Conversión activa y avanzando → `wait`.
- Salida con duración incorrecta → `report_incident`.

Acertó los tres casos, con una ficha nueva por turno. En la primera tanda tardó
aproximadamente 1,75–2,11 s por decisión, sin contar la carga inicial del modelo.
Una segunda prueba con sesión de conversación inicializada comprobó que su
`model_state` permaneció idéntico después de cada revisión.

Recorrido NAS con decisión real: ficha `a399ce2cd2c04487baa1f309b0593e14`, vídeo
sintético en subcarpeta. Se detuvo en `awaiting_review`; el e4b devolvió `publish`
para la revisión 7. El backend aceptó la decisión y completó publicación/catálogo,
con original intacto. Las consultas estaban aceleradas por el arnés; esto no
acredita horas de ejecución ni una conversación natural del 12b.

339 pruebas de regresión correctas: herramientas a través del Agent, top global
y archivo concreto, falta de servicio, configuración cambiada, publicación
condicionada a revisión, decisión duplicada/obsoleta, cancelación, prioridades de
inferencia, cierre de sesiones y regresiones de NAS/chat.

Reproducibles:

```bash
python3 -m tools.media_internal_live --runtime /ruta/helios_runtime \
  --model /ruta/modelo.hnf --evidence-dir /tmp/review-test-nuevo

# El recorrido NAS de tools.media_pipeline_smoke admite además:
# --review-model /ruta/modelo.hnf --runtime /ruta/helios_runtime
```

## Activación en la instalación del usuario

Aplicar esta rama en la máquina del modelo. Este cambio es Python: **no exige
recompilar Héctor** si ya se utiliza el runtime NDJSON con sesiones probado.
Reiniciar Helios para cargar el catálogo y arrancar el worker.

La configuración preparada localmente está en `runtime/workspace/media_jobs.json`
del checkout HandBrake (ignorada por Git). Incluye el preset completo RF 19 y las
dos rutas de películas comprobadas en el NAS. Se copia al **workspace de la
instalación destino**, donde ya están su catálogo e inventario/credenciales.
No contiene contraseñas. Revisar el nombre `synology 1` si allí tiene otro alias.
No se ha activado ni modificado la configuración de la máquina remota del 12b.

Para generarla desde una exportación `{preset: hoja, version: Version*}`:

```bash
python3 -m hexos.agent.media_jobs.setup \
  --workspace /ruta/workspace --device 'synology 1' \
  --preset-json /ruta/preset-exportado.json \
  --storage /volume1/docker/handbrake/storage \
  --output /volume1/docker/handbrake/output \
  --control /volume1/docker/handbrake/config/.hexos-media \
  --ffmpeg /var/packages/ffmpeg7/target/bin/ffmpeg \
  --ffprobe /var/packages/ffmpeg7/target/bin/ffprobe \
  --library '/volume1/multimedia 1/Multimedia/peliculas' \
  --library '/volume4/multimedia 3/multimedia/peliculas'
```

`media.options` debe indicar servicio disponible antes de lanzar una película.
Primera prueba sugerida: pedir un título concreto y el perfil configurado. La
conversación natural con el 12b queda por verificar en ese equipo. No se han
convertido películas reales, únicamente muestras sintéticas.

Pendientes: panel y avisos proactivos en la interfaz, limpieza de temporales,
reconciliación asistida de workers inciertos, más perfiles/pistas/subtítulos y
selección de especialistas. El reinicio automático del contenedor sigue deshabilitado
hasta demostrar exclusividad; una decisión del modelo no elimina esa condición.


## Prueba de conversación por rango (22 septiembre 2026)

`tools.media_conversation_live` ejecuta el modelo real con Agent y el catálogo
completos en un workspace aislado. Solo el NAS se sustituye por metadatos
sintéticos; la cola es SQLite real, sin worker de conversión. No inicia SSH ni
HandBrake. Los tamaños son 3, 8, 12, 18, 25, 35, 50 y 80 GB, en subcarpetas.

Los dos mensajes son buscar MKV entre 8 y 50 GB en `/peliculas` de `synology 1`,
y después comprimir las cinco más pesadas de esas con el perfil configurado.
El resultado esperado es una cola de 50, 35, 25, 18 y 12 GB, sin acciones durante
el primer turno. La prueba falla si el modelo no completa ese recorrido.

Resultado e4b: **no superado**. En la ejecución con inventario sintético registrado
pidió de nuevo el nombre del equipo pese a estar en el mensaje; después pidió
scan_id y profile_id al usuario. No llamó herramientas ni creó tareas.
Evidencia local: `/tmp/hexos-e4b-range-conversation-2`, conversación, generaciones
y veredicto. Esto no invalida las decisiones internas aisladas anteriores, pero
no acredita autonomía conversacional. Falta ejecutar esta prueba con el 12b.

Se corrigió además una carencia independiente: `media.prepare` admite ahora
min_bytes, max_bytes y extensions en la selección por count. El catálogo de
nas.find contiene también archivos fuera del rango; scan_id no conserva filtros.
El modelo debe pasar esos filtros o las rutas exactas. El backend valida límites
y filtra antes de seleccionar las cinco más grandes. La regresión cubre también
una primera página de solo dos resultados, para impedir que el top se limite a
lo mostrado. No se afirma que un modelo que omita los filtros quede corregido
por esta ampliación del contrato.

```bash
python3 -m tools.media_conversation_live --runtime /ruta/helios_runtime \
  --model /ruta/modelo.hnf --template /ruta/chat_template.jinja \
  --evidence-dir /tmp/prueba-conversacion-nueva
```
