# E4 · UI de chats

> **Documento histórico / evidencia de una fase.** Sus pendientes y pruebas
> describen ese corte, no el producto actual. [Estado vigente](../IMPLEMENTATION_STATUS.md)
> (revisado 2026-09-19).

**36 pruebas · 0 fallos** contra el servidor y el motor de verdad. Héctor no se
ha tocado.

## Los nombres, que era lo importante

| Acción | Qué hace | Qué NO hace |
|---|---|---|
| `+ Nuevo chat` | crea y activa | no usa GPU: no hay sesión hasta escribir |
| pulsar un chat | lo activa; para el anterior si generaba | no reconstruye nada |
| `Liberar memoria` | suelta el KV de la GPU | no toca la conversación |
| `Eliminar chat` | borra la conversación, con confirmación | — |

«Cerrar chat» no aparece por ningún lado. El diálogo de eliminar dice
literalmente qué desaparece y remata con *"si solo querías soltar la GPU, usa
«Liberar memoria»"*: nadie debería borrar una conversación creyendo que liberaba
VRAM.

Eliminar está separado en el menú, por debajo de una línea y en rojo apagado.

## Detalles que pediste

- **Título sin gastar inferencia**: primera línea del primer mensaje, recortada
  a 42 caracteres. Un título puesto a mano **no lo pisa** el automático.
- **Chat activo marcado** con `●` y fondo elevado.
- **Respuesta detenida**: se conserva y se pinta con *"— detenida al cambiar de
  chat"*. Enseñarla como si estuviera entera sería mentir sobre lo que dijo.
- **Volver a un chat liberado no reconstruye al seleccionarlo**, sino al
  enviar. Seleccionar tiene que ser gratis, o mirar la lista costaría GPU.
- **Marca `KV`** en los chats cuya memoria está cargada. Una sesión pausada
  sigue gastando VRAM, y eso es lo que decide cuántos chats caben.

## Tres bugs reales que salieron al conectar la UI

**Un `POST` sin `Content-Length` recibía 413.** La regla venía de cuando todo
POST traía carga y un tamaño sin declarar era un riesgo. Pero las acciones de
un chat no llevan cuerpo, y la UI las manda con `fetch(..., {method:'POST'})`
sin body — **ninguna activación funcionaba**. Ahora un POST sin la cabecera es
un POST sin cuerpo; se sigue rechazando un `Content-Length` excesivo, que es lo
que la regla protegía de verdad.

**`recargar()` borraba la marca de sesión viva.** Se llama en cada mutación, así
que crear un chat apagaba el KV de todos los demás a ojos de HexOS: cada turno
habría reconstruido el contexto desde la transcripción y *"cambiar y volver
conserva el KV"* habría dejado de ser cierto **sin que nada fallara a gritos**.
Ahora se conserva al releer, y solo se limpia al abrir — que es el único
momento en que todas son falsas de verdad, porque Héctor acaba de nacer.

**Un título puesto al crear lo sobrescribía el automático**, porque el chat que
recibía los mensajes no era el que yo creía: consecuencia del 413 de arriba.

## Y el mismo error mío por tercera vez

`pedir()` en la prueba deducía el método de si había cuerpo, y `b""` es falsy en
Python: las acciones salían como `GET`, el servidor no hacía nada y la prueba
culpaba al código. Ya me mordió dos veces antes. Esta vez no lo he arreglado
llamada a llamada: **un `GET` a una acción ahora lanza excepción**. Un fallo que
se repite tres veces no es mala suerte, es una herramienta con un filo mal
puesto.

## Tu batería mínima

| | |
|---|---|
| crear A y B, datos distintos | ✅ |
| cambiar entre ambos durante una generación | ✅ y el texto parcial se conserva marcado |
| cada texto en su chat correcto | ✅ |
| liberar A y seguir en la lista | ✅ |
| volver a A y reconstruir | ✅ al enviar, no al seleccionar |
| eliminar B, A intacto | ✅ |
| reiniciar y recuperar lista, activo y transcripciones | ✅ |
| `perfil/sesion/turno` a la cola | ✅ un turno cancelado no se encola |

## Estado

| | |
|---|---|
| Chats + UI | 36 · 0 |
| Conmutación en el runtime | 21 · 0 |
| Aislamiento de sesiones (C++) | 19 · 0 |
| Ruta tipada con memoria | 29 · 0 |
| HERA (almacén/mente/cola) | 59 · 31 · 31, 18 sabotajes, 21 puertas |
| Conformidad del protocolo | 0 violaciones |

Con esto el sistema de chats local queda cerrado: pesos únicos, sesiones
aisladas, pausa real, persistencia y reconstrucción. Vuelta al eje de E4, el
trabajador de reflexión.
