# Auditoría del agente de Hexos · 19 de noviembre de 2026

Rama `grupos-de-herramientas`, revisión `bf30c1b89c`. Se evaluaron el agente Python, sus dos ventanas y el runtime nativo Héctor con los HNF configurados de Gemma 4 26B y Qwen3.6 35B. Se utilizaron perfiles HERA y espacios de trabajo temporales. Las mediciones iniciales corresponden a esa revisión.

## Correcciones implementadas y comprobación posterior

Gemma 4 26B y Qwen3.6 35B guardaron el código `SC-8174` en una nota titulada «Serie Cobre» tanto en Chat como en Agente. Cada turno dejó exactamente una nota en SQLite y tres llamadas correctas en la traza, en el orden de búsqueda, lectura y guardado. Para ello se compartió el grupo de notas entre ambas ventanas y se conservó su selección en las peticiones compuestas. En Agente, ya con el modelo cargado, la cadena tardó 3,6 s con Gemma y 25,6 s con Qwen en esta ejecución.

Ambos modelos recuperaron **Teruel** después de limpiar el contexto. En cada base de prueba constan las escrituras de Cuenca y Teruel asociadas a sus respectivos turnos. Con la orden de nota de 56 caracteres y con la misma orden al final del texto de 1.421, ambos selectores devolvieron `notas`. La actualización automática acepta afirmaciones explícitas de ciudad, nombre y apodo. Si el cambio es ambiguo, se conserva el valor vigente y se indica el conflicto.

Las pruebas de regresión cubren la continuidad de una respuesta simulada que llena la ventana del motor, los traspasos anteriores al cambio, la lectura por ID y el encargo activo al alternar proyectos. La prueba del corte usa el envoltorio de producción. Una prueba adicional verifica que, si después de leer la fuente sigue faltando la nota pedida, Hexos registra un cierre parcial.

La validación automatizada pasó 672 pruebas Python de la selección ejecutada y las 150 de interfaz. Una prueba Python quedó omitida por depender de una plantilla local antigua. `make test` acabó sin interacción al compilar y ejecutar los componentes C en una copia temporal. La prueba de integridad HNF-EXT verificó el bloque después de guardarlo y recargarlo.

En el banco ampliado a 52 frases, Gemma incluyó los grupos necesarios en 52/52 y Qwen en 51/52. Ambos coincidieron exactamente con las etiquetas en 51/52. Gemma ofreció también el grupo de proyecto al leer un manual y guardarlo en una nota. Qwen ofreció notas al buscar unos planos en la web. El selector puede declarar herramientas de más incluso cuando el encargo final se ejecuta correctamente.

Los apartados siguientes conservan las mediciones y recomendaciones de la revisión inicial para poder comparar los resultados.

## Qué recibe el modelo

El prompt de producción se construye en varias etapas. La ventana selecciona el texto de sistema. Una inferencia auxiliar clasifica el mensaje y elige grupos. Hexos incorpora las herramientas de esos grupos a la plantilla del modelo, conserva grupos usados recientemente y añade el historial, el perfil o los resultados que correspondan. Cada llamada vuelve al bucle con sus argumentos validados y su resultado. La respuesta final puede incorporar fuentes o confirmaciones escritas por el propio agente. Al evaluar una respuesta importa distinguir el texto generado, el estado persistido y las acciones de Hexos. [Sistema nativo](../hexos/agent/native.py) · [Selección y contexto](../hexos/agent/chat_backend/context.py) · [Cierre del turno](../hexos/agent/chat_backend/finalization.py)

En esta revisión hay 62 herramientas que pueden ofrecerse al modelo. El núcleo de Chat declara 7 y llega a 26 con todos sus grupos. Agente parte de 10 y llega a 43. El catálogo por grupos conserva margen para el diálogo y ofrece un mecanismo de respaldo si el selector devuelve una salida inválida. Una lista vacía es una decisión válida y no activa ese respaldo. Esto importa cuando el selector pierde el encargo por truncamiento. [Catálogo y ventanas](../hexos/agent/catalog.py) · [Selector](../hexos/agent/tool_groups.py)

## Pruebas con los dos modelos

La matriz muestra una ejecución por modelo y escenario. La prueba del nombre usó el adaptador nativo directo. Las de la ciudad y del manual pasaron por la misma capa `ModelLifecycle` que usa el servidor. La fuente del manual fue local y controlada. El resultado de búsqueda omitía el código y la página abierta contenía `SC-8174`. Para contar una tarea como completada comprobé el título y el contenido de la nota en SQLite. La prueba aísla el encadenamiento de la disponibilidad de un buscador público.

| Escenario y criterio | Gemma 4 26B | Qwen3.6 35B |
|---|---|---|
| Guardar «Lidia», limpiar el contexto y recuperar el nombre | HERA guardó Lidia y el chat respondió Lidia | Mismo resultado. Hizo una consulta adicional al perfil en el primer turno |
| Sustituir la ciudad por Teruel, limpiar y recuperar | HERA conservó Cuenca y respondió Cuenca | HERA conservó Cuenca y respondió Cuenca |
| Chat · buscar el manual, abrirlo y crear la nota | Tres llamadas. Una nota con el título y código correctos | Tres llamadas. Una nota con el título y código correctos |
| Agente · el mismo encargo en un espacio nuevo | Buscó y leyó el código. Cero notas | Buscó, leyó y consultó el estado general y el historial. Cero notas |
| Selector de Chat · misma orden de nota, corta y al final de un texto largo | Eligió `notas` en la corta y `[]` en la larga | Eligió `notas` en la corta y `[]` en la larga |

La cadena de Chat fue `web.search → web.read → note.save` en ambos casos, sin reintentos de formato ni de contexto. El primer turno del proceso tardó 24,5 s con Gemma y 98,1 s con Qwen, incluida la carga bajo demanda. En Agente, ya con el modelo residente, fueron 3,3 s y 15,6 s, respectivamente, para tareas incompletas y con distinto número de llamadas. Son tiempos observados en este equipo, con una ejecución por condición. Las ventanas configuradas fueron 40.960 y 50.176 tokens, respectivamente, con el modo de pensamiento desactivado en estos ensayos.

### Banco del selector

Ejecuté las 51 frases etiquetadas de `tools/banco_selector.py` una vez por modelo, con su plantilla y ventana de contexto configuradas. Ambos eligieron exactamente los grupos esperados en **50/51** casos. En Agente acertaron **40/40** y en Chat **10/11**. El único desacuerdo fue idéntico. Ante «busca en la web los planos del Apple 1», ambos añadieron `descargas`. La búsqueda ya pertenece al núcleo y la frase no pide descargar. Todas las salidas fueron interpretables. Esta medición evalúa la selección con mensajes aislados. La prueba del encargo al final de un texto largo fue adicional a las 51 frases. [Casos y criterio de puntuación](../tools/banco_selector.py)

## Hallazgos y cambios propuestos

### 1. La memoria puede quedarse con un dato que la persona acaba de corregir

La prueba parte de un perfil vacío. Después de «Vivo en Cuenca» envié «Me he mudado. Ahora vivo en Teruel», limpié el contexto conversacional y pregunté «¿En qué ciudad vivo?». Con ambos modelos, la extracción produjo exactamente `yo/ciudad = Teruel`. La regla de actualización exige que el mensaje nuevo incluya también el valor anterior para reemplazarlo automáticamente. El rechazo se descarta durante la extracción y HERA conserva Cuenca. Una respuesta empática a la mudanza hace difícil que la persona advierta el problema. [Regla de actualización y tratamiento de conflictos](../hexos/agent/chat_backend/memory.py)

Permitiría reemplazar atributos de un solo valor ante una actualización explícita del mismo sujeto, conservando ambas citas en HERA. Para un cambio ambiguo, devolvería el conflicto a la conversación. El criterio de aceptación es releer el perfil después de reiniciar o limpiar el contexto y obtener la nueva ciudad. «Mi hermana vive en Teruel» debe conservar la ciudad de la persona.

La escritura automática presenta además un problema de trazabilidad. En los dos ensayos del nombre, HERA guardó `yo/nombre = Lidia` y la respuesta del turno incluyó `profile.remember`, pero ese evento faltaba en `tool_events` al reabrir SQLite. La extracción sí figuraba en `generation_events`. Conviene registrar el desenlace del guardado con su identificador de turno, tanto para reconstruir el historial como para distinguir guardado, ausencia de cambios y conflicto. [Extracción](../hexos/agent/chat_backend/memory.py) · [Persistencia del cierre](../hexos/agent/chat_backend/finalization.py)

### 2. Las ventanas separan el diálogo mejor que la evidencia de las herramientas

El historial reciente y la búsqueda consultan la vista de la ventana y proyecto actuales. Sin embargo, al recortar una conversación larga, el traspaso toma la última operación y el último listado de toda la tabla de eventos. El texto del traspaso vuelve al prompt con resultados, rutas y referencias. Por inspección, un cambio reciente de ventana o proyecto puede atribuir evidencia ajena al encargo que se retoma. La lectura de un mensaje por ID también consulta la tabla global. [Traspaso y último listado](../hexos/agent/chat_backend/context.py) · [Lectura de historial](../hexos/agent/continuity.py) · [Ámbito de la conversación](../hexos/agent/chat_backend/persistence.py)

Aplicaría la misma vista de conversación a esas lecturas. Una prueba de aceptación debe alternar dos proyectos, forzar un recorte y comprobar que cada traspaso conserva sus propias rutas e identificadores. El perfil personal puede seguir siendo compartido según el diseño actual.

### 3. La continuación de una respuesta larga funciona en el adaptador directo y se pierde en el servicio

El coordinador asigna el encargo y sus evidencias a `output_checkpoint` para retomar una respuesta cuando se llena el contexto. En producción esa asignación queda en `ModelLifecycle`. La generación se delega en un `NativeRuntime` que consulta su propio atributo. Reutilicé el motor simulado de la prueba de continuidad y la misma secuencia de dos fragmentos. El adaptador directo emitió «Primer párrafo. Fin.» en dos envíos. Al envolverlo en `ModelLifecycle`, terminó con `context_full` tras el primero. Este ensayo simula el límite del motor y reproduce el comportamiento de las dos clases Python. [Coordinador](../hexos/agent/chat_backend/recovery.py) · [Capa de servicio](../hexos/agent/chat_backend/model_lifecycle.py) · [Continuación nativa](../hexos/agent/native.py) · [Prueba existente](../tools/output_continuity_test.py)

Pasaría el encargo y sus evidencias explícitamente a la generación bajo el bloqueo del runtime. Añadiría la variante con la capa de servicio a la prueba existente. Debe terminar el texto y conservar una sola ejecución de las herramientas previas.

### 4. El selector puede perder la orden al final de un texto pegado

El selector recibe los primeros 1.200 caracteres del mensaje y los primeros 600 de la respuesta anterior. El contexto principal ya dispone de una estrategia para preservar principio y final, pero la elección de grupos ocurre antes. En la muestra controlada, la orden completa tenía 56 caracteres. Al anteponerle un párrafo repetido hasta llegar a 1.421, quedó por completo fuera de lo que recibió el selector. Una respuesta válida `[]` puede dejar fuera la herramienta desde el comienzo. [Construcción del prompt del selector](../hexos/agent/tool_groups.py) · [Orden de preparación del turno](../hexos/agent/chat_backend/context.py)

Dentro del mismo presupuesto guardaría parte del comienzo y el final, con una marca de omisión. Mediría el efecto en peticiones al principio, al final y con dos intenciones. En las dos ventanas comprobaría tanto el grupo seleccionado como el resultado final de la tarea.

### 5. Una cadena necesita una condición de cierre que cubra todo el encargo

El agente ya valida los argumentos, devuelve los resultados al modelo y registra las operaciones. También evita repetir determinadas llamadas y conserva evidencia tras un recorte. Lo más débil es detectar que una petición con dos verbos solo se ha cumplido a medias. «Busca el dato y guárdalo» termina cuando existe la nota con el dato leído. Una URL correcta acredita la lectura, pero todavía queda una escritura pendiente. [Bucle del turno](../hexos/agent/chat_backend/turn.py) · [Ejecutor](../hexos/agent/chat_backend/tools.py) · [Registro de pasos](../hexos/agent/chat_backend/ledger.py)

El catálogo ofrece el grupo de notas en Chat. Si el producto quiere permitir esa cadena también en Agente, ofrecería la capacidad de notas al pedirla sin cargar el catálogo entero. Si la separación es deliberada, la interfaz puede indicar que el último paso está en Chat y trasladar el dato y la fuente. En ambos diseños, el cierre debe indicar qué paso quedó pendiente sin pedir otra vez permiso para una acción que ya se pidió.

## Coste del prompt

En el turno «Me llamo Lidia», la primera generación principal procesó 1.306 tokens de entrada con Gemma y 1.676 con Qwen, con cero tokens reutilizados en ambas. La diferencia incluye plantilla y tokenización. Tras limpiar el contexto, los dos contestaron «Lidia» a «¿Cómo me llamo? Responde solo con el nombre». En ambos casos se lanzó además una extracción de hechos que devolvió un array vacío. La expresión que busca «me llamo» también casa con esa pregunta. Separar las preguntas de recuerdo de las afirmaciones explícitas ahorraría esa generación y mantendría la extracción en mensajes mixtos como «¿te acuerdas de mí? Me llamo Lidia». [Filtro de memoria](../hexos/agent/chat_backend/memory.py) · [Extracción auxiliar](../hexos/agent/native.py)

Antes de ampliar el texto fijo de Chat, mediría por separado cuántas llamadas requieren el selector, el clasificador de tono, la búsqueda y el extractor. El sistema pide buscar en la web incluso para explicar un hecho estable. Un A/B con saludos, explicaciones estables y preguntas de actualidad permitiría medir el efecto sobre la fidelidad, las lecturas de fuentes y el tiempo hasta una respuesta útil. [Prompt de Chat](../hexos/agent/native.py) · [Clasificador de tono](../hexos/agent/registro.py)

El efecto visual de Chat también consumió atención en una respuesta real. Al preguntarle por la ciudad, Qwen incluyó `[[matrix]]` en mitad de la respuesta, aunque la persona no lo pidió y el propio prompt explica que la marca solo actúa en la primera línea. Probaría a ofrecer esa instrucción cuando se solicite el efecto y mediría la aparición espontánea de la marca en un conjunto de conversaciones corrientes.

## Calidad del proyecto y de sus pruebas

Conservaría el catálogo tipado, la separación entre transporte y ejecutores, las plantillas nativas por familia de modelo, las citas de usuario en HERA y la comprobación del estado real de los artefactos. Permiten localizar dónde se pierde un resultado incluso cuando el modelo produce texto convincente. El coste de mantenimiento se concentra en las reglas repartidas entre el prompt, el selector y la recuperación. Una misma intención puede tener tres tratamientos según la ventana, la redacción y la capa que se instancie en el test.

- En 21 módulos Python seleccionados de agente, memoria, contexto, grupos, protocolos y continuidad pasaron 295 pruebas y se omitió una que requiere una plantilla local del antiguo Gemma 12B.
- La interfaz pasó sus 150 pruebas de `npm test`.
- En una copia limpia compiló la parte C. El objetivo `make test` abrió la interfaz interactiva al llamar a `hexos --help`. Se cerró el proceso temporal para que el objetivo siguiera. La prueba de política pasó y Memory Core terminó. La demostración HNF-EXT imprimió `Checksum mismatch` al verificar el bloque modificado y terminó con código cero. Esto identifica una carencia del criterio de prueba. La recarga posterior del fichero funcionó. [Objetivo de pruebas](../Makefile) · [Demostración HNF-EXT](../hnf_ext/tools/hnf_ext_test.c)
- El banco de cadenas devuelve resultados web bajo `results`, mientras que la herramienta real y la recuperación usan `items`. Además, la búsqueda automática llama directamente a `web.search`, por lo que sustituir solo `AgentDependencies.web_search` deja una vía fuera de la simulación. El ensayo controlado del manual usó el formato de producción y sustituyó ambas vías. [Banco de cadenas](../tools/banco_cadenas.py) · [Búsqueda real](../hexos/agent/web.py) · [Búsqueda automática](../hexos/agent/chat_backend/memory.py)

## Orden de trabajo recomendado

| Prioridad | Intervención | Criterio para darla por terminada |
|---|---|---|
| Primera | Corregir la actualización de hechos y el ámbito del traspaso | Ambos modelos recuperan la ciudad nueva tras limpiar el contexto. El archivo y el traspaso respetan la ventana y el proyecto |
| Primera | Enviar el punto de continuación al motor usado por el servicio | Una respuesta larga continúa tras el corte simulado y las herramientas anteriores se ejecutan una sola vez |
| Siguiente | Preservar el final del encargo en el selector y resolver las cadenas entre ventanas | La orden al final de un texto elige el grupo correcto. Una petición de nota deja el artefacto o identifica la ventana que puede terminarla |
| Siguiente | Hacer repetible el banco de producción | La prueba usa los mismos adaptadores y esquemas que el servidor. Se comprueban resultado persistido, llamadas adicionales, reintentos y latencia con el modelo ya residente |

Para comparar modelos como opción predeterminada, repetiría esas tareas con formulaciones nuevas, varios turnos y entrada en frío y en caliente por separado. El banco de selección ya permite comparar cambios del texto de los grupos por revisión. Conviene complementarlo con pruebas de resultado final que no formen parte de las frases usadas para afinar la guía. [Banco del selector](../tools/banco_selector.py) · [Banco de cadenas](../tools/banco_cadenas.py)
