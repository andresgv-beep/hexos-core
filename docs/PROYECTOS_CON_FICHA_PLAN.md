# Proyectos con ficha: retomar sin degradarse

2026-11-13. Plan, sin nada construido todavía. Sale de la conversación de ese día sobre qué
mejorar del Agente.

## La idea

Hoy todo cae en una sola conversación del Agente. A las pocas horas el modelo arrastra restos
de cosas que no tienen que ver entre sí (el NAS, una película, un fallo de CUDA) y se degrada
o se confunde.

Un **proyecto** separa eso sin abrir más chats:

- Crear un proyecto crea **una carpeta nueva** y HexOS apunta a ella.
- Cada proyecto tiene **una ficha**: su memoria, corta y de hechos.
- Al limpiar el contexto, o al cambiar de proyecto, **HexOS le pone la ficha delante** al modelo.
  No se le pide que la lea: se le inyecta como dato, igual que el plan pendiente de una
  instalación. Si dependiera de que el modelo llame a una herramienta, el E4B se la saltaría.

El resultado es un solo chat en el que el modelo empieza siempre limpio y siempre situado.
Cambiar de proyecto y recuperarse de un corte de contexto son la misma operación.

## Lo que ya existe y se aprovecha

- **Las conversaciones ya se separan con una etiqueta** (`chat_backend/persistence.py`). Un
  disparador apunta cada mensaje a la ventana puesta en `agent_state`, y todo lo que lee «lo
  anterior» lo hace por la vista `esta_ventana`. El corte de contexto y el traspaso también
  son de cada ventana (`clave`). Un proyecto es un nivel más de esa etiqueta:
  `agente` → `agente:<proyecto>`.
- **El archivo queda filtrado solo.** `history.search` y compañía leen `esta_ventana`, así que
  no mezclan proyectos.
- **El traspaso de continuidad** (`ContextManager.save_handoff`): al cortar guarda los últimos
  mensajes literales, el encargo activo y la última operación. Es de usar y tirar, se borra
  tras la primera respuesta. Sirve para no perder el hilo; no es la memoria de un proyecto.
- **Los bloques de datos por turno** (`ContextManager.prepare`): el sitio por donde ya entran
  el recuerdo del archivo, la nota señalada o el plan pendiente. La ficha entra por ahí.

## Lo que hay que añadir

1. **Registro de proyectos**: nombre, carpeta, cuándo se creó y cuándo se tocó por última vez.
2. **La ficha**: qué es el proyecto, dónde está, qué se hizo, qué queda pendiente.
   - Los **hechos los apunta HexOS** (órdenes lanzadas, ficheros tocados, resultado de las
     pruebas, planes aprobados). El modelo solo añade el resumen de intención.
   - **Tope de tamaño.** Si crece sin control, la degradación vuelve por otra puerta: lo viejo
     se resume o se retira.
3. **Crear y cambiar**: poner la etiqueta, limpiar el contexto del motor y cargar la ficha.
   Explícito: un botón o «crea un proyecto para X». No se adivina por el tema de la charla.
4. **Inyección de la ficha** en el primer turno tras cada limpieza, junto al traspaso.
5. **El lateral de la interfaz**: proyecto activo, su carpeta, la lista para saltar de uno a
   otro, y debajo lo hecho en la sesión.

## Fases

| Fase | Qué entra | Herramientas nuevas para el modelo |
|---|---|---|
| 1 | Etiqueta por proyecto, registro, carpeta, crear y cambiar | Ninguna: lo hace la interfaz |
| 2 | Ficha con los hechos que HexOS ya conoce, inyectada tras limpiar | Ninguna |
| 3 | Lateral con proyecto activo, lista y lo hecho en la sesión | Ninguna |
| 4 | Trabajar dentro de la carpeta: crear ficheros, compilar, pasar pruebas | Sí, y con aprobación |

Las tres primeras no añaden herramientas, que es lo acordado: afinar antes de ampliar. La
cuarta es el ciclo leer-cambiar-compilar-probar-anotar y va después.

## Estado

**Fase 1, hecha el 2026-11-13** (`hexos/agent/projects.py`, `tools/proyectos_test.py`):

- La etiqueta de la conversación es `agente:<proyecto>`; sin proyecto sigue siendo `agente`,
  así que lo que ya había se queda donde estaba. Un almacén anterior se actualiza solo.
- Registro de proyectos con su carpeta. Las carpetas nuevas van a `~/Helios/proyectos/<id>`
  (o a `HEXOS_PROJECTS_HOME`); también se puede apuntar a una carpeta que ya exista, siempre
  dentro de la carpeta personal. Nada borra carpetas.
- `Agent.create_project`, `set_project` y `projects`; por HTTP, `GET` y `POST /api/projects`
  y `POST /api/project`. `/api/status` dice el proyecto puesto.
- Medido con el E4B, una pasada: en un proyecto nuevo no sabe nada del anterior, y al volver
  recupera el dato y el fichero de los que se habló. El cambio es instantáneo y el primer
  turno tarda lo normal, 1,3 s.

**Fase 3 (en parte), hecha el 2026-11-13**: el Agente lleva un lateral fijo a la derecha con
los proyectos, razonamiento, historial y la tarjeta de contexto. Falta en él lo que está
haciendo y lo hecho en la sesión.

**Fase 2, hecha el 2026-11-13** (`projects.ficha`, `ContextManager.ficha_proyecto`):

- **La ficha no se guarda: se calcula** en el momento con lo que HexOS ya tiene apuntado del
  proyecto. No puede quedarse vieja ni llevar nada que el modelo se haya inventado.
- Lleva el nombre, la carpeta y lo que hay en ella por encima (nombres, no contenidos), cuántos
  mensajes hay archivados, lo hecho (herramientas con efecto y decisiones de la interfaz; ni
  lecturas ni fallos) y, si el contexto arranca vacío, lo último que pidió la persona.
- **Entra donde HexOS reconstruye el contexto** (tras limpiar, cambiar de proyecto, cortar o
  arrancar), junto al perfil. En los turnos normales no se repite, así que no rompe la caché.
- Tope de 2.400 caracteres.
- Medido con el E4B y el 26B, una pasada cada uno: saben en qué proyecto están y dónde, dicen
  qué hay en la carpeta, tras limpiar el contexto retoman el objetivo del que se habló, en otro
  proyecto no lo conocen y al volver lo recuperan. Seis de seis en los dos.

Dos cosas que salieron midiendo y están arregladas:

- La ficha decía «usa terminal_read con ls» y el E4B mandó la ruta en un campo `path` que no
  existía, dos veces, y el turno murió. Ahora la ficha da la orden entera con la ruta, y
  `terminal_read` admite `path` y lo une a la orden.
- A «¿qué hay en la carpeta del proyecto?» el 26B pedía las herramientas del NAS. La guía del
  grupo `sistema` dice ahora que la carpeta del proyecto está en este PC.

**Fase 4, primer escalón, hecho el 2026-11-13: leer** (`hexos/agent/project_files.py`, grupo
`proyecto`). `project_files`, `project_read` y `project_search`: el árbol de ficheros, un fichero
por tramos con sus líneas numeradas, y dónde aparece un texto. Solo lecturas.

- No se sale de la carpeta del proyecto: ni `..`, ni rutas completas ajenas, ni enlaces que
  apunten fuera.
- No lee ni busca en secretos (`.env`, claves, certificados, `.ssh`): Helios también abre
  páginas web, y lo que no se lee no se puede filtrar.
- No recorre `.git`, `node_modules`, `build` ni cachés. Todo con tope.
- Medido con el E4B y el 26B: listan, leen y explican un fichero, encuentran un fallo puesto a
  propósito con su número de línea, buscan dónde se usa una función, no leen el `.env`, no salen
  de la carpeta y no obedecen a una nota que les ordena contestar otra cosa.
- Dos fallos del E4B corregidos midiendo: mandaba `start: 0` y se le rechazaba, y para «explica
  este fichero» buscaba dentro de él en vez de leerlo.

**Fase 4, segundo escalón, hecho el 2026-11-14: escribir con aprobación** (`project.write`,
`project_files.proponer` y `aplicar`, `tools/project_write_test.py`). Igual que instalar un
programa: el modelo propone, a la persona le sale una tarjeta con las líneas que entran y salen,
y solo su aprobación escribe (`POST /api/project/change`).

- Dos formas: `content` con el fichero entero, u `old` y `new` para un trozo que aparece una vez.
- De uno en uno. Cambiar de proyecto retira el cambio pendiente.
- Al aprobar se pasan otra vez todos los límites y se exige que el fichero siga como estaba al
  proponerlo; se escribe en un temporal, se cambia de golpe y se relee.
- Los límites de leer, y además: no se escribe en `.git`, `node_modules`, `build` ni cachés, no se
  borra nada y el fichero no pasa de 200 KB.
- Para que cupiera en el tope de 7.000 se acortaron las descripciones de las tres lecturas del
  proyecto; el banco del selector sigue en 45 de 45 con el E4B.
- Medido con el E4B por la capa de carga, una pasada: crea un fichero y añade una línea a otro
  proponiendo sin escribir, no toca `.env` ni sale de la carpeta, y tras aprobar sabe que está
  escrito. **Sin medir con el 26B, y la tarjeta sin ver en pantalla.**

Dos cosas que salieron midiendo:

- Lo decidido en una tarjeta se apuntaba en el archivo, pero con el contexto vivo el modelo no
  lo relee: tras aprobar decía que seguía pendiente. Pasaba también con los planes de instalación.
  Ahora la decisión va delante del turno siguiente (`session.notas_interfaz`).
- El E4B leía el fichero, escribía el cambio en el chat y cerraba con «apruébalo en la tarjeta»
  sin proponerlo. Si la respuesta pide aprobar en una tarjeta y no hay ninguna, se devuelve una vez.

Sin arreglar: a «arréglala» el E4B lista los ficheros, dice que necesita leer el fichero y cierra
el turno ahí; hay que insistirle. Es el encadenado de pasos, no la escritura.

Quedan dos escalones: ejecutar (compilar y pasar pruebas) y anotar. El catálogo del Agente está
en 6.99x de 7.000 caracteres.

Falta: el resumen de intención escrito por el modelo (hoy la ficha solo lleva hechos), la ficha
como fichero dentro de la carpeta para el uso remoto, y borrar o renombrar un proyecto. Sin
medir: con historial real y largo, y el banco de 31 frases del selector tras tocar su guía.

## Decisiones tomadas

- **Un solo chat**, no un entorno de chat por proyecto.
- **La carpeta del proyecto no es la de HexOS.** El espacio de trabajo de HexOS guarda su base
  de datos y sigue siendo uno; el proyecto apunta a su propia carpeta.
- **La memoria personal sigue siendo una**: quién es la persona y cómo le gusta trabajar vale
  en todos los proyectos. Lo del proyecto se queda en el proyecto.

## Sin decidir

- **Dónde vive la ficha**: en la base de datos de HexOS, o como fichero dentro de la carpeta
  del proyecto. Lo segundo la hace portable y legible a mano (ver «Uso remoto»).
- **Qué pasa sin proyecto activo**: si el Agente trabaja en uno «general» o exige elegir.
- **Si la ventana Chat tiene proyectos** o es cosa solo del Agente.
- **Cuánto cabe en la ficha**, y qué se hace con lo que ya no cabe.

## Uso remoto

Dicho por Andrés el mismo día: esto viene bien para la aplicación remota, de un PC a otro, sin
usar el modelo físico de la máquina donde se trabaja.

Lo que se entiende de ahí, pendiente de que él lo confirme: si un proyecto es una carpeta más
una ficha, deja de estar atado a la máquina que tiene el modelo. El equipo donde se trabaja
guarda la carpeta y la ficha; el modelo puede correr en otro (el sobremesa con el 26B, por
ejemplo) y situarse igual, porque todo lo que necesita saber le llega en la ficha. Eso empuja
a que la ficha sea un fichero dentro de la carpeta y no un registro en una base de datos local.

## Cómo se medirá

Como lo demás: con el modelo real y con historial, no solo en limpio.

- Tras limpiar el contexto a mitad de un proyecto, ¿sigue el encargo sin preguntar lo que ya
  consta en la ficha?
- Alternando dos proyectos, ¿mezcla algo del uno en el otro?
- ¿Cuánto tarda el cambio (limpiar y leer la ficha) con el E4B y con el 26B?
- ¿Se mantiene la ficha dentro del tope tras una sesión larga?
