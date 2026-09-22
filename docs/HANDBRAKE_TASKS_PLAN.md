# Tareas de compresión: contrato propuesto

Estado 2026-09-22: diseño e inspección completados; base de tareas implementada
con simulador. Ejecución NAS e interfaz de control pendientes.
[Implementación, pruebas y límites](MEDIA_JOBS_FOUNDATION.md).
No se han copiado películas ni iniciado conversiones con este trabajo.

Actualizado con las decisiones de la conversación del 2026-09-21.
El contrato de contextos, recursos y separación de módulos vive en
[INTERNAL_TASKS_ARCHITECTURE.md](INTERNAL_TASKS_ARCHITECTURE.md).

## Alcance de la primera versión

Solo películas de las carpetas de películas de multimedia 1 o multimedia 3.
Series, temporadas, documentales y entradas ambiguas no entran automáticamente;
su clasificación se abordará después.

El 12B interpreta la petición y propone una selección de 1–5 archivos. HexOS
valida la selección y crea un lote con una ficha independiente por película.
Una sola ficha activa: copiar, comprimir, verificar, publicar y cerrar antes de
copiar la siguiente. No preparar cinco copias grandes por adelantado.

Cada ficha conserva equipo, identidad y ruta exacta de origen, subcarpetas,
destino resuelto, perfil congelado, estado, observaciones e intentos. La salida
vuelve a la carpeta de origen de esa película, sin deducir el disco de su título.
Para pruebas, política inicial conservadora: `Título.optimizada.mkv` junto al
original, sin sobrescritura. Un destino existente produce conflicto, no permiso
para sustituirlo. Reemplazo con respaldo queda fuera de esta primera versión.

## Hallazgos de la instalación

Inspección SSH del 21 de septiembre de 2026, contenedor `HandBrake` en Synology 1:

- Imagen declarada: `jlesage/handbrake:latest`; contenedor running/healthy.
- `/watch`: `/volume1/docker/handbrake/watch`, lectura y escritura.
- `/output`: `/volume1/docker/handbrake/output`, lectura y escritura.
- `/storage`: `/volume1/docker/handbrake/storage`, solo lectura dentro del contenedor.
- `/config`: `/volume1/docker/handbrake/config`.
- Perfil de automatización configurado: `General/Very Fast 1080p30`.
- Formato de automatización: mp4; conservar entrada: sí; sobrescribir salida: no.
- Presets personalizados exportados de `/config/ghb/presets.json` a
  `runtime/handbrake-review/presets-export.json` (artefacto local, no configuración aplicada).
- `jellyfin/Fast 1080p30`: x264, RF 19, fast, **MKV** guardado.
- `jellyfin/jellyfin universal device`: x264, RF 18, fast, **MKV** guardado.

La captura de Summary mostraba MP4; el usuario confirmó después **MKV** y entrada
en **storage**. Se usará como base `jellyfin/Fast 1080p30`, con lanzamiento
explícito sobre `/storage` y salida `/output`. No se usará `/watch`: su perfil
automático es distinto. El montaje de storage es de solo lectura para HandBrake;
el adaptador copia a la ruta del host, no intenta escribir dentro de ese montaje.

Referencia del contenedor y automatización:
https://github.com/jlesage/docker-handbrake#automatic-video-conversion
Las capacidades de la versión instalada se deben comprobar antes de elegir el
adaptador de ejecución; la documentación de latest puede cambiar.

## Flujo de una tarea

1. Seleccionar entre una y cinco películas desde una consulta de catálogo,
   ordenadas por tamaño numérico; conservar copia de los filtros y de la selección.
2. Resolver equipo y ruta exacta, revalidar identidad/tamaño/fecha del origen,
   inspeccionar duración, pistas y espacio disponible en origen, trabajo y destino.
3. Congelar el preset completo con versión y hash; no aceptar opciones shell
   arbitrarias propuestas por el modelo.
4. Copiar una película a un staging bajo la ruta del host de storage. Comprobar
   copia completa y publicar la entrada de una vez. No lanzar sobre una copia de
   30 GB todavía en curso. Nombres y directorios aislados por identificador.
5. Lanzar exactamente una conversión por contenedor; cola de hasta cinco entradas.
   El dueño del lanzamiento será el runner explícito; no depositar entradas en
   watch ni interferir con los trabajos manuales o automáticos existentes.
6. Registrar proceso/trabajo remoto identificable, progreso, fase/pasada, tiempo,
   estimación y tamaño provisional. Una desconexión no prueba que haya terminado.
7. Verificar resultado terminado: salida del proceso correcta, archivo de esta
   tarea, tamaño mayor que cero, duración dentro de tolerancia y pistas/códec
   esperados. Registrar por separado validación técnica, objetivo de tamaño y
   calidad visual pendiente; un archivo pequeño no acredita calidad visual.
8. Publicar la salida validada en la carpeta de películas según la política elegida.
   Entre discos: copiar a temporal del destino, verificar y renombrar. Nunca tratar
   un movimiento entre volúmenes como una operación atómica.
9. Actualizar el catálogo con el resultado real y avanzar al siguiente elemento.

## Módulos pequeños

| Componente propuesto | Responsabilidad |
|---|---|
| `media_jobs/store.py` | SQLite: tareas, elementos, eventos, revisiones y próxima observación |
| `media_jobs/profiles.py` | Presets permitidos, versiones, hashes y condiciones de uso |
| `media_jobs/policy.py` | Transiciones, tiempos de espera y criterios de finalización |
| `media_jobs/runner.py` | Reclamar trabajo pendiente y ejecutar una transición idempotente |
| `media_jobs/handbrake.py` | Adaptador de lanzamiento, identificación y progreso remoto |
| `media_jobs/files.py` | Staging, espacio libre, comprobaciones y publicación sin colisiones |
| `chat_backend/media_tools.py` | Contratos estrechos para crear, consultar y cancelar tareas |
| Servicio de tareas | Ejecutar vencimientos sin mantener un turno de chat abierto |

Las fichas actuales de `work.py` son registros, no ejecutores. No añadir procesos,
esperas ni gestión de archivos a ese módulo. Relacionar la tarea operativa con su
ficha por identificador cuando corresponda.

## Espera y reactivación

Persistir `next_check_at` en UTC; no mantener un sleep largo dentro del turno.
Primera comprobación dos minutos después del arranque. Después, política inicial
basada en la última ETA válida:

| ETA restante | Próxima comprobación |
|---|---|
| Más de 30 minutos | 30 minutos |
| Entre 2 y 30 minutos | Al cumplirse esa estimación |
| Hasta 2 minutos | 1 minuto |
| Sin ETA válida | 2 minutos |

Ejemplo solicitado: arranque con ETA 56 min → comprobar a los 2 min → si quedan
56 min, esperar 30 → si quedan 20 min, esperar 20 → si queda 1 min, esperar 1.
Una ETA agotada solo dispara una consulta; nunca marca éxito.

El backend obtiene y registra la observación sin necesitar inferencia. Si hace
falta una decisión del agente, crea una solicitud con job_id, revisión y evidencia
para un turno interno aislado, nunca para la conversación activa del usuario.
Ese turno no repite la petición inicial ni puede duplicar el lanzamiento. Si el
modelo está ocupado, la solicitud espera; la vigilancia determinista continúa.
Una señal fiable de finalización puede adelantar la observación programada.

## Persistencia y recuperación

Estados separados: pendiente, copiando, preparada, comprimiendo, recuperando,
verificando, pendiente_de_publicación, publicando, completada, error,
cancelación_solicitada y cancelada. El lote puede pausarse sin perder las fichas.
Pausar el lote impide iniciar nuevos elementos; no supone suspender el encoder
activo. Cancelar una tarea activa es una operación distinta.

Guardar fuente, destino, identidad del proceso, hash del preset, timestamps,
bytes copiados, bytes provisionales/finales, porcentaje por fase, ETA, próximo
control y evidencia de cada transición. Reclamo transaccional con lease impide
dos trabajadores sobre la misma tarea. Recuperar una tarea tras reinicio exige
consultar el proceso y reconciliar sus archivos antes de reintentar una acción.

Cancelar señala el proceso concreto y verifica su parada; la cancelación ordinaria
no detiene todo el contenedor ni otras conversiones. Los restos de staging pertenecen a la tarea;
no limpiar archivos ajenos ni borrar originales automáticamente.

## Bloqueos y recuperación acotada

Observar fase/pasada, porcentaje, actividad del proceso, logs, tamaño provisional
y hora de cada medida. Confirmar ausencia de avance con varias observaciones
válidas y un umbral por fase. Una ETA fija, un archivo que todavía no crece o un
fallo de SSH por separado no prueban bloqueo. Los umbrales se fijan con medidas.

1. Registrar evidencia y marcar recuperando; impedir otra conversión del lote.
2. Intentar detener solo el proceso de la ficha y comprobar la parada.
3. Si no responde, permitir reinicio del contenedor únicamente tras comprobar
   que no hay trabajos manuales o ajenos que se interrumpirían. Si no se puede
   comprobar exclusividad, pausar y notificar; no reiniciar a ciegas.
4. Verificar contenedor utilizable y proceso previo ausente antes de relanzar.
5. Separar la salida parcial y no publicarla. El nuevo intento tiene identidad
   propia y usa el mismo origen verificado y preset congelado.
6. Máximo un reintento automático por ficha; persistir el contador antes de
   lanzarlo. Un nuevo fallo termina en error, sin bucle de reinicios.

Un fallo propio de una película permite avanzar a la siguiente tras cerrar su
recuperación. Disco lleno, servicio inaccesible o conflicto de exclusividad son
problemas compartidos: pausar el lote para no repetir el mismo fallo cinco veces.

## Publicación y fin verificable

Ni `running` del contenedor ni 100 % de una pasada equivalen a película terminada.
Se requiere terminación satisfactoria del trabajo identificado y validación de
su archivo. Objetivo de 5–8 GB, validez técnica y valoración visual se registran
por separado: RF 19 no promete un tamaño fijo. Si no satisface un criterio
obligatorio de la tarea, conservar el resultado para revisión sin publicarlo.

Publicar sin sobrescribir mediante temporal en el filesystem de destino y
verificación de la copia. Completada significa salida publicada y registrada en
el catálogo, no solo encoder finalizado. La limpieza posterior se limita a los
temporales propios cuya publicación esté comprobada; nunca al original.

## Decisiones pendientes

- Verificar interfaces de progreso, launcher y lector de metadatos disponibles
  en la instalación antes de implementar el adaptador.
- Confirmar con una conversión real duración, pistas preservadas y tolerancias.
- Política futura de reemplazo/backups; primera versión conserva el original.

## Pruebas necesarias antes de lanzar una película real

Reloj simulado para la secuencia 2/30/20/1; ETA ausente o cambiante; reinicio en
copia/compresión/publicación; reclamación concurrente; desconexión SSH; disco
lleno; copia incompleta; entrada modificada; mismo nombre en dos carpetas;
archivo de salida previo; perfil incorrecto; fallo del encoder; duración o pistas
incorrectas; publicación entre discos; cancelación sin afectar otros procesos.

Añadir: reinicio con trabajo ajeno, segunda recuperación bloqueada, fallo
compartido que pausa el lote, exclusión de series/documentales, no copiar el
siguiente elemento antes de cerrar el anterior y publicación sin sobrescritura.
