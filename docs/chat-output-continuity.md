# Continuidad de respuestas largas

El adaptador nativo mantiene bloques de 3.072 tokens, pero un corte
`max_tokens` ya no termina el turno con una excepción que pierde la respuesta.
Reenvía el prompt preformateado con la continuación exacta del asistente, sin
añadir mensajes del usuario ni volver a ejecutar herramientas anteriores.
Máximo: cuatro bloques (12.288 tokens de salida), sujeto al contexto disponible.
No se modifica el presupuesto de sesiones internas ni de extracción de memoria.

La salida en streaming es acumulativa entre bloques. Las llamadas a herramientas
solo se interpretan tras un final válido y siguen pasando por el parser y la
validación habituales. Una llamada incompleta no es una acción ejecutable.

Si se llena el contexto, no hay avance, se agotan los cuatro bloques o falla
una continuación, se archiva la parte visible y se devuelve `incomplete: true`.
La interfaz recibe un aviso de que la implementación no está terminada, fuera
del bloque de código. El texto bruto queda en generation_events. Se reinicia
el contexto del adaptador para que la siguiente petición parta del archivo,
no de una llamada o prefijo incompleto. No hay reanudación en segundo plano ni
garantía de completar una implementación de tamaño ilimitado. La persona puede
pedir continuar; ese siguiente turno reconstruye su contexto normalmente.

## Verificación (24 septiembre 2026)

- 150 pruebas seleccionadas pasan, incluidas seis nuevas de continuidad.
- Prueba aislada con el 12B real y límite de prueba de 128 tokens: primer bloque
  `max_tokens` (128), segundo `eos` (72); HTML completo con un único doctype.
  No se envió ningún mensaje al chat del usuario ni se ejecutaron herramientas.
- Cinco pruebas de agent_chat_test fallan igual en el padre 5fb197b: esperan
  reescrituras por afirmaciones/promesas retiradas anteriormente. No se reponen.
- No se necesita recompilar Héctor ni la interfaz. El parpadeo de resaltado
  de código no forma parte de esta corrección.
