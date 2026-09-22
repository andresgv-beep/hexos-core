# Archivos y recorrido completo en NAS

2026-09-22, rama `codex/handbrake-task-foundation`. Los adaptadores de archivos y
encoder se conectan al Runner existente. La prueba se ejecuta desde una utilidad
operativa; no habilita acciones nuevas para el chat ni instala un servicio.

## Responsabilidades y efectos

`nas_files_adapter.py` congela la configuración del operador, construye peticiones
estables sin revisión/progreso conversacional y actualiza el catálogo.
`nas_files_transport.py` despliega un ZIP de módulos por hash y realiza llamadas
SSH de hasta 20 s. Los workers viven en el host NAS y continúan fuera del SSH.
Cada acción tiene intención durable, petición, lock, progreso y resultado.

Los módulos remotos separan controlador, worker, primitivas de copia, reglas de
publicación e inspección multimedia. Ninguno interpreta instrucciones del modelo
ni recibe shell generado por él. Las bibliotecas y binarios vienen del operador.

### Copia a storage

- Solo bibliotecas explícitas de películas. Destino derivado de la ruta original,
  preservando las subcarpetas; nunca deducido por el título.
- Identidad (tamaño, mtime_ns, inode, filesystem) comprobada antes y después de copiar.
  Apertura por descriptores sin seguir enlaces en los componentes.
- Espacio libre para la copia más reserva de 64 MiB. No es una reserva global
  contra otras aplicaciones que escriban en el disco.
- Temporal exclusivo, copia en bloques, SHA-256 del origen leído y comprobación
  de la copia por nueva lectura. Entrada completa bajo `/storage/.hexos-media/<id>/`.
- No se toca `/watch`. Se conserva el original y los temporales propios.

### Verificación

Se usan FFmpeg/FFprobe **explícitos**, disponibles en este NAS en
`/var/packages/ffmpeg7/target/bin/`. El `/usr/bin/ffmpeg` del NAS carece del decoder
H.264 y no sirve para esta comprobación. No se ha instalado software adicional.

Se exige recibo correcto del encoder de esta ficha, tamaño concordante, MKV,
un vídeo H.264 de dimensiones válidas hasta 1080p y duración con tolerancia
máxima de 1 s o 0,1 %. Se verifica el número de pistas AAC previsto por el perfil
de primer audio. Se calcula hash y se decodifica todo vídeo/audio con `-xerror`.
La identidad se comprueba después de la decodificación.

Primer contrato soportado: selección del primer audio, un encoder AAC explícito
y selección de subtítulos `none`. Otras reglas se rechazan hasta ampliar el
verificador. **Calidad visual y subtítulos quemados no están evaluados** y aparecen
así en la ficha. No se certifica compatibilidad con todos los reproductores.

Por defecto se rechaza una salida que no reduzca el tamaño del original.
No se garantiza el intervalo 5–8 GB con RF 19. La prueba sintética desactiva
explícitamente `require_smaller`: un tono corto a 16 kbps crece al convertirlo con
el audio del preset del usuario. Esto permite probar el recorrido sin presentar
la muestra como evidencia de ahorro.

### Publicación y catálogo

El original se revalida antes de publicar. Se copia la salida validada a un
temporal en la **carpeta de destino**, comprobando hash, y se publica mediante
hardlink exclusivo dentro de ese filesystem. Funciona aunque output esté en otro
volumen: no se usa rename entre discos. Un destino existente nunca se reemplaza.
Se conserva el temporal como evidencia; la limpieza automática queda pendiente.

La salida se llama `Título.optimizada.mkv`. Su identidad y hash se vuelven a
observar antes del catálogo. La observación tiene identificador estable y su
repetición no duplica el snapshot. Está marcada como parcial/puntual: no afirma
haber recorrido de nuevo toda la biblioteca.

### Cancelación y fallos

Cancelar marca la ficha en el NAS y espera a que sus workers dejen de escribir
antes de cerrar la cancelación. La publicación final comparte el lock de control:
la cancelación sucede antes o después del commit, y se conservan los efectos ya
realizados. No elimina una salida que se hubiese publicado justo antes.

Si desaparece un worker, se bloquea para revisar recibos/temporales; no se reinicia
la misma acción a ciegas. Aún falta una herramienta de reconciliación operativa
para estos casos. Reanudar el lote no borra ni sustituye esa evidencia.
Existe un límite configurable de 24 h por acción comprobado entre bloques; una
lectura de disco bloqueada en el kernel puede necesitar intervención externa.
No se reinicia el contenedor y no se tocan procesos ajenos.

## Evidencia

Primera ficha completada: `8f051b6bc3fb421b907e916abc03f5b5`.
Biblioteca sintética bajo `/volume1/docker/handbrake/.hexos-library-tests/`, con
subcarpeta y nombre con espacios/tildes. Fuente de 15 s, 320×180, vídeo + tono.

Recorrido real: copiar → ready → HandBrake → verificar → publicar → indexar →
completed. Salida MKV de 315.322 bytes, 15,061 s, H.264 + AAC. Comprobación
independiente posterior confirmó la identidad original y el hash publicado.
No se han usado películas de las bibliotecas multimedia 1 o 3.

`tools/media_pipeline_smoke.py` reproduce el recorrido; requiere workspace de
credenciales, configuración de rutas/binarios, preset completo y raíz de pruebas.
Crea su propia subcarpeta y SQLite de evidencia. Acelera **el reloj de consultas**
del Runner para no esperar minutos entre pasos; la copia, compresión, verificación
y publicación son reales. No valida por ello una noche de ejecución ni su servicio.

313 pruebas locales en la batería ampliada. Incluyen origen modificado, enlaces,
espacio insuficiente, cancelación, destino ocupado, hash cambiado, duración/códec/
audio incorrectos, salida sin ahorro, respuesta perdida, worker ausente y replay
del catálogo. La publicación entre filesystems se prueba usando `/dev/shm` y `/tmp`.

## Siguiente integración: turno del e4b

El Runner de prueba publica determinísticamente. Para el flujo acordado falta
detenerse tras la verificación, registrar un despertar persistente y dar al e4b
una ficha con herramientas de continuación. El backend deberá rechazar una
publicación ajena, obsoleta o sin validar, aunque el modelo la pida. También
despertará ante incidencias; las consultas normales de progreso no necesitan LLM.

Después se probarán los tres casos: salida correcta, trabajo que sigue activo y
salida inválida. Todavía **no se ha probado la capacidad del e4b** con este circuito.
