# Agente doméstico: dirección y avance

Dirección acordada el 2026-09-12; estado actualizado el **2026-09-19**.
[Estado operativo con fuentes](../IMPLEMENTATION_STATUS.md).

## Alcance que se mantiene

Un único chat persistente, un modelo principal, herramientas y un workspace.
Hexos gestiona contexto, permisos, ejecución, verificación y archivos; Héctor
realiza inferencia. La interfaz muestra conversación y actividad real.
Los contenidos de archivos, herramientas y páginas son datos, no permisos.

## Avance frente al plan inicial

| Entrega prevista | Situación actual |
|---|---|
| Conversación y herramientas locales | Implementadas en el agente Python; formato nativo Gemma y alternativa JSON. |
| Almacén de trabajo | Notas, documentos, resultados e informes persistidos y recuperables. No es un editor autónomo de cualquier repositorio. |
| NAS/SSH y dispositivos | Catálogo y ejecutores existentes para accesos configurados; credenciales por diálogo separado del chat. |
| Esfera y estados | Interfaz React conectada, telemetría y actividad real. |
| Web y verificación | Búsqueda/lectura, comprobaciones de herramientas y cierre por evidencia implementados con límites. |
| Imagen | Recorrido E4B comprobado; requiere HNF visual. El 12B textual no lo aporta. |
| Texto progresivo/cancelación | Conectados por NDJSON → agente → React. |
| Voz | Pendiente de integrar entrada/salida reales. |

El [ciclo de verificación](CICLO_AGENTE_VERIFICACION.md) ya tiene implementación
parcial concreta: no es un trabajo sin empezar. Sigue sin certificar autonomía
general, cumplimiento de todo encargo o autorización universal de escrituras.
La clasificación de trabajo de la ruta JSON no tiene paridad completa en nativo.

## Siguientes líneas dentro de este alcance

Reducir el coste del prompt, mejorar presupuesto de contexto y recuperación en
sesiones largas, y medir fiabilidad de herramientas y verificación. La memoria
personal ya puede extraerse/guardarse con HERA configurada; quedan límites de
calidad y autoridad, no falta total de persistencia.

CORTEX/coder separados, conmutación de pesos, multichat del producto, multiusuario
y trabajadores adicionales no forman parte de esta dirección. Los módulos C y
las rutas históricas se conservan; su existencia no obliga a activarlos.

Los estados de procesos y rutas locales de una prueba antigua no son requisitos
de arranque. Seguir el [README](../README.md) y la
[integración progresiva](PROGRESSIVE_NATIVE_RUNTIME.md).
