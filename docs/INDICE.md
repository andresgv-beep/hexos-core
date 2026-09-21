# Índice documental de Hexos

Revisado el **2026-09-19**, sobre `76a75c0`. Empezar por el
[estado de implementación](../IMPLEMENTATION_STATUS.md) y el [arranque](../README.md).
No convertir una lista de pendientes histórica en tareas nuevas sin contrastarla
con ese estado y con el código.

## Guías y contratos mantenidos

| Documento | Ámbito |
|---|---|
| [AGENTE_DOMESTICO_PLAN.md](AGENTE_DOMESTICO_PLAN.md) | Dirección y avance del producto de un modelo/un chat. |
| [AVISOS_DE_OPERACION.md](AVISOS_DE_OPERACION.md) | Avisos de herramientas, distintos del streaming. |
| [CICLO_AGENTE_VERIFICACION.md](CICLO_AGENTE_VERIFICACION.md) | Diseño e implementación parcial; no certifica autonomía general. |
| [E1_PROTOCOLO_RUNTIME.md](E1_PROTOCOLO_RUNTIME.md) | Estado del protocolo implementado y diferencias con E1. |
| [INVENTARIO_DISPOSITIVOS.md](INVENTARIO_DISPOSITIVOS.md) | Registro y atribución de equipos. |
| [NAS_CONTENIDO.md](NAS_CONTENIDO.md) | Exploración y catálogo de archivos; arquitectura prevista de HandBrake. |
| [FILE_CATALOG_ARCHITECTURE.md](FILE_CATALOG_ARCHITECTURE.md) | Base modular implementada, contratos y etapas pendientes para bibliotecas, sincronización y acceso a archivos. |
| [MULTIMODAL_TRANSPORT.md](MULTIMODAL_TRANSPORT.md) | Python/base64/NDJSON separado del endpoint RGB8 C. |
| [NATIVE_TOOLS_INTEGRACION.md](NATIVE_TOOLS_INTEGRACION.md) | Integración nativa; incluye evidencia de sus primeros cortes. |
| [PROGRESSIVE_NATIVE_RUNTIME.md](PROGRESSIVE_NATIVE_RUNTIME.md) | Progreso, cancelación, arranque y aceptación real. |
| [RECUPERACION_CAPACIDADES.md](RECUPERACION_CAPACIDADES.md) | Memoria, contexto e imágenes ya incorporados y límites. |
| [RED_LOCAL_LECTURA.md](RED_LOCAL_LECTURA.md) | Lecturas pasivas y sus límites de descubrimiento. |
| [RUNTIME_RESIDENCY_POLICY.md](RUNTIME_RESIDENCY_POLICY.md) | Política C/launcher; diferencias explícitas con Python. |
| [SSH_SYNOLOGY_DIAGNOSTICO.md](SSH_SYNOLOGY_DIAGNOSTICO.md) | Estado actual del acceso y registro histórico de Synology. |
| [TRABAJOS.md](TRABAJOS.md) | Almacén, fichas, documentos e informes. |
| [WEB_PUBLICA.md](WEB_PUBLICA.md) | Frontera y validación de búsqueda/lectura web. |

Interfaz: [uso](../interfaz/README.md) y [arquitectura](../interfaz/docs/ARQUITECTURA.md).

## Planes y auditorías de cortes anteriores

Los hallazgos siguen siendo evidencia de aquel corte. Las prioridades operativas
actuales están en `IMPLEMENTATION_STATUS.md`. CK y la ruta C no son el agente
Python; los especialistas están aparcados.

- [AGENTES_ESPECIALISTAS_PLAN.md](AGENTES_ESPECIALISTAS_PLAN.md).
- [AUDITORIA_CONVERSACION_NATIVA.md](AUDITORIA_CONVERSACION_NATIVA.md).
- [AUDITORIA_PROMPT_AGENTE.md](AUDITORIA_PROMPT_AGENTE.md).
- [CK_V4_NORTE.md](CK_V4_NORTE.md).
- [CK_V5_CONTRATO.md](CK_V5_CONTRATO.md).
- [CONVERSACION_CONTEXTO_Y_FOCO.md](CONVERSACION_CONTEXTO_Y_FOCO.md).
- [CONVERSACION_LARGA_PLAN.md](CONVERSACION_LARGA_PLAN.md).
- [CONVERSACION_NATIVA_CORRECCION.md](CONVERSACION_NATIVA_CORRECCION.md).
- [E0_INVENTARIO_PROMPTS.md](E0_INVENTARIO_PROMPTS.md).
- [E2_CORPUS_CK.md](E2_CORPUS_CK.md).
- [NATIVE_TOOLS_LAB.md](NATIVE_TOOLS_LAB.md).
- [PLAN_EVACUACION_COGNITIVA.md](PLAN_EVACUACION_COGNITIVA.md).

## Informes de hitos

E2/E3/E4 describen portación, memoria, sesiones y UI del servidor C. No implican
que multichat o reflexión estén activados en React/Python. E5 documenta el hito
inicial del 12B; sus cifras no sustituyen las campañas posteriores de Héctor.

- [E2_CIERRE.md](../informes/E2_CIERRE.md).
- [E3_ALMACEN.md](../informes/E3_ALMACEN.md).
- [E3_CABLEADO.md](../informes/E3_CABLEADO.md).
- [E3_MENTE.md](../informes/E3_MENTE.md).
- [E4_CHATS.md](../informes/E4_CHATS.md).
- [E4_CHATS_HEXOS.md](../informes/E4_CHATS_HEXOS.md).
- [E4_COLA.md](../informes/E4_COLA.md).
- [E4_PARSER.md](../informes/E4_PARSER.md).
- [E4_REFLEXION.md](../informes/E4_REFLEXION.md).
- [E4_UI_CHATS.md](../informes/E4_UI_CHATS.md).
- [E5_GEMMA4_12B.md](../informes/E5_GEMMA4_12B.md).

Otros antecedentes: [portación HERA](../hera/PORT_FROM_CHAT.md),
[experimentos LM Studio](../experiments/lmstudio/README.md).

## Documentos sustituidos, conservados para consulta

- [E1_PROTOCOLO_PROPUESTA.md](historico/E1_PROTOCOLO_PROPUESTA.md).
- [IMPLEMENTATION_STATUS_2026-01-18.md](historico/IMPLEMENTATION_STATUS_2026-01-18.md).
- [README_ECOSISTEMA_PRE_2026-09-19.md](historico/README_ECOSISTEMA_PRE_2026-09-19.md).

## Regla de actualización

Cada hito que cambie capacidades o arranque debe actualizar el estado, el contrato
afectado y su evidencia. No presentar recuentos antiguos de tests como nuevas
validaciones ni confundir el modelo probado con toda una familia.

[Desfases corregidos y comprobaciones de esta revisión](REVISION_DOCUMENTAL_2026-09-19.md).
