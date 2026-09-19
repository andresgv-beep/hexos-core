# Corrección del recorrido conversacional nativo

> **Documento histórico / evidencia de una fase.** Sus pendientes y pruebas
> describen ese corte, no el producto actual. [Estado vigente](../IMPLEMENTATION_STATUS.md)
> (revisado 2026-09-19).

2026-09-12. Cambios aplicados al chat experimental y comprobados con E4B local.
Sucede a AUDITORIA_CONVERSACION_NATIVA.md, que conserva los fallos anteriores.

Este documento describe el primer corte. El [seguimiento de contexto y foco](CONVERSACION_CONTEXTO_Y_FOCO.md)
actualiza la composición del diálogo, recuperación de citas y fuentes de resultados.

## Resultado comprobado

Los dos turnos del incidente, reconstruidos desde el snapshot privado en copias
temporales, responden «Te llamas Andrés.» sin llamadas ficticias ni reintentos.
El historial original, incluidas sus respuestas equivocadas, permanece en disco.
No hay nombres ni extracción de nombres mediante expresiones regulares en el
código del agente: el modelo interpreta las citas de la persona.

El recorrido nuevo con datos sintéticos hace lo siguiente:

1. «Me llamo Marta.» → «Te llamas Marta.»
2. Pregunta por el nombre → Marta.
3. Corrección a Elena → Elena.
4. Ideas para un inventario → dos ideas, sin herramientas.
5. Vuelta al nombre → Elena.
6. Consulta de procedimientos → llamada real y explicación de pending_report.
7. Limpiar contexto, cerrar el motor, cargarlo de nuevo y abrir otro Agent sobre
   el mismo almacén; preguntar el nombre → history.recent → Elena.
8. Preguntar por una ciudad que no se ha dicho → reconoce que falta ese dato.

El paso 7 necesitó un reintento: inicialmente emitió una pseudollamada. El sistema
la rechazó y obtuvo una llamada nativa nueva. No se presenta como acierto del
modelo al primer intento.

## Implementación

- **Contexto nativo con roles y procedencia**, en context.py. Hasta 16 mensajes,
  con 6000 caracteres de presupuesto de historial y extractos recuperables para
  mensajes largos. Las citas del usuario se presentan además separadas y en orden
  cronológico: las afirmaciones del asistente no se promocionan a hechos del
  usuario. Las pseudollamadas y respuestas vacías antiguas se sustituyen por un
  aviso solo en la entrada al modelo; el registro original no se altera.
- **Contexto y archivo diferenciados.** Tras reset, cuando el contexto está vacío,
  se indica que siguen existiendo mensajes archivados consultables. Un perfil
  HERA vacío no implica ausencia de información en la conversación.
- **Recuperación cronológica.** history.recent y history.search seleccionan los
  últimos 20 registros coincidentes y los entregan del más antiguo al más nuevo,
  con roles y `order: oldest_to_newest`. Antes, el nombre original quedaba después
  de su corrección en la respuesta de la herramienta.
- **Contrato compartido**, en decisions.py. Rechaza respuestas vacías y
  pseudollamadas aisladas a funciones conocidas. Permite explicaciones que
  mencionan funciones. No es un clasificador semántico universal.
- **Recuperación nativa acotada.** NativeSyntax participa del contrato de error.
  Hay un reintento por turno. Tras una pseudollamada, una generación nueva empieza
  con `<|tool_call>call:`; nombre y argumentos se generan de nuevo y se validan.
  Ese reintento solo puede solicitar lecturas, nunca escrituras. No se traduce ni
  ejecuta el pseudocódigo rechazado. Un corte por tokens no autoriza ejecución,
  aunque el texto parezca una llamada completa. Si persiste, se devuelve un error.
- **Presupuestos separados.** Seis herramientas y hasta diez decisiones para dejar
  margen a finalización y recuperaciones. Una séptima solicitud no se ejecuta.
- **Registro local**, en generation_events. Conserva prompt y hash, salida del
  motor, prefijo suministrado, salida reconstruida, terminación, tokens y tiempo.
  Distingue tokens prefijados de tokens emitidos. Vive en el almacén privado.

JSON conserva su montaje y ventana de ocho mensajes. Comparte el rechazo de
respuestas inválidas y el nuevo presupuesto. Héctor no se modificó en este trabajo:
se usa su puente preformateado existente.

## Validación

- 40 pruebas Python pasan. Las nuevas verifican rechazo y registro de fallos,
  recuperación acotada, separación de texto/ejecución, prohibición de escritura en
  la recuperación forzada, truncamientos, orden/procedencia y seis llamadas más
  respuesta, bloqueando una séptima.
- Diez turnos de aceptación real en la última corrida, incluidos los dos replays.
  Se comprueban errores y presencia del nombre esperado; respuestas y trazas se
  revisaron manualmente. No es una tasa estadística de fiabilidad.
- Pasa el recorrido real de informes: resumir → guardar → reset → recuperar el
  mismo informe sin recalcular; petición ambigua → aclaración; ideas sin guardar
  informes ni crear trabajos.
- Servidor restaurado en native-experimental. Comparación con el snapshot previo:
  conversation, tool_events, agent_reports, agent_state y jobs idénticos.
  La nueva tabla de trazas no altera los registros existentes.

Instrumentos: tools/conversation_test.py y tools/conversation_live_test.py.
Evidencia privada bajo runtime/logs/conversation-fix/: fourth.json y
procedures-final.log corresponden a la versión final. Se conservan las primeras
corridas fallidas para explicar qué motivó las correcciones.

## Límites abiertos

El dato personal se recupera del historial; no se escribe automáticamente en HERA.
Sigue pendiente la autorización independiente de report.save descrita en la
auditoría: restringir el reintento a lecturas no corrige las llamadas ordinarias.
Tampoco se implementó presupuesto global por tokens, KV incremental, visión,
cancelación ni clasificación nativa de trabajos.

El modelo sigue siendo variable. El contrato evita aceptar algunos fallos de
formato, pero no certifica toda afirmación factual de una respuesta libre. No se
han borrado errores previos ni declarado estable todo el agente por este recorrido.
