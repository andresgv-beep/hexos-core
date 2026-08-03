# E4 · trabajador de reflexión — SOLO ENSAYO

**22 pruebas · 0 fallos.** El trabajador corre, evalúa y **no escribe nada**.

```
salida del modelo → parsear → ensayar → telemetría
                                      ✗ aplicar
```

No hay aplicador, y su ausencia no es un descuido: mientras no exista una
puerta demostrada delante, dar autoridad a una extracción del modelo es lo que
esta evacuación lleva media docena de rebanadas impidiendo.

## Cómo trabaja

Toma el pendiente más antiguo, lo ejecuta en la sesión reservada
`hera:reflection` —que no está en el registro de chats, así que **no puede**
salir en la barra lateral— y la resetea **antes y después**. Cada trabajo es
una evaluación independiente: dos jobs seguidos no comparten KV ni muestreador.

Solo ve el renderer de reflexión y la entrada congelada. Ni identidad, ni
memoria, ni el contrato del chat: un trabajo de reflexión no es una
conversación y no debe parecerlo.

Sus eventos no tocan el canal del usuario. Ni SSE, ni burbujas, ni el estado
del motor — si la reflexión moviera el estado a "escribiendo", la UI diría que
Héctor contesta algo que nadie preguntó.

## `aplazado`: una preempción no es un fallo

Estado nuevo de la cola. Si llega un turno visible, la reflexión se corta, el
job vuelve a **pendiente**, **no gasta intento** y **no cuenta como fallo**.
Usar `fallido` habría hecho que un rato de conversación agotara los intentos de
un trabajo perfectamente sano y lo diera por imposible.

La prueba lo aplaza más veces que intentos hay y comprueba que sigue vivo; y
que después puede fallar de verdad sus tres veces. En la corrida completa:
**2 aplazados, 0 reintentos**.

## Dos cosas que hubo que medir, no suponer

**Con presupuesto de pensamiento CERO, el modelo razona en voz alta.** La
respuesta salía llena de deliberación en inglés y el parser la rechazaba
entera — correctamente, pero el camino bueno nunca se demostraba. Darle sitio
donde pensar es lo que hace que lo visible sea solo el delta. Lo que piense no
se guarda ni se mira: el job no tiene campo para ello.

**El ejemplo del renderer se copiaba tal cual.** Con marcadores
(`"valor":"dato"`), el modelo los devolvía literalmente. El ensayo los
rechazaba por `no_literal` — la red aguantó — pero el trabajador no producía
nada útil. Con un ejemplo trabajado y ajeno, sale lo que toca: **2 operaciones,
2 aceptables, 0 aplicadas**.

## Tu barrera

| | |
|---|---|
| diario idéntico byte a byte | ✅ |
| nada de la reflexión en chat, SSE ni transcripción | ✅ |
| un chat interrumpe y responde normal | ✅ |
| el job interrumpido conserva sus intentos | ✅ |
| dos jobs seguidos no comparten KV ni sampler | ✅ reset antes y después |
| un delta corrupto no escribe ni atasca | ✅ |
| matar el trabajador recupera el job | ✅ por la cola durable |
| telemetría con recuentos y tiempos, cero contenido | ✅ |
| la sesión reservada nunca sale en la sidebar | ✅ |
| los chats conservan comportamiento y contexto | ✅ 36 · 0 |

## Y otra vez mi propia prueba

Cuarta vez en esta batería: comparaba el diario contra una foto **anterior a
varios turnos de chat**, y cada turno visible escribe su evidencia. Eso lo
escribe el chat, no el trabajador. La foto tiene que tomarse justo antes de la
ventana en la que solo actúa la reflexión. Queda escrito en el propio test.

También estaba **trazando un marcador en vez del `reset` real**, y el de cierre
no se trazaba. Una traza que dice otra cosa es peor que no tenerla, porque se
usa para demostrar propiedades — ya me pasó con el `shutdown`.

## Anotado, no arreglado

Matar HexOS de golpe deja vivo a `helios_runtime` unos segundos: vive en su
propia sesión y se entera por el EOF de su entrada. Se apaga solo, pero
mientras tanto retiene la VRAM y un arranque inmediato compite por ella.

## Estado

| | |
|---|---|
| Reflexión (solo ensayo) | 22 · 0 |
| Chats + UI | 36 · 0 |
| Ruta tipada con memoria | 29 · 0 |
| HERA: almacén/mente/cola | 59 · 31 · 34, 18 sabotajes, 22 puertas |

Siguiente rebanada: el aplicador limitado a candidatos.
