# Encoder real: alcance y evidencia

Fecha: 2026-09-22. Rama `codex/handbrake-task-foundation`.

## Contrato operativo

`NasHandBrake` implementa el contrato del encoder con transporte inyectado.
No se instala automáticamente ni activa nuevas herramientas de escritura en el
chat. El placeholder sigue siendo la alternativa explícita cuando no hay adapter.

- Recibe el preset completo congelado, su versión de exportación y una ruta
  previamente preparada bajo `/storage/.hexos-media/`.
- Cada intento de cada ficha determina un `run_id` SHA-256. La salida queda bajo
  `/output/.hexos-media/<run_id>/encoded.mkv`; no se toca `/watch`.
- El controlador guarda la petición y la intención antes de arrancar un worker
  independiente del SSH. Repetir la clave reconcilia el recibo, no vuelve a lanzar.
- Los archivos de control quedan en `/config/.hexos-media/runs/<run_id>/`:
  petición, intención, estado, preset, log y marcador de cancelación.
- Escrituras por reemplazo atómico con fsync. Un candado por ejecución serializa
  arranque/cancelación; otro impide dos workers HexOS usando el encoder a la vez.
- Si cae el controlador entre la intención y el proceso, no se puede afirmar
  si arrancó. Tras 30 s sin recibo se bloquea la tarea para reconciliarla. No se
  promete ejecución exactamente una vez ante cualquier caída: se evita duplicar
  automáticamente un efecto incierto.
- Lee el JSON de HandBrake: fase, porcentaje, ETA; añade tamaño de salida y
  actividad CPU del proceso. No confunde heartbeat del supervisor con avance.
- Cancelar solicita terminar el proceso propio, espera hasta 10 s y escala a kill.
  El runner vuelve en 15 s mientras la parada está pendiente. Si no hay confirmación
  en 30 s, bloquea; no declara cancelado un proceso que podría seguir vivo.
- SSH tiene un presupuesto de 20 s compartido entre rutas, por debajo del lease
  de 30 s del runner. La conversión continúa fuera de esa llamada.

El reinicio del contenedor está **deshabilitado** en este adaptador. La GUI está
abierta y no hay una prueba suficiente de exclusividad. La máquina de estados
admite recuperación, pero no debe reiniciar trabajos manuales ajenos. Para activarlo
se necesita un contenedor dedicado o un mecanismo verificable de propiedad.

No hay limpieza automática de recibos/salidas ni recogida de procesos inciertos.
Conservarlos permite diagnosticar y reconciliar sin sobreescribir evidencias.

## Prueba real

NAS `synology 1`, contenedor `HandBrake`, CLI 1.9.2. Preset hoja recuperado de
`jellyfin/Fast 1080p30`, exportación 59.0.0: x264, RF 19, fast, main/4.0, límite
1080p sin aumentar resolución, PFR 30, MKV y reglas originales de audio/subtítulos.
No se reconstruyó el preset a partir de capturas.

Se generó localmente un vídeo sintético de 15 s, 320×180, 24 fps y tono de audio.
Se transfirió a un directorio nuevo bajo storage y se lanzó con ese preset. La
segunda prueba reproducible produjo:

- `run_id`: `ee276ff831a28a6748c41a654b3267b7e0fe45eed41326d975384d34ff572e16`.
- Exit code 0; MKV de 315.322 bytes, H.264 + AAC, duración 15,061 s.
- Descarga y comprobación independiente con ffprobe; decodificación completa con
  `ffmpeg -xerror` sin errores.
- Repetición de start: mismo recibo final y PID, sin segundo proceso de compresión.

La muestra es demasiado corta para medir rendimiento sostenido, calidad de cine,
objetivo de 5–8 GB, bloqueo prolongado o ETA real. Progreso y cancelación se
comprueban además con un subproceso controlado en pruebas locales. No se ha
reiniciado el contenedor ni se han copiado/comprimido películas de la biblioteca.

## Repetir

`tools/media_encoder_smoke.py` es opt-in y requiere ffmpeg/ffprobe locales.
Acepta un JSON con `preset` (hoja completa) y `version` (campos VersionMajor,
VersionMinor y VersionMicro de la exportación). Escribe evidencia JSON local y
conserva los archivos remotos de prueba. Las credenciales no entran en ese JSON.

```bash
python3 -m tools.media_encoder_smoke \
  --workspace /ruta/al/workspace-con-credenciales \
  --device 'synology 1' \
  --storage-host-root /volume1/docker/handbrake/storage \
  --output-host-root /volume1/docker/handbrake/output \
  --preset-json /tmp/handbrake-preset.json \
  --evidence /tmp/handbrake-smoke-evidence.json
```

Pruebas locales: `tools/media_encoder_test.py` y caso de parada pendiente en
`tools/media_jobs_test.py`. La batería ampliada de esta entrega suma 292 pruebas:
encoder, cola, sesiones internas, SSH, archivos, catálogo, chat, contenedores y
parsers. El parser de laboratorio requiere `PYTHONPATH=.:tools` en esta rama;
no se ha importado la corrección independiente de la rama de Claude.

## Lo pendiente para usarlo desde Helios

Actualización: el primer punto está implementado y probado con un vídeo sintético;
ver [validación del recorrido de archivos](HANDBRAKE_FILES_VALIDATION.md).

1. Adaptador de archivos con copia durable, espacio libre, identidad del origen,
   verificación de duración/pistas/decodificación y publicación sin sobrescribir.
2. Servicio persistente de vencimientos y configuración explícita del recurso;
   después, herramienta para preparar y lanzar lotes de 1–5 películas.
3. Panel/consultas del estado real y actualización del catálogo al publicar.
4. Fábrica real de sesiones internas en `text/0x0`; posteriormente binding a
   cortex. El modelo no participa en la espera ni es dueño del proceso encoder.
