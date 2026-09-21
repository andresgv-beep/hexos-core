# Base modular del catálogo de archivos

Primera etapa implementada el 2026-09-20. La misma base admite metadatos de
documentos, música y vídeo, con extensiones arbitrarias. Buscar un PDF por nombre
no implica leer su texto. El catálogo conserva observaciones, no garantiza el
estado actual del NAS.

## Responsabilidades y dependencias

```text
Herramientas nas.* → nas_files.py (composición y compatibilidad)
                         │
                   FileCatalog
                   /         \
          FileReader          CatalogStore
              │                    │
            ssh.py        sqlite_repository.py
              │                    │
        nas_session          nas_files.sqlite
              │
      nas_files_remote.py
```

Todos los módulos salvo la fachada y el lector remoto están en
`hexos/agent/file_catalog/`:

| Módulo | Responsabilidad | Dónde investigar un fallo |
|---|---|---|
| `ports.py` | Contratos sustituibles de lectura y almacenamiento | Implementaciones incompatibles |
| `service.py` | Navegar, publicar y consultar usando puertos inyectados | Política de publicación completa/parcial |
| `validation.py` | Validación pura de rutas, extensiones y rangos | Filtros rechazados o mal normalizados |
| `ssh.py` | Preparar y decodificar el protocolo del lector remoto | Transporte, autenticación y protocolo |
| `sqlite_repository.py` | Esquema, transacciones y consultas parametrizadas | Persistencia, conteos o filtros SQL |
| `presentation.py` | Vistas compactas y paginación para el chat | Resultados que consumen demasiado contexto |
| `directories.py` | Lecturas actuales de carpetas y recursos compartidos | Diferenciar carpetas, memoria y archivos |
| `directory_snapshots.py` | Observaciones persistentes de directorios, usadas por el adaptador SQLite | Páginas estables sin repetir lecturas remotas |

`nas_files_remote.py` sigue siendo un programa autónomo de biblioteca estándar:
observa metadatos en el NAS sin importar el agente. Los problemas de recorrido,
montajes o permisos de archivos se investigan allí. La recuperación del contexto
del modelo continúa en `chat_backend`, fuera del catálogo.

`nas_shares_remote.py` lee la configuración SMB de Synology sin recorrer archivos.
El adaptador SSH selecciona ese lector para `nas.shares`; `nas.directories` usa
el recorrido seguro existente con selección de directorios, incluidos los vacíos.

`chat_backend/file_requests.py` verifica nombres expresamente indicados en el
mensaje actual antes de ejecutar búsquedas: cambiar `HNF9` por `HNFV9` produce
un error corregible, no una búsqueda de otro objeto. No interpreta todos los
modos posibles de expresar un nombre. Las peticiones aproximadas y las referencias
ambiguas siguen el circuito del modelo. Un mandato simple de buscar una carpeta,
con nombre literal y un único equipo explícito, se integra en `explicit_read`
para impedir que el modelo lo dé por resuelto reutilizando una respuesta antigua.
No se extiende ese atajo a órdenes con subcarpetas, varios equipos o prosa adicional.
El listado simple de carpetas compartidas con un equipo explícito tiene el mismo
tratamiento de lectura actual.

`chat_backend/file_responses.py` presenta listados sencillos directamente desde
los resultados estructurados: nombre literal, rutas, acceso y cobertura parcial.
Se aplica solo a formas explícitas acotadas y resultados del mismo alcance;
las solicitudes compuestas siguen con respuesta del modelo. Esto impide que
un resumen de esos listados omita incidencias o exponga parámetros internos.

El servicio no importa SSH, SQLite ni el chat. Recibe
`FileCatalog(reader, store)` y puede probarse con un lector local o simulado.
El repositorio devuelve registros completos; la presentación copia y reduce
las vistas sin modificar los datos originales. El repositorio no conoce el
presupuesto de contexto del modelo. La fachada conserva las firmas de las
herramientas existentes y construye los adaptadores.

## Contratos y consistencia

- El lector recibe equipo y petición estructurada (`operation`, `roots` y
  filtros del recorrido). Devuelve equipo, fecha, registros y cobertura;
  `complete=false` y los errores nunca se interpretan como biblioteca vacía.
- `CatalogStore.publish` guarda observación, archivos y directorios en una
  transacción. Devuelve un `scan_id` nuevo. Un error revierte la publicación;
  las observaciones previas siguen consultables.
- `nas.index` exige lectura completa. `nas.find` puede publicar hallazgos
  parciales con su cobertura explícita. Ninguno sustituye observaciones previas.
- Las páginas locales conservan `scan_id`, filtros y `next_offset`. La memoria
  de directorios conserva la fecha de observación, no prueba existencia actual.
- Se conserva el archivo SQLite y su esquema. Esta separación no requiere
  migración ni invalida los identificadores guardados.

La ampliación posterior añade la tabla `directory_snapshots` al publicar una
observación de carpetas, sin alterar tablas ni identificadores anteriores.
`listing_followups.py` conserva la consulta reciente a través de la traza, y el
coordinador recupera sus páginas sin inferencia. `history_archive.py` pagina el
archivo visible con cursores estables, separado de la ventana de contexto.

## Siguientes etapas, todavía pendientes

1. Registro explícito de bibliotecas: identificador, equipo, raíces y alcance.
   Permite actualizar una biblioteca concreta sin redescubrir todo el NAS.
2. Actualización con estado y caducidad por biblioteca, trabajos reanudables y
   tratamiento de cambios, eliminaciones y fallos parciales. Una ruta sin acceso
   no debe provocar eliminaciones del catálogo. Los snapshots actuales no son
   un sincronizador incremental ni reconocen renombrados como identidad estable.
3. Pines persistentes y lectores PDF/DOCX. Ampliar el acceso ya disponible para
   texto UTF-8 manteniendo la revalidación del archivo y la lectura por fragmentos.
4. Conversión con HandBrake como servicio de trabajos propio, después de
   revalidar el archivo de origen y definir verificación y publicación del resultado.

La ampliación del 2026-09-21 incorpora lectura de texto, visor y descarga acotada
en [NAS_DOCUMENTOS.md](NAS_DOCUMENTOS.md). No hay aún refresco automático,
extracción PDF/DOCX, pines ni conversión.
Las búsquedas persistentes actuales son snapshots consultables; no son objetos
de consulta guardada. Cada etapa debe añadir su contrato y pruebas sin incorporar
esas responsabilidades a `service.py` o al despachador del chat.

## Verificación de esta etapa

`tools/file_catalog_test.py` comprueba una biblioteca mixta PDF/MD/MP3/MKV,
renombrados, tamaños nuevos, altas y bajas entre dos lecturas; persistencia de la
observación anterior; consulta sin lector disponible; rollback transaccional;
vistas que no alteran registros; e independencia de importaciones entre capas.
`tools/nas_files_test.py` mantiene las regresiones del protocolo y las herramientas.

Estas pruebas usan archivos temporales y no modifican contenido del NAS. Simulan
los cambios entre lecturas; no certifican actualización automática ni el
comportamiento lingüístico del modelo. Los límites operativos y las pruebas
anteriores con equipos reales están en [NAS_CONTENIDO.md](NAS_CONTENIDO.md).

La ampliación de directorios incorpora `tools/nas_directories_test.py`: carpetas
vacías, diferencias entre `HNF9` y `HNFV9`, mayúsculas, permisos, renombrados,
configuración SMB, protección del literal y presentación de resultados parciales.
Tras añadir continuidad y paginación del historial, la batería conjunta pasa
241 pruebas de backend y 78 de interfaz, más comprobación de tipos TypeScript.
`tools/listing_continuity_test.py` cubre el diálogo de 39 carpetas, reinicio,
lectura sin red/modelo, corrección de alcance y cursores de historial con nuevas
inserciones. La comprobación visual con navegador no pudo completarse por un
fallo de conexión de la herramienta; se verificaron API, proxy y render estático.
