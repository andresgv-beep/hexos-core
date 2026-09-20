# Contrato de instrucciones del chat nativo

## Responsabilidades

- `hexos/agent/native.py:POLICY`: identidad, ejecución del encargo, continuidad,
  autorización general, honestidad y forma de responder.
- `hexos/agent/catalog.py:NATIVE_DESCRIPTIONS`: selección, argumentos y límites
  específicos de cada herramienta. `model_description` usa la descripción larga
  de `TOOLS` solamente cuando no hay una compacta. No se envían ambas juntas.
- `chat_backend/context.py`: datos del turno, perfil disponible, historial y
  traspaso. Las referencias históricas no son nuevas instrucciones.
- Ejecutores, verificadores y recuperación: garantías de permisos y resultados.
  Una instrucción al modelo no sustituye estas comprobaciones.

## Criterios de mantenimiento

No añadir al prompt general ejemplos de NAS, nombres de herramientas o arreglos
para una frase concreta. Las instrucciones específicas van junto a su herramienta.
Los avisos de cambios delicados pueden repetir la autorización general localmente.

Una aceptación se interpreta respecto a la propuesta pendiente, no mediante la
palabra «vale» aislada. Un equipo registrado se resuelve desde el inventario; uno
nuevo puede necesitar dirección y nombre. Las credenciales se solicitan por la
interfaz, no por el chat.

La extracción automática del perfil es condicional: requiere perfil, soporte del
runtime, pasar el filtro de afirmaciones y validación. El modelo no debe prometer
persistencia sin confirmación. El historial y el perfil son almacenes distintos.

## Alcance y validación

Esta reorganización modifica instrucciones nativas, no ejecutores, permisos,
esquemas, herramientas ofrecidas ni el protocolo JSON heredado. No modifica el
motor ni necesita compilarlo. Un backend ya iniciado necesita reiniciarse para
importar las nuevas instrucciones.

Las pruebas de catálogo protegen ubicación y presencia de reglas; no demuestran
obediencia del modelo. Tras pasar las pruebas automáticas, comprobar en conversación:

1. Saludar sin reabrir trabajos y aceptar una propuesta pendiente con «vale».
2. Consultar inventario frente a observar red sin guardar IPs.
3. Registrar dirección literal y nombre; conectar y diagnosticar tras el modal.
4. Consultar contenedores sin cambiar su estado.
5. Buscar y leer fuentes web, citando la página utilizada.
6. Recordar datos disponibles sin prometer guardados no confirmados.

Medir por separado caracteres del contrato, declaraciones renderizadas y tokens
del tokenizador real. Las reservas de contexto no son texto enviado al modelo.

## Lectura web antes de responder

Si una búsqueda nativa devuelve enlaces y aún no se ha intentado leer una fuente,
RecoveryController solicita una sola continuación con prefijo `web_read`. El
modelo elige la URL; argumentos y acceso pasan por los validadores habituales.
No cambia el catálogo (conserva el prefijo KV), no añade una generación y no
publica argumentos como texto provisional. Tras la lectura vuelve el streaming
normal. Una búsqueda vacía o fallida no fuerza lecturas; una lectura fallida deja
la recuperación habitual a cargo del agente. El guardado de evidencia al cierre
sigue vigente como respaldo. Esto no elimina los borradores de otras correcciones.

Validado con E4B real y fuentes simuladas en workspace temporal: search → read →
respuesta, cero previews entre búsqueda y lectura y streaming final activo.
