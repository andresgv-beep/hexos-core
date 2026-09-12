# Auditoría exploratoria del prompt del agente

Fecha: 2026-09-12. Ruta evaluada: `hexos/agent/chat.py`, no CK legacy.
Nota posterior: esta captura corresponde al ciclo v1. El ciclo v2 separa
resumen y guardado; ejecutar el script ahora compara el prompt vigente y no
reproduce exactamente esta captura histórica. Véase TRABAJOS.md.
No se modificó el prompt del servidor ni el perfil de la persona. Candidato
confinado a `tools/prompt_audit.py`; espacios de trabajo temporales independientes.

## Método y límites

Mismo runtime Héctor, HNF E4B, contexto 8192 y generación greedy. Se mantuvieron
el ciclo de herramientas, las correcciones automáticas y la reconstrucción de
contexto. Un trabajo inicial: «Revisar espacio libre del NAS». Se probaron seis
turnos por variante: resumen de pendientes, resumen anafórico, ideas de mejora,
saludo, retorno al informe, y recuperación después de limpiar contexto.

Una sola secuencia por variante, sin significación estadística ni certificación
de autonomía. La versión candidata modifica varias instrucciones: no permite
atribuir cada diferencia a una frase concreta. La prueba anterior de errores
inyectados es independiente; esta comparación no los inyectó.

## Evidencia observada

| Medida | Actual | Candidato simplificado |
|---|---|---|
| Turnos con ofrecimiento/pregunta de cortesía final (lectura manual) | 4/6 | 1/6 |
| Primera petición de resumen | procedure.run correcto | arguments vacío; error; corrección con id |
| «haz un resumen» tras el resultado | Resume sin preguntar | Resume sin preguntar |
| Petición de ideas modifica fichas | No | No |
| Recuperación después de limpiar contexto | report.list → report.get → procedure.run | report.list → report.get |

En la variante actual, recuperar el informe produjo además uno nuevo: no era
necesario ni equivalente a consultar la instantánea. La candidata evitó ese paso,
pero copió varias veces la advertencia de «no es una revisión de dispositivos».
Ambas conservan rasgos de asistente comercial; incluso la candidata saludó con
«¿En qué puedo ayudarte hoy?». No se declara ningún candidato listo para sustituir
al actual.

## Hallazgos de código

1. El prompt pide clasificar todo turno sobre un trabajo concreto y luego excluye
   consultas/informes. La condición de crear ficha es ambigua.
2. Catálogo y validación están escritos en sitios distintos: el esquema no genera
   la documentación entregada al modelo. La candidata usó `{}` como ejemplo
   genérico y el modelo emitió precisamente argumentos vacíos. Es una pista de
   sensibilidad al ejemplo, no una causa demostrada con ablación.
3. La ruta no llama a CK/HERA legacy: modificar sus contratos no corrige este chat.
4. El historial se reduce a ocho mensajes y se aplana dentro de un mensaje user.
   Los mensajes de más de 1000 caracteres se sustituyen completos por un aviso.
   Esto limita continuidad independientemente de la personalidad del prompt.
5. Solo se reinyecta la última operación registrada, no un índice de todos los
   artefactos relevantes. Los informes anteriores siguen en disco y requieren
   herramientas de recuperación.
6. Una recuperación automática puede rescatar una llamada; el resultado final
   satisfactorio no demuestra que el modelo la haya formulado bien al primer intento.

## Mejora recomendada, aún no aplicada

- Mantener un objetivo estable y corto: completar el encargo, comprobar resultado
  y comunicarlo. Separar esa política del protocolo JSON.
- Generar catálogo y errores desde una única definición de argumentos/permisos.
  Usar ejemplos válidos concretos, no un objeto vacío como ejemplo universal.
- Definir por separado consulta, recuperación de instantánea y creación de informe.
  La recuperación no debe activar implícitamente una nueva ejecución.
- Reservar clasificación de fichas para la creación explícita de trabajos; no
  pedirla como decisión secundaria en toda respuesta.
- Evaluar el estado del encargo y recuperación de artefactos por separado del
  estilo. No esperar que menos instrucciones recuperen información omitida.
- Ampliar A/B con solicitudes ambiguas, negativas, errores, documentos largos y
  retorno tras cambio de tema; medir primer intento, escrituras no solicitadas,
  aclaraciones redundantes y fidelidad del resultado además de longitud.

Reproducción (requiere GPU libre; no ejecutar junto al servidor con otro modelo):

```sh
python3 tools/prompt_audit.py --runtime /ruta/helios_runtime --model /ruta/modelo.hnf
```
