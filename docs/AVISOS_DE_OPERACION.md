# Avisos intermedios en el chat

Actualizado el 2026-09-19: estos avisos de operaciones son distintos del texto
progresivo de la respuesta, que ya está conectado. Véase
[generación progresiva](PROGRESSIVE_NATIVE_RUNTIME.md). Los recuentos de pruebas
inferiores corresponden a la aceptación original de este mecanismo.

El aviso utiliza el preámbulo visible que Gemma genera antes de una llamada
nativa, una vez validada su sintaxis y argumentos. Se pueden conservar avances
de varias operaciones durante el mismo turno. Si falta preámbulo, solo el primer
aviso puede solicitar una generación suplementaria sin herramientas; si tampoco
produce texto válido se usa el respaldo genérico. En los pasos posteriores sin
preámbulo sigue visible la actividad de la herramienta, sin pagar otra inferencia
solo para redactar un aviso.

El pensamiento interno no se publica como aviso. El preámbulo se reinicia entre
generaciones y turnos. La generación suplementaria no sustituye la operación
ya validada ni su contexto. Fuente: `chat_backend/tools.py`.

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
`nas.read` opera sobre equipos registrados y con credenciales configuradas;
no está limitado por nombre a un único Synology. Las secciones disponibles y
su interpretación dependen del ejecutor y del equipo. No es shell arbitraria.

La regresión adicional comprueba la redacción suplementaria sin sustituir la llamada
pendiente. La aceptación con Gemma incluye forzar la ausencia de preámbulo y
comparar el aviso con la generación real marcada como `announcement`.
