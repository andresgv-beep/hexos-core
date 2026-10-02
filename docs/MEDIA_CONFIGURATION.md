# Configuración multimedia de Helios

Referencia de instalación actualizada el 2 de octubre de 2026. La configuración
reproducible está en
[`runtime/examples/media_jobs.helios-rf18.json`](../runtime/examples/media_jobs.helios-rf18.json).
Contiene el preset completo y su hash, las rutas del NAS y las políticas
autorizadas por el operador. No incluye credenciales, historial ni tareas SQLite.

## Perfil y alcance

- Perfil `jellyfin-1080-rf18`, nombre `Helios 1080p RF18`.
- H.264 x264, calidad constante RF 18 (`VideoQualityType: 2`), preset `fast`,
  sin tune, perfil `main`, nivel `4.0`, pico de 30 fps (`pfr`).
- El valor `VideoAvgBitrate: 9000` reproduce el campo alternativo de la captura;
  no es un objetivo ni un límite de bitrate con calidad constante seleccionada.
- Se conservan resolución máxima 1080p, MKV, audio y subtítulos del preset
  existente. El cambio de vídeo no constituye una revisión de filtros o HDR.
- Compresión autorizada en `/volume1/multimedia 1/Multimedia` y
  `/volume4/multimedia 3/multimedia`, incluidas sus subcarpetas: Series, Disney,
  Marvel, etc. Las raíces anteriores `peliculas` se conservan como entradas
  explícitas para las fichas existentes y las selecciones acotadas a películas.
- `require_smaller: true` y `replace_original: true`: se exige reducción de
  tamaño y se elimina el original después de verificar, publicar e indexar.
  La comprobación técnica no evalúa calidad visual (`visual_quality=not_assessed`).

El catálogo NAS puede leer otras rutas con los permisos de su conexión. La lista
`files.libraries` limita las operaciones de conversión; no configura permisos
del usuario del NAS. Ampliarla no inicia conversiones por sí solo. El contrato
interno sigue usando `kind=movie` para los vídeos seleccionados: esta ampliación
no añade clasificación semántica de series ni selección automática de temporadas.

## Git y configuración activa

HexOS lee `media_jobs.json` dentro del workspace indicado al arrancar. En esta
instalación es `/home/andres/Documentos/hexos-prueba-12b-hq42/media_jobs.json`.
El archivo de ejemplo de Git no se carga automáticamente ni sustituye ajustes
al actualizar el código. Permite revisar y recuperar los valores de esta
instalación; en otra máquina deben adaptarse equipo, rutas y ejecutables.

Para recuperar la configuración, respaldar primero la existente y comprobar
que no haya tareas no terminales. Con el backend parado, copiar el ejemplo al
workspace como `media_jobs.json`, protegerlo con permisos 0600 y validar con
`hexos.agent.media_jobs.configuration.load(workspace)` antes de arrancar.
El ejemplo lleva `enabled: true` y borrado de originales activado: reproduce
la política elegida para esta instalación, no una configuración universal.
Las credenciales se restauran por separado desde su respaldo privado.

El trabajador recarga la configuración en cada tick. Cada tarea conserva la
huella de la configuración con la que se encoló: un cambio de huella bloquea
su seguimiento aunque HandBrake continúe ejecutándose en el NAS. Reiniciar
sin cambiar los ajustes conserva esa huella y recupera el seguimiento.

La ampliación del 2 de octubre se aplicó con el backend detenido, respaldo de
configuración y SQLite, y una migración controlada de la ficha activa. Se
comprobó que solo se añadían bibliotecas, conservando perfil, origen, destino,
estado y `run_id`; se registró `operator_library_expansion` en los eventos.
Fue una operación de mantenimiento de esa instalación, no una migración que
se ejecute al hacer checkout. No cambiar huellas de tareas automáticamente
para aceptar modificaciones generales del preset o de las políticas.

Los trabajos terminados permanecen en «Recientes» del panel Tareas; el chat
muestra solo los activos. Ese comportamiento sí forma parte del código de `main`.
