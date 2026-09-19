# Revisión documental de Héctor y Hexos — 2026-09-19

Bases contrastadas: Héctor `b822e1b`, Hexos `76a75c0`. Esta entrega modifica
solo documentación: no altera motor, pesos, agente, procesos ni configuración.

| Desfase encontrado | Corrección y evidencia |
|---|---|
| Héctor decía «sin streaming» y «solo binarios de test» | README reescrito: CLI, NDJSON, eventos y cancelación ya implementados en `tools/helios_runtime.cpp`. HTTP sigue perteneciendo a Hexos. |
| Listado de modelos omitía Gemma/Qwen3 y prometía un pipeline sin ramas | Estado por familia, evidencia fechada y límites; `graph_builder` y runner Gemma tienen rutas específicas. |
| HQ41/HQ51 se describían como bloques de 1K y HQ62 no estaba explicado | Tabla desde `src/dtype.cpp`: bloques de 256, bytes efectivos y HQ62 limitado a lookup. |
| CMake documentaba arquitecturas CUDA 75/86/89 predeterminadas | Ahora documenta la asignación `native` existente y el límite de portabilidad. |
| Estado de Hexos de enero decía motor inexistente y proponía integrar llama.cpp | Archivado íntegro; nuevo estado del agente real/Héctor y responsabilidades. |
| UI documentada como demo, sin conexión, sin detener | READMEs/arquitectura actualizados a transporte real, sondeo de progreso y cancelación dirigida. |
| Esfera documentada a 24 fps/DPR 1/sin bloom/pausada | Código actual: máximo 30 fps, DPR 2, EffectComposer/Bloom, movimiento condicionado a visibilidad y preferencia. |
| E1 seguía «propuesto», sin sesiones y con invariantes KV anticuados | Propuesta archivada y contrato actual en Héctor; diferencias explicadas en Hexos. Las fixtures iniciales no se anuncian como cobertura completa. |
| API C y Python se mezclaban | Separadas en arranque, estado, protocolo de imagen y residencia. No son backends intercambiables en 8080. |
| Perfil, contexto, imagen, SSH/web y cancelación figuraban ausentes | Listas actualizadas desde `memory.py`, `context.py`, catálogo, transporte y server. Límites de calidad/autoridad conservados. |
| SSH figuraba solo en memoria durante ocho horas, sin credenciales persistidas | Alcance actual desde `hosts.py`, `nas_session.py` y `access.py`; historia de Synology identificada expresamente. |
| Plan de evacuación y portación HERA parecían sin empezar | Enlaces a hitos ya implementados y separación de la dirección actual de un chat. |

## Criterios conservados

- Visión encoder-free del 12B sigue pendiente; convertir el bloque no completa
  el runner. E4B con torre no certifica esa variante.
- Voz, multi-GPU, batching concurrente y autonomía general no se dan por terminados.
- La política automática mmap de C no se atribuye al adaptador Python, que fuerza
  actualmente dos variables al lanzar Héctor.
- No se borran medidas ni incidentes de los informes; se marca su fecha/alcance.
- La ventana JSON de ocho mensajes se diferencia del bloque nativo con KV y traspaso.

## Validación documental

Contraste con código local, revisión de enlaces relativos de los documentos
modificados y `git diff --check`. Sin nuevas inferencias ni benchmark: los
resultados citados pertenecen a los informes existentes. No se requiere reiniciar
ni recompilar para estos cambios.

Puertas de entrada mantenidas: `Hector-engine/ESTADO_ACTUAL.md`,
[IMPLEMENTATION_STATUS](../IMPLEMENTATION_STATUS.md) e [índice](INDICE.md).
