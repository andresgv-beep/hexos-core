# Abrir, leer y descargar documentos del NAS

Implementado el 2026-09-21. El buscador de metadatos y el lector de contenido son
capacidades separadas. La apertura no modifica el NAS.

## Uso

1. `nas.find` o `nas.search` devuelve `scan_id` y una ruta de archivo observada.
2. `nas.file_open(scan_id, path)` obtiene el equipo desde ese catálogo, abre el
   archivo por SSH sin seguir enlaces y compara tamaño, mtime, inode y filesystem.
   Si cambió, pide actualizar el catálogo; no usa una ruta parecida.
3. Guarda una copia inmutable local y devuelve `file_id`, tamaño, SHA-256 y si hay
   texto disponible. La interfaz abre el visor al recibir el resultado del turno.
4. `nas.file_read(file_id, offset, count)` entrega hasta 6.000 caracteres. El modelo
   continúa con `next_offset`; `null` indica final. Las líneas largas y Unicode no
   bloquean el avance. Los límites de operaciones por turno siguen vigentes: abrir
   un archivo no acredita haberlo leído entero.

El botón **Archivos del NAS**, en escritorio y móvil, permite recuperar las 50
copias más recientes. El visor muestra texto literal por fragmentos y ofrece
descargar los bytes originales. No interpreta Markdown como HTML ni ejecuta
contenido del documento. Las instrucciones dentro de un archivo son datos
externos, no permisos para actuar.

## Límites de esta primera versión

- Máximo 8 MiB por archivo, comprobado antes de transferir y durante la lectura.
- Texto UTF-8 (con o sin BOM): Markdown, texto y otros archivos textuales.
- Binarios y otras codificaciones: descarga disponible, sin extracción de texto.
  PDF/DOCX requieren sus futuros lectores; no se afirma haber leído su contenido.
- La copia tiene fecha de lectura; los cambios posteriores en el NAS no la alteran.
- No hay aún limpieza automática de copias, streaming de películas ni pines.
- La interfaz abre el visor al finalizar el turno. Abrir no requiere otra generación
  para preparar el archivo; la decisión del modelo de elegir la herramienta sigue
  siendo evaluable por separado.

## Responsabilidades

| Módulo | Responsabilidad |
|---|---|
| `nas_document_remote.py` | Abrir un archivo regular sin enlaces, verificar identidad y transferir bytes acotados |
| `file_catalog/file_access.py` | Validar procedencia del catálogo y exponer apertura/lectura por fragmentos |
| `file_catalog/file_copies.py` | Guardar copias y metadatos en `file_copies.sqlite` |
| `chat_backend/file_http.py` | Servir copias por identificador, sin aceptar rutas del filesystem |
| `interfaz/lib/helios/files.ts` | Contrato cliente del visor |
| `interfaz/components/NasFileViewer.tsx` | Selección, lectura por fragmentos y descarga |

La descarga usa `Content-Disposition: attachment`, tipo binario, `nosniff` y CSP
restrictiva. Los nombres se codifican en la cabecera. No se expone una URL de
descarga arbitraria ni se entrega base64 al contexto del modelo.

## Verificación

248 pruebas de backend, 81 de interfaz, tipos TypeScript y build/render correctos. Regresiones:
archivo cambiado, enlace en lugar del origen, ruta ajena al catálogo, límite de
tamaño, binario, archivo vacío, Unicode y línea larga, descarga idéntica al hash,
despacho sin pedir equipo y validación de identificadores del visor.

Prueba real: `HELIOS_ECOSYSTEM_COMPLETE_AUDIT.md` de Synology 1, 86.992 bytes.
La descarga a través del proxy de la interfaz coincide con el SHA-256 de la copia;
12 fragmentos de texto reconstruyen su contenido completo. Evidencias locales:
`runtime/logs/file-open-live.json` y `runtime/logs/file-download-live.json`.
Esto valida herramientas y HTTP; no certifica la elección del lector por el 12B
en la otra máquina ni sustituye una comprobación visual del visor en navegador.

### Continuación de lectura y formato nativo

El intérprete acepta un bloque `thought` cerrado después del preámbulo visible
y antes de la llamada. Separa el razonamiento sin alterar los argumentos ni los
marcadores dentro de cadenas de la herramienta. Los canales incompletos,
anidados o repetidos y las llamadas malformadas siguen rechazándose.

`tools/native_channels_test.py` reproduce la secuencia reportada por el 12B:
preámbulo, canal vacío y `nas.file_read` con `offset=4000`, `count=4000`.
Comprueba que se registra una sola llamada y que el texto de pensamiento no se
muestra ni se ejecuta. La batería ampliada de backend pasa 291 pruebas; esta
regresión usa una salida simulada, pendiente de repetir con el 12B real.
El cambio es Python: requiere reiniciar el backend, sin recompilar el motor.
