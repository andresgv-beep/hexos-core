# Chat, servicio y revisión interna

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
