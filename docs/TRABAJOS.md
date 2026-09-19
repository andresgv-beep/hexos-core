# Fichas de trabajo del agente doméstico

El almacén Python/SQLite vive en `hexos/agent/work.py` y lo utiliza el agente
HTTP actual (`hexos/agent/chat_backend/`), conectado a React. El servidor C
`hexos_serve` se conserva como otra ruta; no es el backend de esta interfaz.
El almacén no necesita GPU. [Estado actualizado](../IMPLEMENTATION_STATUS.md).

## Datos y responsabilidad

Cada ficha guarda ID, petición original y referencia al turno, fechas UTC de
creación/actualización, tipo, ámbito, etiquetas, estado, resumen, referencias,
siguiente paso y revisión. El diario de cambios conserva quién cambió qué.

La aplicación crea la ficha desde una petición real. El modelo puede proponer
`kind`, `scope`, `tags` y una justificación. La propuesta queda separada de la
clasificación aplicada. El usuario o la aplicación aplica una clasificación;
una propuesta posterior del modelo no pisa esa decisión. Estado, resultado y
siguiente paso los registra el llamante de confianza, a partir del trabajo real.
El resumen es un registro operativo, no una prueba de ejecución de comandos.

Tipos: consulta, diagnostico, mantenimiento, documento, codigo.
Estados: pendiente, en_curso, bloqueado, terminado.
Ámbitos y etiquetas son abiertos: NAS, casa o nombre de proyecto, por ejemplo.
No se crea memoria personal, se ejecuta SSH ni se concede autoridad a través de
una clasificación. Las referencias son identificadores; el registro no las abre.

## Uso desde la raíz del repositorio

Elegir una raíz de trabajo explícita (no modifica el perfil de HERA):

```sh
python3 -m hexos.agent.work --workspace /ruta/al/espacio-de-trabajo
```

Enviar un único objeto JSON por stdin; responde con `ok` y `result` o `error`.
Código de salida 1 en rechazo. Operaciones:

```json
{"op":"create","title":"Revisar disco del NAS","request":"¿Cuánto espacio queda?","source_ref":"turn:1"}
{"op":"classify","id":"ID_DEVUELTO","revision":1,"kind":"diagnostico","scope":"NAS","tags":["disco"],"reason":"La petición consulta el almacenamiento"}
{"op":"list","scope":"NAS","since":"2026-09-12","until":"2026-09-12"}
{"op":"get","id":"ID_DEVUELTO"}
{"op":"history","id":"ID_DEVUELTO"}
{"op":"update","id":"ID_DEVUELTO","revision":2,"state":"bloqueado","next_step":"Falta conexión al NAS","refs":[]}
```

`--actor model` crea una propuesta de clasificación, no una aplicada. El proceso
que conecte el LLM debe fijar ese actor; nunca permitir que el modelo suministre
argumentos CLI ni seleccione `user`/`system`. Las escrituras exigen la revisión
vigente para evitar sobrescribir cambios concurrentes. Campos desconocidos y
claves JSON repetidas se rechazan. La lista devuelve hasta 100 fichas compactas;
las fechas filtran por última actualización, con extremos inclusivos UTC.

## Comprobación del almacén

`python3 tools/work_test.py` comprueba reapertura, propuesta/corrección,
historial, búsqueda por fecha/ámbito, conflictos y rechazos sin escritura parcial.

## Ruta JSON de pruebas y documentos largos

Desde la raíz del repo:

```sh
python3 -m hexos.agent.chat --workspace runtime/workspace \
  --runtime /ruta/Hector-engine/build/helios_runtime --model /ruta/modelo.hnf
```

Ese comando, sin `--native-template`, selecciona decisiones JSON y el panel
HTML de compatibilidad en `http://127.0.0.1:8080/`. La interfaz React conectada
está en 3000; para la ruta nativa seguir el [arranque actual](../README.md).
El catálogo actual ya incorpora SSH y web; las imágenes requieren el adaptador
nativo y un HNF visual. Voz sigue pendiente. La clasificación JSON no tiene
paridad total en nativo. No se certifica cualquier clase de encargo.

El mensaje se guarda íntegro hasta 8 MiB UTF-8; los mayores se rechazan. Sobre
6000 caracteres se registra además como documento con SHA256 y se entrega una
vista parcial al modelo, que puede usar document.read/document.search. Guardar
todo no implica que todo entre en contexto ni que el modelo lo haya leído.
Estos límites corresponden a esta ruta, no arreglan el `/pegar` legacy.

## Ciclo de trabajo v2: resumir, guardar y recuperar

`catalog.py` define nombres, argumentos requeridos/opcionales, tipos y efectos.
Su representación alimenta el prompt y su validador recibe cada llamada. Los
módulos siguen comprobando reglas de dominio (rangos, existencia de ids, etc.).
No hay dos catálogos de herramientas mantenidos a mano.

`workflow.py` separa:

- `procedure.run` con `id: pending_report`: lee pendientes y registra una
  instantánea operativa en agent_results. No escribe agent_reports.
- `report.save` con result_id: guarda esa instantánea, sin recalcularla. Es
  idempotente por resultado y no modifica las fichas originales.
- `result.get`: recupera un resultado operativo.
- `report.list/get`: recupera informes existentes sin crear otros.

Los informes antiguos (v1) siguen legibles. No se migran ni borran. La v2
reemplaza la combinación anterior «consultar y guardar» por dos operaciones.
Los resultados operativos sí persisten aunque no se pidan informes: son el estado
local del encargo, no un archivo que el usuario haya solicitado guardar.

El encargo activo conserva fuente, estado y referencias a resultado/informe.
Las decisiones del modelo distinguen herramienta, respuesta y aclaración. Una
aclaración registra su intención provisional y pregunta mediante task.focus;
no pasa a ser un hecho personal confirmado. La formulación de esa intención
sigue dependiendo del modelo y no está certificada para cualquier conversación.

El modelo selecciona acciones según la petición. El esquema verifica argumentos,
no demuestra que haya interpretado correctamente una autorización en lenguaje
natural. El catálogo actual sí tiene SSH y acciones remotas acotadas; validar
argumentos no concede autoridad adicional sobre un recurso.

«Limpiar contexto del modelo» resetea KV y establece un corte de historial para
inferencia, sin borrar conversación, documentos, trabajos o informes. Después,
el encargo aporta referencias y el contenido se recupera por herramienta.
La ruta JSON conserva ocho mensajes; la nativa conserva el bloque desde el
último corte con presupuesto y posición KV. El archivo puede consultarse con
herramientas de historial. No se promete contexto infinito; la búsqueda de
fichas usa los filtros definidos por el almacén.

Las llamadas y resultados quedan en tool_events. Se incorpora al siguiente turno
la última operación posterior al corte (hasta 4000 caracteres o metadatos). Los
contadores diagnostics revelan correcciones de JSON, esquema y recuperación.
Los límites actuales son diez iteraciones del bucle y seis eventos de traza
(`chat_backend/settings.py`); la recuperación tiene sus límites propios. Los
errores persistentes se muestran, no se convierten en éxito.

## Pruebas del recorrido

```sh
python3 tools/work_test.py
python3 tools/agent_chat_test.py
python3 tools/procedures_test.py
python3 tools/procedures_live_test.py --runtime /ruta/helios_runtime --model /ruta/modelo.hnf
```

La última requiere GPU libre y un almacén temporal: resumen sin guardar,
«guárdalo» sobre el mismo resultado, reset/reapertura, recuperación sin nuevas
escrituras, aclaración y petición de ideas sin crear fichas/informes.
`--inject-invalid-arguments` introduce un campo inválido para probar recuperación.
Los ensayos con Gemma E4B pasaron el recorrido principal; una recuperación
necesitó corregir el formato JSON. No implica autonomía general ni que todos los
turnos funcionen al primer intento. Las pruebas locales también comprueban que
cambiar una ficha antes de guardar no altera la instantánea que se guarda.
El ensayo de «solo dame ideas» no creó fichas ni informes, pero el modelo pidió
una aclaración innecesaria: la ausencia de escritura no certifica buena conducta.
