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

Falta: no hay nada en la interfaz todavía (fase 3), no hay ficha (fase 2: hoy al volver lee el
archivo del proyecto, no un resumen), y no se puede borrar ni renombrar un proyecto.

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
