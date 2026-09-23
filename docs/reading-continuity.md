# Continuidad de lectura acotada

La lectura de copias (`nas.file_open`, `nas.file_read`) dispone de 48 llamadas y
300 segundos por turno, comprobados entre llamadas. Las demás herramientas
conservan su presupuesto de seis llamadas. La cancelación sigue usando el
mecanismo del turno. Una llamada en curso conserva sus propios timeouts.

El modelo puede encadenar lecturas y explicar fragmentos. La cobertura parcial
se añade a su respuesta sin borrar observaciones parciales. Las afirmaciones de
lectura completa reconocidas por el comprobador se corrigen si falta cobertura.
El detector lingüístico no garantiza reconocer todas las afirmaciones posibles.

La comprobación ofrece otra generación cuando se pidió lectura completa o se
ha afirmado haberla completado, siempre que aumente la cobertura. Tres lecturas
consecutivas de la misma copia sin cobertura nueva detienen la continuación.
Los offsets siguen en puntos de código Unicode y los rangos persisten en la traza.

No es todavía un planificador persistente de investigaciones: al agotar el
presupuesto el turno termina y no se reanuda en segundo plano. Tampoco garantiza
que los fragmentos entregados sigan en contexto ni que hayan sido comprendidos.
La recuperación de contexto existente conserva sus propios límites.

Validación: runtime simulado que lee 66.978 caracteres en 17 llamadas dentro de
una sola petición; respuestas parciales, continuidad superior a dos reintentos,
tiempo, estancamiento y separación del presupuesto de otras herramientas.
La evaluación del modelo 12b real debe realizarse en su instancia.
