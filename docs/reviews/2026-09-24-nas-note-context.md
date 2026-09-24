# Auditoría del resumen NAS guardado como nota

Evidencia: registros locales de `runtime/workspace/work.sqlite`; inspección de solo lectura.
No se ha modificado la nota ni el perfil de HERA.

## Contaminación del resumen

- Petición `41ed91f738934d01862792d2abc458de`: «haz un resumen de todo y crealo como nota», después de una revisión del Synology 1.
- El prompt registrado en `generation_events` contiene el perfil personal completo bajo `PERFIL CONFIRMADO POR HERA`, inmediatamente en el contexto del turno. No procede de una lectura NAS.
- `ContextService` lee el perfil en `chat_backend/context.py` y lo incorpora a los metadatos nativos sin selección de relevancia por encargo.
- El modelo llamó `core.overview`, anunció que compilaría lo guardado en su equipo y redactó una sección de contexto personal. La desviación aparece en la generación previa al guardado.
- Tras la confirmación, el turno `38f3588f67894c608c0d6b1a347399ee` llamó `note.save` con ese contenido. El resultado coincide con los argumentos: 889 caracteres. No hubo recorte a 300 ni a 2000.
- `note.save` verifica persistencia por relectura. Esa comprobación no certifica relevancia ni exactitud del informe.

## Lectura de contenedores con alcance incorrecto

- Turno `a4eda4efd98b476abe84db2e5c7fa9dd`: `nas.read` con `section=containers`, `container=all`.
- `nas_session.command` convierte cualquier nombre recibido en `docker ps -a --filter name=<nombre>`. `all` no es un selector global.
- La respuesta fue una lista vacía con `container=all`. No prueba que no existan contenedores en el servidor.
- El modelo generalizó ese resultado a todos los contenedores y lo propagó a la nota.

## Correcciones a diseñar y validar

1. Separar memoria personal y fuentes del encargo; no entregar indiscriminadamente todo el perfil para producir un informe técnico. Una instrucción en el prompt no constituye una garantía.
2. Hacer explícito el alcance de listados NAS: todos o nombre concreto. No convertir silenciosamente `all` en un listado global, pues también puede ser un nombre real.
3. Probar la cadena completa con resultados conocidos: resumen del NAS sin datos ajenos, listado filtrado vacío sin concluir ausencia global, y recuperación personal cuando sí se solicita.
4. Corregir la nota mediante una nueva revisión únicamente con contenido respaldado, sin borrar su histórico ni inventar el estado actual del NAS.

Esta auditoría no demuestra un fallo del parser de Markdown ni de los límites de almacenamiento. El visor tenía además un fallo de presentación independiente: mostraba Markdown como texto plano.

## Corrección aplicada

- Perfil retirado de la inyección automática, tanto nativa como JSON. Nueva lectura `profile.recall(query)` devuelve hasta diez hechos coincidentes; no existe volcado implícito ni comodín global.
- `nas.read` distingue `scope=all` sin `container` y `scope=name` con un filtro. El `container=all` ambiguo se rechaza antes del transporte y explica cómo corregirlo. Un contenedor realmente llamado all sigue siendo consultable con scope=name.
- Los resultados identifican el alcance; una lista filtrada vacía advierte que no demuestra ausencia global.
- 131 pruebas de contexto, perfil, NAS, adaptador nativo y notas superadas.
- Prueba aislada con Gemma 4 E4B real y perfil ficticio: la primera solicitud creó una nota técnica de NAS con los resultados suministrados y sin hechos del perfil. Sin SSH ni escritura en el almacén real durante esa prueba. Es una prueba puntual, no una garantía universal del modelo.
- Nota afectada corregida a revisión 2, preservando revisión 1. Renovado el contexto activo sin borrar conversación ni HERA para evitar reutilizar el borrador contaminado.
