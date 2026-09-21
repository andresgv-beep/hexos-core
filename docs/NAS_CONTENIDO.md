# Contenido del NAS: exploración, catálogo y futura conversión

## Objetivo y alcance implementado

Helios dirige desde la máquina de IA. Los archivos permanecen en el NAS; su
Python 3 recorre metadatos mediante el usuario SSH ya configurado, sin sudo,
instalaciones ni escritura remota. Hexos guarda localmente un catálogo SQLite
de rutas, tamaños y fechas. No descarga películas ni lee su contenido.

Implementado: navegar carpetas, indexar varias raíces de un mismo equipo y
buscar recursivamente extensiones arbitrarias (MKV, MP4, AVI, MP3, etc.), con tamaños mínimo y máximo
opcionales. Sin filtros: desde cero bytes, sin máximo. HandBrake, análisis de
códecs, cola de conversión y sustitución de originales **no están implementados**.

## Responsabilidades

```text
Agente → catálogo de herramientas → ToolDispatcher
                                      │
                             AgentDependencies.nas_files
                                      │
                               nas_files.py
                         ┌────────────┴─────────────┐
                 browse/find/index                search
                         │                          │
              nas_session.execute_remote     nas_files.sqlite
                         │                   snapshots inmutables
                SSH + identidad existente
                         │
                  nas_files_remote.py
              metadatos en el propio NAS
```

- `catalog.py` declara argumentos y uso, incluidos los esquemas nativos. No se
  añade lógica NAS al prompt general del modelo.
- `chat_backend/tools.py` resuelve el equipo y conserva el diálogo de credenciales
  y la operación pendiente. La búsqueda local no requiere credenciales.
- `nas_files.py` conserva la API y compone el servicio con los adaptadores.
  `file_catalog/service.py` coordina casos de uso con lector y repositorio
  inyectados; `ssh.py` prepara el protocolo; `sqlite_repository.py` publica en
  transacciones y consulta SQL; `presentation.py` limita las páginas del chat.
  Contratos, pruebas y siguientes etapas en
  [FILE_CATALOG_ARCHITECTURE.md](FILE_CATALOG_ARCHITECTURE.md).
- `nas_files_remote.py` solo usa biblioteca estándar. No importa el agente ni
  conoce claves, historial, presets o SQLite.
- `nas_session.execute_remote` comparte transporte, fijación de host, rutas
  alternativas y autenticación con las herramientas previas. No es una herramienta
  de shell para el modelo: recibe comandos construidos por adaptadores internos.

El protocolo codifica JSON como base64 en una línea identificada. Un nombre como
`password:` no puede activar el envío de la credencial en el transporte interactivo.
Las rutas viajan como argumento JSON citado, nunca interpoladas como shell.

## Herramientas disponibles

| Herramienta | Entrada | Resultado |
|---|---|---|
| `nas.directories` | `device`, `query` literal, `exact`, `roots`, `include_hidden`, `limit`, `offset` | Búsqueda actual recursiva de directorios, incluso vacíos; ignora mayúsculas y conserva cobertura |
| `nas.shares` | `device`, `limit`, `offset` | Recursos SMB configurados en Synology: nombre, ruta y acceso por SSH; no requiere patrón |
| `nas.directory_page` | `snapshot_id`, `limit`, `offset` | Página local de la misma observación de directorios o recursos compartidos; conserva filtros y alcance |
| `nas.locations` | `device`, `query` (nombre de carpeta), `limit`, `offset` | Directorios recordados con fecha de observación, sin SSH ni recorrido |
| `nas.browse` | `device`, `path` absoluto (defecto `/`), `offset`, `limit` | Una carpeta: directorios, archivos, enlaces y entradas especiales; paginación y cobertura |
| `nas.find` | `device`, `roots` opcional, `extensions`, `min_bytes`, `max_bytes`, `query`, `limit`, `include_hidden` | Descubre volúmenes, recorre subcarpetas y devuelve coincidencias, cobertura y `scan_id` en una llamada |
| `nas.index` (API compatible, oculta al modelo) | `roots` como lista de rutas observadas, `device` | Catálogo estricto: solo publica recorridos completos; rechaza `/` y dirige a `nas.find` |
| `nas.search` | `scan_id`, `extensions`, `min_bytes`, `max_bytes`, `kind`, `query`, `root`, `offset`, `limit` | Página local ordenada por tamaño descendente y ruta, total de coincidencias y siguiente desplazamiento |

Ejemplo orientativo; las rutas reales se descubren, no se suponen:

```json
{"tool":"nas.browse","arguments":{"device":"contenido","path":"/"}}
{"tool":"nas.find","arguments":{"device":"contenido","extensions":["mkv","mp4","avi","mp3"],"limit":5}}
{"tool":"nas.search","arguments":{"scan_id":"ID_DEVUELTO","extensions":["mkv","mp4"],"min_bytes":10000000000,"max_bytes":100000000000}}
```

Los límites son inclusivos. Se puede omitir cualquiera, y `max_bytes=0` encuentra
archivos vacíos. GB decimal significa 1.000.000.000 bytes; GiB, 1.073.741.824.
No hay un filtro fijo de 10 a 100 GB. `query` busca texto literal sin distinguir
mayúsculas Unicode; `%` no es un comodín SQL. `kind=video` clasifica extensiones,
incluidas imágenes ISO candidatas, y no afirma haber inspeccionado un códec.

`nas.find` descubre los montajes Synology `/volumeN` y `/volumeUSBN[/recurso]` desde
`/proc/self/mountinfo` cuando se omiten `roots` o se usa `["/"]`. Añade las carpetas
compartidas que son subvolúmenes Btrfs como raíces propias. En equipos con otra
distribución de datos se pueden indicar raíces explícitas. Las rutas ocultas o
internas `@` se omiten por defecto y se cuentan; `include_hidden=true` las incluye.

La recursión y el filtro de extensiones se ejecutan en el NAS. Se aceptan `MKV` y
`.mkv`, sin comodines ni búsqueda por subcadena (`pelicula.mkv.bak` no es MKV).
Los tamaños y el texto se filtran localmente: pueden cambiarse sin recorrer de
nuevo. Un catálogo creado para MKV/MP3 no contiene AVI; pedir nuevas extensiones
requiere otro `nas.find`. Omitir `extensions` en `nas.search` conserva el alcance
del catálogo. Omitirlas en `nas.find` cataloga todos los archivos del alcance.

La identidad es `(scan_id, path)`: dos películas con igual nombre en distintos
directorios siguen siendo dos entradas. Las raíces solapadas no duplican rutas;
la raíz más específica conserva su atribución. Se guardan inode y filesystem_id,
pero no se infiere duplicación de contenido ni ahorro por ellos.

## Memoria de ubicaciones

La memoria no sustituye la búsqueda de carpetas. `nas.directories` recorre
directorios actuales por nombre (por defecto contiene el texto, `exact=true`
compara el nombre completo), incluso vacíos. Omite raíces para descubrir todos
los volúmenes de datos. `HNF9` y `hnf9` coinciden; `HNFV9` es otro nombre.
Los enlaces no se siguen y la exclusión de ocultos y límites del recorrido se
declaran en el resultado. Los directorios encontrados se recuerdan localmente.

`nas.shares` lee `/etc/samba/smb.share.conf` en Synology sin sudo. Enumera recursos
configurados, no carpetas arbitrarias de un volumen ni coincidencias con la palabra
«compartido». Comprueba por separado si el usuario SSH puede abrir cada ruta;
esto no certifica permisos SMB. Configuración inaccesible o con inclusiones no
leídas produce cobertura parcial, nunca un listado vacío presentado como completo.
Estas dos lecturas guardan ahora una observación de directorios con `snapshot_id`.
`nas.directory_page` pagina esa observación sin repetir SSH y sin mezclar cambios
posteriores. Repetir `nas.directories` o `nas.shares` sí realiza una nueva lectura.
La salida al modelo se limita por filas y caracteres.

### Continuación de listados e historial visible

`chat_backend/listing_followups.py` resuelve continuaciones breves como «muéstrame
todas» a partir de consultas recientes registradas, conservando equipo, raíces,
texto y comparación exacta. Una referencia a «las que están en Compartido» busca
el alcance observado, no la palabra «compartido» en el inventario de recursos SMB.
Si hay varios alcances compatibles, o un cambio de tema, no elige arbitrariamente.
Las observaciones anteriores sin snapshot se vuelven a leer una sola vez con los
mismos argumentos; las siguientes páginas son locales.

El turno recupera las páginas dentro del presupuesto normal de operaciones y
presenta el listado directamente, sin generar otro resumen ni otro anuncio con
el modelo. Si queda paginación al alcanzar el límite, lo declara en la respuesta.
Al entregar una vista estructurada se reconstruye el siguiente contexto desde
el archivo: el modelo no conserva un borrador distinto del texto visible.

Validación real del diálogo reportado: «todas las que están en Compartido» devolvió
las 39 carpetas con `hnf` en 2,286 segundos; «muéstrame todas» repitió las 39 desde
la observación guardada en 0,018 segundos, sin SSH ni generación. Evidencia local:
`runtime/logs/listing-followup-scoped.json` y `listing-followup-all.json`.

El historial visual es independiente de la ventana del modelo. La ruta compatible
`/api/history` mantiene sus últimos 100 mensajes; `/api/history?limit=100&before=…`
añade paginación por cursor estable y solo devuelve texto visible. La interfaz de
escritorio y móvil permite cargar mensajes anteriores sin reemplazar los nuevos.
Se recuperaron 1.726 mensajes en 18 páginas a través del proxy, sin duplicados.

Prueba real de esta ampliación: Synology 1 devuelve 15 recursos configurados,
7 con lectura SSH disponible y 8 sin ella. Buscar exactamente `HNF9` devuelve
cero coincidencias en las rutas accesibles y diez errores de permisos: no demuestra
ausencia en todo el NAS. Evidencia local: `runtime/logs/nas-directories-shares-live.json`.
La primera prueba conversacional volvió a sustituir el literal por `HNFV9`; por
ello se añadió validación del nombre actual y lectura anticipada para mandatos
simples inequívocos. Las pruebas del lector por sí solas no certifican la elección
de argumentos ni la redacción del modelo.

`nas.locations` consulta `directories` en el mismo SQLite, separado de los archivos
y los snapshots. Guarda `(device, path, observed_at)`. `nas.browse` recuerda el
directorio leído y los subdirectorios de cada página; `nas.find`/`nas.index`
recuerdan las raíces observadas y los padres de los archivos encontrados, dentro
de su raíz. No se añaden rutas inventadas ni raíces que fallaron antes de observarse.

Los catálogos anteriores se importan localmente una sola vez, con marca en
`directory_imports`. Esto evita repetir SSH para aprender ubicaciones que ya
constan en los resultados. La consulta por nombre de carpeta prioriza rutas
superiores; buscar `multimedia` no devuelve cada película descendiente.

Para búsquedas por biblioteca, la descripción del catálogo indica consultar
primero `nas.locations` y pasar las rutas pertinentes a `nas.find` como `roots`.
No se cambia silenciosamente el alcance de «todo el NAS»: omitir raíces sigue
buscando en sus volúmenes. Tampoco se garantiza que todos los directorios estén
ya aprendidos, ni que un directorio recordado siga existiendo. Cada lectura actual
comprueba las rutas de nuevo y devuelve errores si cambiaron los permisos.

La memoria persiste al reiniciar. Los directorios vacíos pueden conocerse por
navegación, búsqueda de directorios o como raíces; un índice de archivos filtrado
no descubre todas las carpetas vacías.
No hay detección automática de cambios, borrado de rutas antiguas ni actualización
en segundo plano. Consultar ubicaciones cuesta una lectura local, mientras que
medir archivos actuales requiere recorrer solo las bibliotecas elegidas.

Comprobación local sobre el workspace existente: la importación tardó unos
0,5 segundos y las consultas posteriores unos 0,01 segundos, sin red. Recordó las
bibliotecas de `/volume1/multimedia 1/Multimedia` y `/volume4/multimedia 3/multimedia`
de Synology 1. Regresiones: persistencia, consulta sin transporte, directorios
vacíos, raíces fallidas, importación única, paginación y separación por equipo.

## Consistencia y límites

- Cada catálogo publicado es inmutable. Añadir o borrar archivos después no altera
  las páginas de ese catálogo. Volver a indexar crea otro `scan_id`; el anterior
  sigue consultable. `observed_at` identifica la lectura, `queried_at` la búsqueda.
- El recorrido del NAS no es un snapshot transaccional del sistema de archivos:
  los archivos pueden cambiar mientras se observa. Una futura conversión debe
  revalidar el origen antes de actuar.
- Hasta 16 raíces explícitas o 128 descubiertas. El lector corta a 100.000 entradas
  para indexado/navegación y 1.000.000 para búsqueda filtrada, 25 segundos de
  recorrido o aproximadamente 12 MiB de registros JSON. SSH conserva su plazo de
  45 segundos. Los límites son de ejecución, **no de tamaño de película**.
- `nas.index` no publica ante errores. `nas.find` conserva hallazgos parciales en
  otro snapshot con `complete=false`, `total_is_exact=false` y errores de cobertura;
  nunca reemplaza un catálogo anterior. Se devuelven cobertura y causa; se puede acotar
  la raíz. Una biblioteca que exceda estos límites necesitará un indexador
  incremental persistente, no aumentar indefinidamente la salida del chat.
- No sigue enlaces, abre cada componente sin seguirlos y no cruza montajes
  anidados. Esos montajes se indican como raíces propias. Los omitidos se cuentan.
- `nas.browse` vuelve a observar la carpeta en cada página; puede cambiar entre
  páginas. Para páginas estables de archivos se usa `nas.find` → `nas.search`.
  El modelo recibe solo ruta, tipo y tamaño por entrada para no llenar el contexto
  con metadatos repetidos. Las rutas ocultas y las internas `@` aparecen después
  de las de usuario, pero ninguna se elimina del listado.
- `filesystem_id` distingue sistemas de archivos; no identifica necesariamente un
  disco físico, especialmente con RAID. La raíz mantiene la atribución útil para
  las dos bibliotecas. No se inventan nombres de disco.
- Los tamaños y sumas son lógicos: hardlinks, compresión y archivos dispersos
  impiden tratarlos como ocupación física o ahorro recuperable.
- No hay purga automática de catálogos todavía. Son metadatos persistentes en el
  workspace; la retención deberá preservar IDs usados en trabajos pendientes.

## Siguiente capa: trabajos de HandBrake en el NAS (diseño, no disponible)

Las herramientas de consulta no arrancarán conversiones. El servicio de trabajos
será distinto del catálogo y tendrá un adaptador para HandBrakeCLI. El agente
seleccionará archivos por su identidad de catálogo y elegirá un preset existente;
el ejecutor validará rutas y construirá argumentos, sin aceptar comandos libres.

La cola y el estado de ejecución residirán en el NAS para sobrevivir a cerrar
Helios o perder SSH. Cada trabajo tendrá ID estable, origen y versión observada,
preset y versión, destino, estado, progreso, error y evidencia de verificación.
La consulta del estado reconciliará el trabajo real antes de cualquier reintento.

Estados previstos:

```text
preparado → en_cola → convirtiendo → verificando → completado
                         └───────────────┴──────→ fallido / cancelado
```

Antes de encolar: inspeccionar vídeo/audio/subtítulos, revalidar origen, comprobar
espacio temporal y destino, y evitar trabajos duplicados sobre el mismo archivo.
Usar el preset del usuario, con prueba inicial para medir tiempo, calidad y ahorro.
La concurrencia será configuración del ejecutor, no una deducción del número de hilos.

El destino temporal será distinto del original. La verificación comprobará el
archivo resultante y las pistas esperadas; solo entonces se publicará el resultado
y se medirá la diferencia real de tamaño. Sustituir un original será una operación
separada, con autorización, revalidación y recuperación; no un efecto de buscar,
indexar o convertir. Estos estados y comprobaciones deben vivir en el ejecutor,
no depender de instrucciones al modelo.

## Evidencia local

`tools/nas_files_test.py` ejecuta el lector sobre directorios temporales y archivos
dispersos de hasta 102 GB, sin reservar ese espacio físico. Cubre rangos, cero,
ausencia de máximo, varias raíces, nombres iguales, Unicode, comillas, saltos de
línea, nombres semejantes a prompts, enlaces, límites, publicaciones incompletas,
refresco, páginas estables y el despacho con petición de credenciales.

Las pruebas de SSH, credenciales, contenedores y catálogo comprueban compatibilidad
con el transporte anterior. El NAS necesita Python 3 con las operaciones POSIX
usadas y permisos de lectura sobre las rutas seleccionadas.

### Aceptación real de navegación, 2026-09-20

Agente HTTP con runtime nativo E4B, workspace habitual y credenciales existentes.
El modelo eligió `nas.browse` y consultó `/` y `/volume1` en los dos Synology:
lecturas completas, sin errores de acceso. En Synology 2 navegó desde
`/volume1/multimedia` a `peliculas` y, en un turno posterior, al directorio de una
película; este último estaba vacío. En Synology 1 se verificó el listado de
`/volume1`, con 81 entradas y siguiente página en offset 30.
Al entrar en `/volume1/multimedia 1` se obtuvo `errno=13` (permiso denegado):
el usuario SSH no puede leer esa raíz. No se elevaron permisos ni modificaron
ACL. La respuesta del modelo informó del fallo, pero propuso también una ruta
no observada (`/volume1/multimedia`); la elección posterior debe volver a basarse
en rutas efectivamente listadas.

La prueba inicial mostró dos límites del comportamiento del modelo: resumía las
carpetas en exceso y pedía confirmación para seguir, aunque ya se había pedido
explorar. Se compactó el resultado de navegación y se priorizaron rutas de usuario
para evitar que metadatos y carpetas internas ocuparan la primera página.
Con una ruta concreta navega y lista; todavía no se certifica que complete por sí
solo una exploración abierta o toda la paginación. Esta prueba de navegación
precede al buscador recursivo descrito a continuación.

Evidencia completa local (sin versionar): `runtime/logs/nas-files-live-chat.json`,
`nas-files-interior-chat.json`, `nas-files-actual-files-chat.json` y
`nas-files-synology1-chat.json`, más `nas-files-media1-chat.json` para el bloqueo
de permisos. Las consultas se enviaron a `/api/chat`, no se
sustituyeron herramientas ni respuestas del modelo.

### Búsqueda recursiva real, 2026-09-20

Invocación directa del adaptador con MKV/MP4/AVI/MP3, sin raíces ni límites de tamaño:
1.903 coincidencias en Synology 1 (164.502 entradas recorridas, 11 errores de acceso)
y 15.413 en Synology 2 (284.750 entradas, 2 errores). No se alcanzaron los límites
de tiempo ni volumen de salida. Los recuentos son parciales por los permisos,
no totales certificados del NAS. Evidencia: `runtime/logs/nas-find-filtered-1.json`
y `nas-find-filtered-2.json`, sin versionar.

La primera prueba del modelo eligió `nas.index` sobre `/`, por lo que se ocultó
esa API del catálogo ofrecido: para buscar queda una entrada, `nas.find`.
El siguiente intento eligió `nas.find` con `roots=["/"]`: esa forma ahora significa
descubrir los volúmenes de datos, igual que omitir roots. No modifica permisos
ni recorre solamente la partición de sistema.

La prueba en conversación temporal detectó además dos interferencias del agente:
la recuperación de cobertura de dos equipos forzaba `nas_read` aunque el encargo
fuera buscar archivos, y «te muestro los archivos» podía disparar la comprobación
de apertura de una nota. Se corrigieron ambas en sus responsables
(`recovery.py` y `completion.py`), con regresiones de cobertura y notas. No se
añadieron ejemplos NAS al prompt general ni se borró el historial del usuario.

Las pruebas locales también cubren extensiones normalizadas y compuestas,
recursión profunda, descubrimiento de montajes, interpretación de `/`, paginación
local sin SSH, catálogo parcial, exclusión explícita de ocultos y ampliación de
filtros solo dentro de las extensiones realmente indexadas.

Prueba final con petición natural y conversación temporal: el modelo ejecutó
`nas.find` en ambos equipos sin pedir rutas internas y respondió con los cinco
mayores de cada uno y tamaños en GB. Evidencia:
`runtime/logs/nas-find-fresh-live-v3.json`. El resumen confundió parcialmente
cobertura con paginación (los 1.903/15.413 son totales del catálogo, no de la
primera página; paginar no recupera rutas sin permiso). Se explicitó esa
distinción en el contrato del resultado. Esto no certifica cada formulación del
modelo: la cobertura y los totales estructurados son la referencia verificable.

### Desbordamiento de contexto con páginas grandes

La petición real de MKV entre 8 y 50 GB produjo una llamada con `limit=100`:
unas 40.000 letras de resultados entraron en el contexto. Tras la primera
recuperación se volvió a pedir una página igual de grande, perdiendo además
el máximo y el desplazamiento, y el segundo `context_full` llegó a la interfaz.

Las páginas de `nas.search` (y por tanto `nas.find`) ahora se ajustan a un
presupuesto de unos 6.500 caracteres más encabezado y guía. `limit` sigue siendo
un máximo, no una promesa de devolver esa cantidad. Se conservan rutas enteras,
`returned_count` y `next_offset`; el catálogo SQLite conserva todos los campos.
El modelo recibe ruta, nombre, raíz y tamaño en cada fila, sin repetir inode y
otros detalles que no necesita para presentar el listado. Un encabezado separa
el total filtrado del número de archivos de la página y la cobertura del NAS.

La recuperación conserva `scan_id`, filtros y desplazamiento como referencia
consultable, sin reinyectar todos los resultados ni metadatos históricos. Permite
hasta tres reconstrucciones si hubo operaciones nuevas; dos desbordamientos
consecutivos sin avance siguen siendo un fallo explícito, no un bucle infinito.

Validado con 213 pruebas, incluidas páginas de 100 rutas largas sin omisiones ni
duplicados y desbordamientos sucesivos con/sin avance. En el chat habitual,
sin borrar el historial, una búsqueda nueva volvió a pedir 100 resultados:
recibió 16 filas en unos 6.700 caracteres y terminó sin `context_full`, con cero
reintentos de contexto. Evidencia: `runtime/logs/nas-context-regression-live-fresh.json`.
La repetición literal anterior reutilizó una respuesta histórica sin ejecutar
herramientas: no se cuenta como validación de la lectura nueva.
Tras añadir el encabezado explícito, otra lectura real distinguió las 120
coincidencias del catálogo de las cinco entregadas, sin reintentos de contexto
(`runtime/logs/nas-context-count-live.json`). El modelo tradujo GB a límites
binarios (8 y 50 GiB) en estas llamadas y omitió la salvedad de permisos en la
última respuesta: esas limitaciones de interpretación no se consideran resueltas
por corregir el transporte de páginas y la recuperación del contexto.
