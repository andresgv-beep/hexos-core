# Contexto separado del diálogo y recuperación local

2026-09-12. Seguimiento de la captura donde «qué tal va todo» provocaba un volcado
del encargo antiguo, «qué quiere decir eso» repetía su ID y «vale» seguía explicándolo.

## Qué se corrigió

La petición del usuario estaba al final de un mensaje que contenía perfil, estado,
referencias y citas. Eso introducía antecedentes artificiales para «eso» y daba
protagonismo al estado del trabajo incluso en una charla.

La ruta nativa ahora separa:

- Política del agente y referencias de contexto, marcadas como datos.
- Los dos últimos intercambios de conversación, con sus roles y herramientas reales
  (ampliado tras el fallo de aceptación descrito en `RED_LOCAL_LECTURA.md`).
- La petición actual como mensaje propio. Si el turno anterior tuvo una respuesta
  de formato inválido, se conserva el antecedente de la petición sin responder;
  no se reintroduce aquella salida inválida como si fuera una respuesta válida.
- Hasta ocho citas recientes escritas por el usuario, recuperadas directamente
  del historial, con un presupuesto de 4000 caracteres. No se extraen nombres con
  reglas ni se convierten respuestas del modelo en hechos de la persona.
- El contenido del resultado/informe activo, leído del almacén local como fuente
  histórica. Las referencias internas no se presentan como el mensaje del usuario.

El estado completo del encargo deja de encabezar cada petición. Las referencias
necesarias para guardar o recuperar se mantienen fuera del diálogo. Las herramientas
del último intercambio se reconstruyen con bloques nativos; hay un presupuesto
adicional de 4000 caracteres y extractos explícitos para resultados grandes.

Las lecturas previas de resultados e informes se devuelven en `context_sources`.
`tools` sigue registrando las llamadas solicitadas por el modelo. Así se distingue
una lectura de contexto hecha por HexOS de una decisión de herramientas del modelo.
Los textos de estos recursos se limitan a 1600 caracteres por recurso y señalan
`partial` cuando hace falta consultar el contenido completo.

Limpiar contexto reinicia la ventana del diálogo y el motor, pero las citas del
usuario y los recursos guardados siguen siendo recuperables automáticamente. Es
recuperación de datos existentes, no escritura ni confirmación de memoria en HERA.
Para contenido anterior a esas citas siguen disponibles las herramientas de historial.

`result.get` admite ahora omitir `id`: recupera el resultado del encargo activo.
La lectura no recalcula, crea ni guarda otro resultado. Las instrucciones generales
se simplificaron para distinguir conversación, consulta y ejecución; no hay reglas
de código que clasifiquen frases como «vale» o «qué tal».

## Evidencia final

- 47 pruebas Python pasan, incluyendo fuentes de contexto sin recalcular, citas
  del usuario tras reset, conservación de roles, recuperación del resultado activo
  sin ID y los controles previos de protocolo y presupuesto.
- La última corrida de conversación contiene 18 turnos: cinco replays históricos,
  la secuencia social de la captura, vuelta al resultado antiguo y el recorrido de
  nombre/corrección/cambio de tema/reinicio. Las comprobaciones automáticas terminan
  sin errores; las respuestas se revisaron además manualmente.
- El replay de «qué quiere decir eso» responde con el trabajo pendiente, «Revisar
  espacio libre del NAS», en lugar del identificador. «Vale» recibe «De acuerdo».
  La secuencia social nueva no introduce el informe ni expone sus IDs.
- Volver al resultado antiguo ejecutó `result.get` sin argumentos y comunicó el
  contenido del resultado original. No generó uno nuevo.
- Pasa resumir → guardar → reset → recuperar el mismo informe, con comprobación de
  identidad y contenido de la fuente. El test admite la lectura real de contexto
  de `report.get` además de una llamada solicitada por el modelo; no confunde ambas.
- Prueba adicional: después de terminar el trabajo en el almacén temporal, pedir
  un resumen actualizado ejecuta `procedure.run` y responde «No hay trabajos
  pendientes», aunque exista un informe histórico con aquel trabajo pendiente.
- También pasan petición ambigua → aclaración e ideas sin guardar informes.
- Comparación final con el snapshot de entrada: conversación, eventos de herramientas,
  resultados, informes, estado y trabajos originales idénticos. Sin dispositivos ni commit.

Evidencia privada en `runtime/logs/conversation-focus-fix/`: `tenth.json` contiene
los 18 turnos finales; `fresh-procedures.log` incluye la prueba de estado actualizado.
Las corridas anteriores fallidas se conservan, no se cuentan como resultados buenos.

## Límites observados

### Seguimiento: iniciativa y comprobaciones

Se reforzó la política nativa: una consulta solicitada incluye comunicar su
resultado sin otra confirmación; el estado de sistemas requiere observaciones
actuales. El catálogo de `procedure.run` aclara que `pending_report` resume fichas,
no ejecuta sus trabajos ni inspecciona dispositivos. No se han añadido conexiones.

La corrida privada `initiative.json` amplía la aceptación a 23 turnos con el
recorrido de la captura. Ante «como estan los sistemas?» responde «Aún no he
comprobado el estado de los sistemas». Ante «mi nas» y «si revisalo» comunica la
falta de acceso sin presentar la ficha pendiente como revisión realizada.
Estos cinco turnos se inspeccionan manualmente: el código de salida del script
no certifica su calidad semántica. El último «si», después del bloqueo, provoca
una pregunta genérica innecesaria. Siguen apareciendo ofertas automáticas y
frases artificiales. Esta mejora de veracidad no resuelve toda la naturalidad.

Las comprobaciones de nombre son de presencia del dato, no una certificación
semántica. En el replay antiguo «te he preguntado», la respuesta final incluye
Andrés, pero aún tiene una introducción innecesaria sobre memoria y usa «tu creador»
con una perspectiva incorrecta. También persisten ofertas automáticas de ayuda.
Por tanto, no se declara estabilizada toda la conversación ni perfecto el estilo.

Se comparó activar pensamiento; no corrigió por sí solo los problemas de continuidad
y recuperación. Existe `--native-thinking` para continuar esa evaluación, pero el
servidor queda sin ese modo activado. El adaptador separa el canal de pensamiento
de la respuesta visible y distingue las continuaciones con canal abierto.

La autorización independiente de escrituras ordinarias, contexto global por tokens,
KV incremental, visión y cancelación siguen pendientes. Esta corrección no añade
permisos para dispositivos ni herramientas nuevas de escritura.
