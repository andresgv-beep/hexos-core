# Capacidades recuperadas de la ruta agente

Actualizado el **2026-09-19**. Sustituye la lista de pendientes del primer corte.
[Estado general](../IMPLEMENTATION_STATUS.md).

## Implementado

- Perfil HERA mediante `--hera` y `--memory-home`: lectura, extracción de
  afirmaciones, guardado/corrección con citas y relectura de comprobación.
  Sin esa configuración no se activa el perfil; el historial SQLite sí persiste.
- `history.search`, `history.read` y `history.recent`, con archivo recuperable
  tras limpiar contexto. La ruta JSON conserva su ventana de ocho mensajes;
  la nativa usa el bloque desde el corte, reutilización y traspaso literal.
- Separación entre diálogo, referencias y resultados de herramientas; recuperación
  de pseudollamadas con reintento restringido a lecturas.
- Imagen en el adaptador nativo cuando el HNF tiene visión; E4B real comprobado.
- Texto progresivo, cancelación por ID y continuación del chat, conectados a React.
- Notas, informes, inventario, consultas remotas, web y verificación según catálogo.

Fuentes: `hexos/agent/chat_backend/memory.py`, `context.py`, `verification.py`,
`hexos/agent/native.py` y `native_transport.py`.

## Límites que permanecen

La persistencia no garantiza una recuperación semántica perfecta ni ausencia de
confusión de identidad. No hay contexto infinito, voz conectada ni visión del
12B encoder-free. La clasificación conversacional nativa sigue devolviendo
`work: null`. No se ha certificado una autorización independiente general de
toda escritura ni autonomía completa. El producto mantiene una conversación.

## Evidencia histórica

La [auditoría inicial](AUDITORIA_CONVERSACION_NATIVA.md) registra fallos reales;
la [corrección posterior](CONVERSACION_NATIVA_CORRECCION.md) y el
[seguimiento de foco](CONVERSACION_CONTEXTO_Y_FOCO.md) documentan sus regresiones.
Sus números y pendientes corresponden a aquellos cortes. Para el transporte
actual consultar [generación progresiva](PROGRESSIVE_NATIVE_RUNTIME.md).
