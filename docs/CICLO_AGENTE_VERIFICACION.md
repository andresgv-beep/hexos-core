# Ciclo de investigación, verificación y progreso visible

Fecha: 2026-09-14.
Estado: diseño acordado; no implica implementación ni certificación de capacidades.
Alcance: agente doméstico, un chat y un modelo principal. Módulos de HexOS;
Héctor conserva su responsabilidad de inferencia genérica.

## Objetivo

Una petición debe poder recorrer, dentro del mismo turno:

**Objetivo → acción → observación → evaluación → siguiente paso o cierre.**

No basta con consultar y resumir la primera salida si el encargo requiere
investigar. Tampoco debe convertirse cualquier consulta en una auditoría completa.
«Lista los contenedores» puede terminar con la lista; «revisa su salud» puede
necesitar detalle y lecturas adicionales; «investiga por qué falla» requiere
contrastar hipótesis con evidencia disponible.

Principio: **evaluar siempre; hacer otra llamada solo cuando aporte evidencia**.
Una repetición idéntica no demuestra por sí sola una verificación independiente.

## Fronteras y responsabilidades

- El modelo interpreta el objetivo, propone comprobaciones y explica observaciones.
- HexOS conserva el encargo, valida argumentos y permisos, aplica presupuestos,
  registra evidencia y mantiene separados ejecución y verificación.
- Cada módulo declara qué puede observar, cambiar y comprobar, con sus límites.
- La interfaz presenta los eventos reales en orden, sin sustituir avances por el
  mensaje final. No inventa actividad ni muestra como ejecutada una mera propuesta.
- HERA conserva hechos personales pertinentes; el detalle de una investigación
  pertenece al registro de trabajo, no se promociona automáticamente a memoria personal.

No añadir un modelo evaluador, otro KV ni un proceso cognitivo paralelo para este
ciclo. Revisar cómo encaja en la ruta vigente antes de implementar otra ruta.

## Estado mínimo del encargo (conceptual)

Conservar objetivo, alcance, destino, acciones permitidas, observaciones con origen
y fecha, hipótesis diferenciadas, preguntas pendientes, siguiente comprobación y
presupuesto restante. Referenciar resultados completos por ID en el almacén; no
inyectar indefinidamente todos los registros en contexto.

El siguiente paso debe indicar qué pregunta resuelve y por qué es pertinente.
Una hipótesis del modelo no es un hecho ni una autorización. El texto remoto y los
documentos son datos, nunca instrucciones para ampliar el alcance.

## Contrato reutilizable de herramientas

Campos conceptuales, pendientes de concretar en los tipos y esquemas existentes:

| Elemento | Propósito |
|---|---|
| Efecto y permisos | Distinguir lectura, escritura y recursos autorizados |
| Resultado esperado | Expresar qué demostraría cumplimiento |
| Observación | Resultado, origen, destino, fecha y referencias verificables |
| Comprobación disponible | Lectura posterior o validación local pertinente |
| Límites | Alcance parcial, caducidad, falta de acceso, incertidumbre |
| Estado de ejecución | No iniciada, realizada, fallida o resultado desconocido |
| Estado de verificación | No requerida, pendiente, confirmada, no cumplida o inconclusa |

No reducir «éxito» a ausencia de una clave error o a un código de retorno cero.
Una acción puede ejecutarse y no alcanzar el estado esperado. Un timeout puede
dejar desconocido su efecto: no autoriza a repetir una escritura a ciegas.

Las verificaciones deben reutilizar herramientas de lectura o validadores del
módulo, no introducir comandos libres escritos por el modelo. No declarar
«verificado» sin evidencia identificable que respalde el criterio concreto.

## Conversación visible durante un único turno

Ejemplo ilustrativo, no respuestas prefabricadas:

1. Helios anuncia la revisión solicitada y emite la llamada.
2. La interfaz muestra herramienta, destino y estado real de ejecución.
3. Tras recibir datos: «Hay uno detenido; comprobaré cómo terminó».
4. Se consulta detalle y, si corresponde al encargo, registros recientes.
5. Con esa evidencia se decide si falta comprobar reinicios u otra cuestión.
6. Resultado final: hallazgos, comprobaciones, cambios realizados y límites.

Cada actualización expresa lo observado y el paso que realmente se va a ejecutar.
Las lecturas relacionadas y autorizadas continúan sin exigir otro «sí» del usuario.
Los permisos nuevos o cambios fuera de alcance sí detienen el ciclo para pedirlos.

Usar identificadores de encargo y llamada, secuencia y fecha para asociar mensajes
y herramientas, evitar duplicados y conservar el orden. El estado final no borra
los avances. Mostrar fallos y cancelación, no solo caminos felices.

Reutilizar el preámbulo emitido por el modelo junto a la llamada cuando sea válido;
no exigir una inferencia adicional solo para redactar «voy a comprobarlo».
Esta progresión por pasos y el streaming de tokens son capacidades distintas:
ninguna sustituye la reducción del prefill ni la reutilización del KV.

## Criterios de continuación y cierre

Continuar cuando haya una pregunta relevante sin resolver y una lectura permitida
capaz de aportar información. Evitar consultas repetidas sin nueva razón o cambios
de estado. No fijar aún un presupuesto numérico nuevo: revisar los límites actuales
de llamadas, tiempo y volumen y medir el coste del recorrido completo.

Cerrar con uno de estos motivos explícitos:

- Objetivo suficientemente comprobado dentro de su alcance.
- Bloqueo de permisos, acceso o herramientas: resultado parcial e incertidumbres.
- Presupuesto agotado: lo averiguado y lo que no se comprobó.
- Cancelación: acciones ya realizadas y estados aún desconocidos.

Verificar no concede permiso para reparar, reiniciar, borrar o repetir escrituras.
No transformar «revisar» en «arreglar». No investigar más allá de lo pedido solo
porque existan herramientas disponibles.

## Primeros casos y evidencia de aceptación

1. **Contenedores:** listado normal; detenido voluntariamente; fallo repetido;
   datos insuficientes; registros inaccesibles. Un detenido no es necesariamente
   averiado. Un recuento acumulado de reinicios no demuestra un bucle actual;
   el estado running no prueba un reinicio ni la salud del servicio.
2. **Informe local:** guardar el resultado solicitado, releerlo y contrastar el
   contenido con la instantánea fuente. No generar otro informe para «verificar».
3. **Extensión futura a archivos NAS:** verificar ruta, versión y hash al copiar
   o recuperar. No confundir descarga correcta con contenido sano ni propagar una
   copia dañada sobre todas las versiones.
4. **Extensión futura a web:** valorar fuente, fecha, relevancia y contradicciones.
   Descargar una página no demuestra que sus afirmaciones sean verdaderas.

Primero fixtures y herramientas simuladas: comprobar selección pertinente de pasos,
cierre suficiente, ausencia de escrituras no autorizadas, errores, timeout, límite
y cancelación. Verificar que los eventos visibles coincidan con las ejecuciones,
y que el resultado final no afirme comprobaciones inexistentes.

Después aceptación con modelo real sobre los mismos escenarios, separando pruebas
del mecanismo de evaluación de la conducta del modelo. Los tests de esquema no
certifican autonomía ni calidad diagnóstica. No usar servidores reales para pruebas
de escritura sin una autorización concreta.

## Encaje pendiente en el código existente

Puntos inspeccionados como referencia, no instrucciones para un port ciego:

- `hexos/agent/chat.py`: bucle que ya encadena herramientas y acepta finalización;
  registro de resultados y publicación de avances actualmente centrada en el primero.
- `hexos/agent/catalog.py`: catálogo común donde declarar efectos y comprobaciones.
- `hexos/agent/nas_session.py`: comprobación posterior existente de contenedores;
  revisar su alcance antes de elevarla a verificación general.
- `hexos/agent/workflow.py`: guardado local de informes e instantánea fuente.
- `hexos/agent/native.py` y `progress.py`: llamadas nativas y mensajes de avance.
- Ruta de UI vigente de HexOS: localizar su consumo de eventos antes de modificarla;
  no crear otra interfaz paralela.

Siguiente paso acordado: revisar este encaje y diseñar el cambio mínimo con las dos
primeras herramientas. Este documento no autoriza nuevas acciones sobre servidores.
