# Helios: estado vigente

Revisión local: **24 de septiembre de 2026**. Este documento sustituye las
afirmaciones antiguas de que HandBrake no estaba conectado. El informe anterior
se conserva en `docs/historico/IMPLEMENTATION_STATUS_2026-09-19.md`.

**Referencia de desarrollo: `main`.** Backend e interfaz se despliegan juntos,
desde el mismo commit limpio en `hexos-live`. El commit exacto está en el archivo
local `release.env`; no se elige una rama distinta para cada componente.
Consulta [arranque y recuperación](docs/LOCAL_BASELINE.md).

## Lo que se puede usar y qué evidencia existe

| Parte | Estado y límites |
|---|---|
| Chat 12B / Héctor | Inferencia real comprobada. Historial persistente, streaming y cancelación. La descarga del modelo por inactividad es normal, no una caída. |
| Respuestas largas | Continuación del mismo prefijo hasta cuatro bloques de 3.072 tokens, limitada también por contexto. Probada con el 12B forzando un corte. Si no termina, conserva el parcial y avisa. No garantiza implementaciones ilimitadas. |
| Interfaz | Esfera nueva NebulaOrb, visor de código, preview HTML, deshacer, redimensionado y maximizar/restaurar. La respuesta incompleta no reemplaza automáticamente el código abierto. El prompt permite cambiar estructura ante un rediseño, sin imponer retoques mínimos. |
| Edición del código | Existe edición desde el chat, pero el prompt exige devolver la versión COMPLETA. No existe aún aplicación incremental de parches sobre archivos persistentes. |
| Resaltado progresivo | Se eliminó la alternancia entre texto plano y resaltado al alcanzar cada fragmento. Regresión estructural cubierta; pendiente confirmar percepción visual en uso prolongado. |
| HERA | Conector explícito en el arranque. Citas validadas antes de agrupar candidatos. Una extracción automática con valor distinto no sustituye otro si el mensaje no contiene el valor anterior; la herramienta explícita conserva correcciones. El extractor pide atributos específicos y distingue ediciones locales de preferencias duraderas. No garantiza extracción semántica infalible. No hay nombre personal hardcodeado en el prompt. |
| NAS y preparación multimedia | Búsqueda con raíz/tamaño/extensión y preparación de planes. Hay pruebas reales anteriores de selección correcta del 12B, con contexto; no certifican autonomía en frío. Preparado NO significa iniciado. |
| HandBrake | Transporte real, copia, conversión, seguimiento, verificación y publicación implementados. Ciclo sintético real histórico completo; película real convertida y validada técnicamente, pero NO publicada. |
| Revisión interna de La Monja | **Pendiente/bloqueada**: `awaiting_review`, revisión 15, validación y decodificación registradas como correctas, publicación ausente. No se ha reintentado ni publicado durante esta consolidación. |
| Text / Cortex | Sesiones y contextos separados. Hoy las revisiones reutilizan los pesos de Text `0x0`; no hay modelo Cortex en otra GPU. |
| Lectura documental | Rangos acumulados, cobertura y continuidad acotada integrados. No convierte una lectura parcial en una lectura completa. |

## Qué NO se da por resuelto

- JSON inválido de la revisión interna de HandBrake. El error no prueba que el
  vídeo esté mal; tampoco permite afirmar que ya esté publicado.
- Fiabilidad conversacional general del 12B con contexto frío o memoria:
  una respuesta convincente no sustituye llamadas, argumentos y resultados.
- Edición incremental de código, voz operativa y reparto de un modelo entre GPU.
- Autorización general de escrituras: la validación de argumentos no constituye
  por sí sola un sistema completo de permisos. No se integró la rama experimental
  `frenos-y-silencios` ni se restauraron reescrituras por frases de Text.
- No se ha comprimido otra película, alterado el preset ni reiniciado el
  contenedor de HandBrake para esta revisión.

## Verificación reproducible

```bash
python3 tools/check_local_baseline.py
cd interfaz
npm test
npm run check
npm run build
```

La batería Python utiliza una lista explícita de pruebas locales: no importa
los scripts opt-in que envían mensajes a un servidor vivo. Resultado de la
base actual: **665 pruebas Python, 85 de interfaz, tipos y build/render**.
Los ensayos reales históricos están en
`docs/HANDBRAKE_CHAT_REVIEW.md`; no se presentan como repetidos hoy.

## Ramas: no hay que adivinar cuál usar

En `main` se reúnen tareas HandBrake, contratos de búsqueda, progreso real,
memoria, retirada de reescrituras de Text, correcciones posteriores de
recuperación, nombres multimedia legibles, lectura acotada y continuidad de
salida. Las ramas de esos temas se conservan como referencias históricas.

`vision-en-el-chat` ya está contenido en la base. `diseno/nucleo` conserva un
experimento de diseño no seleccionado. `frenos-y-silencios` conserva una línea
experimental de permisos expresamente no incorporada. No se han borrado ramas
ni se ha hecho push. Héctor es otro repositorio: no se han cambiado sus pesos,
su rama ni su motor durante esta consolidación.
