# Avisos intermedios en el chat

El aviso usa el preámbulo visible que Gemma genera antes de su primera llamada
nativa. La política pide una frase breve sobre la operación y su destinatario,
sin nombres internos de herramientas ni resultados anticipados. HexOS no mantiene
una lista de frases por dispositivo. Si falta el preámbulo, el mismo modelo redacta una frase en una generación
separada sin herramientas, usando la petición y la operación ya validada. Esa
generación no cambia la llamada pendiente ni el contexto de la operación. Solo
si tampoco produce un texto válido queda el respaldo genérico.

Solo se publica después de validar todas las llamadas de esa generación, justo
antes de ejecutar la primera. El pensamiento interno no se utiliza como aviso.
El preámbulo se reinicia entre generaciones y turnos para no reutilizar otro antiguo.

`/api/status` permite mostrarlo durante la consulta. La respuesta final incluye
el mismo evento para operaciones demasiado rápidas para el sondeo; la interfaz
deduplica por id. No se añade una espera artificial. Los eventos se conservan en
`progress_events` y se reconstruyen después del mensaje del usuario al recargar.
No forman parte del historial que se envía al modelo ni sustituyen su respuesta.

Validación: 63 pruebas Python pasan, incluyendo publicación anterior al ejecutor,
preámbulo exacto del modelo, exclusión del pensamiento y respaldo sin texto heredado.
La comprobación JavaScript previa verificó visibilidad antes del resultado, orden
y ausencia de duplicados. `tools/progress_live_test.py` contrasta el aviso mostrado
con la generación real de Gemma en consultas locales de procedimientos e historial.

Esto hace genérica la redacción del aviso, no las capacidades de los ejecutores:
`nas.read` sigue configurado exclusivamente para el Synology. Otros accesos SSH
requieren configurar sus destinos y permisos, aunque ya no haya que escribirles avisos.

La regresión adicional comprueba la redacción suplementaria sin sustituir la llamada
pendiente. La aceptación con Gemma incluye forzar la ausencia de preámbulo y
comparar el aviso con la generación real marcada como `announcement`.
