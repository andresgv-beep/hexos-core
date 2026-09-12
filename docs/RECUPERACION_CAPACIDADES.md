# Recuperación de capacidades de la ruta agente

## Primer corte implementado

- `--hera` y `--memory-home` conectan el perfil confirmado existente al contexto
  de cada turno. Usa la API HERA mediante CLI, no un segundo parser del diario.
  No importa legacy ni promociona candidatos. Abrir HERA conserva su recuperación
  habitual de cola incompleta y sus cerrojos; no es apertura forense de solo lectura.
- `history.search`, `history.read` y `history.recent` recuperan mensajes del mismo
  espacio de trabajo después de limpiar contexto. Lectura paginada completa.
- El contexto corto incluye IDs y fechas; mensajes largos incluyen extracto y
  referencia recuperable. La ventana de ocho mensajes no se ha eliminado: se ha
  añadido acceso al resto, no contexto infinito.
- 30 pruebas Python pasan. Las tres nuevas comprueban recuperación paginada exacta,
  aislamiento, perfil HERA confirmado, corrección, ausencia de append al leer un
  diario válido y error explícito si falla el perfil.
- Prueba real: Marta → pregunta por nombre → corrección Elena → pregunta por nombre
  devuelve los nombres correspondientes. Primera respuesta fue «Soy Marta», una
  confusión de voz todavía observable; no certificar comportamiento completo.
- Después de reset el modelo buscó una frase demasiado literal y concluyó ausencia.
  Se añadió `history.recent` como alternativa; pendiente repetir esa prueba real.

Actualización de investigación: la [auditoría de conversación y arquitectura](AUDITORIA_CONVERSACION_NATIVA.md)
repitió una secuencia aislada Marta → Elena → reset. Recuperó Elena mediante
history.search con «nombre», pero los turnos reales del usuario siguieron fallando
en el replay. La recuperación limpia no certifica continuidad con errores previos.

Corrección posterior: [recorrido conversacional](CONVERSACION_NATIVA_CORRECCION.md).
Ahora pasan ambos replays y la recuperación de la corrección del nombre después
de reset y reinicio real del motor. El historial se devuelve en orden cronológico;
una pseudollamada puede recuperarse con un reintento nativo restringido a lecturas.

El [seguimiento de contexto y foco](CONVERSACION_CONTEXTO_Y_FOCO.md) añade recuperación
automática de hasta ocho citas recientes del usuario, incluso después de reset.
El diálogo inmediato y esas referencias quedan separados. Esto no escribe en HERA.

## No completado

Escritura de memoria personal desde el agente, extracción de candidatos y confirmación
con autoridad; visión en el puente nativo; clasificación conversacional nativa;
streaming y cancelación; revisión de identidad/registro. No se restaura multichat.

El servidor se reinicia con el perfil HERA existente, sin borrar conversación.
No afirmar que «soy X» ya se guarda como hecho persistente: hoy queda en historial
y puede recuperarse, pero no se promociona automáticamente al perfil confirmado.
