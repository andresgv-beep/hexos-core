# E4 · registro y API de chats en HexOS

**29 pruebas · 0 fallos** contra el servidor y el motor de verdad. La UI queda
para después, como pediste.

## Primero: la causalidad de `session_paused`

Tenías razón. El lector anunciaba la pausa al **pedir** la cancelación, cuando
la sesión todavía estaba terminando su token: en ese instante se está
pausando, no está pausada. Ahora el lector solo señala y el hilo dueño confirma
cuando `run_turn` ha vuelto. El orden que ve quien lee la traza es el orden de
lo que pasó:

```
text_delta A …
completed A: cancelled
session_paused A: switch
turn de B
```

La prueba exige las dos mitades: que el terminal de A salga **antes** del
`session_paused`, y que después no llegue ni un token más de A. Con el grifo
`HELIOS_PAUSA_TEMPRANA` —que reproduce el fallo— la primera falla.

Un matiz honesto: de las dos, la que caza el fallo de forma fiable es la del
orden. La de "no llegan más tokens" depende de cuánto tarde la cancelación en
morder, así que a veces pasa aunque el bug esté.

## El registro

`chats.jsonl` en el perfil, de solo añadir y con el mismo cerrojo que HERA.
Campos: `chat_id`, `titulo`, `creado`, `actualizado`, `activo`,
`sesion_viva`, transcripción. Un dueño, sin cuentas.

**`sesion_viva` no se persiste, a propósito.** Al arrancar es falso para todos
porque Héctor acaba de nacer y no tiene ninguna sesión. Guardarlo sería
prometer un KV que no existe, y el primer turno lo descubriría contestando sin
contexto.

## Tres estados que no son el mismo

| | |
|---|---|
| **activo** | el chat que se mira. Solo uno |
| **sesión viva** | Héctor tiene su KV cargado |
| **existe** | está en el registro con su transcripción |

Cambiar de chat **no cierra** el anterior: queda pausado con su KV vivo, y
volver sigue la conversación. Cerrar libera el KV y conserva el chat. Borrar es
otra cosa y se pide aparte.

## La API

| | |
|---|---|
| `POST /api/chats` | crear (cuerpo = título) |
| `GET /api/chats` | listar, del más reciente al más viejo |
| `GET /api/chats/<id>` | el chat con su transcripción |
| `POST /api/chats/<id>/activar` | activar |
| `POST /api/chats/<id>/cerrar` | liberar KV, conservar conversación |
| `DELETE /api/chats/<id>` | borrar |

`/api/chat` sigue funcionando: manda al chat activo, y si no hay ninguno lo
crea. La ruta antigua no se ha movido.

## Un hueco que salió al probar

**Activar otro chat no bastaba con cambiar un puntero.** Si el motor estaba
generando, seguía ocupado y el chat nuevo recibía un `409`: la persona
esperando a una respuesta que ya no mira. Ahora activar **cancela** lo que
hubiera en vuelo — eso es lo que hace que "pausar" signifique algo. Lo emitido
se conserva y se guarda en su chat.

## Y dos fallos míos que las pruebas destaparon

**Aliasing en `rt_send`.** Guardaba `const char *chat = chats_activo()`, que
devuelve el buffer estático del registro. Al activar otro chat desde el hilo
HTTP, esa variable local **cambiaba de valor sola** a mitad del turno y lo
dicho se anotaba en el chat equivocado. Ahora se copia. Solo aparece si
cambias de chat mientras genera — que es el caso normal, no el raro.

**Orden de evaluación indefinido** en el `cancel`: `++g_seq` y `g_seq - 1` en
la misma expresión. El objetivo se calcula ahora antes de tocar el contador.

## Y tres veces mi propia prueba estaba mal

Van aquí porque el patrón ya es un clásico de esta sesión.

- **`b""` es falsy en Python**, así que mi cliente deducía `GET` para todas las
  acciones sin cuerpo: ninguna activación ocurría y la prueba "fallaba" por su
  propio cliente. Nueve falsos negativos.
- **Asumía que dos segundos de generación dan texto visible.** Con un modelo
  que piensa antes de hablar, eran todo razonamiento: no había nada parcial que
  conservar y la prueba comprobaba otra cosa. Ahora espera a que haya texto.
- **Daba por cancelado un turno que había terminado solo**, así que la
  comprobación de "un turno cancelado no se encola" no probaba nada.

## Los siete puntos de tu barrera

| | |
|---|---|
| A y B recuerdan solo lo suyo | ✅ |
| cambiar y volver conserva el KV vivo | ✅ no se reenvía transcripción ni hay reset |
| reiniciar el runtime reconstruye desde transcripción | ✅ |
| cerrar libera KV pero no borra el chat | ✅ |
| borrar borra solo el elegido | ✅ |
| lo cancelado a medias queda representado honestamente | ✅ |
| `perfil/sesion/turno` llega a la cola | ✅ y un turno cancelado **no** se encola |
| `/api/chat` antigua sigue funcionando | ✅ |

Encolar **no ejecuta nada**: no hay trabajador. Y va después de emitir el
texto, así que no retrasa la respuesta.

## El protocolo aprendió que hay sesiones

`inv6` seguía una **única** línea de posición del KV. Con varias sesiones, dos
chats con posiciones distintas la habrían roto siempre. Ahora la sigue **por
sesión**, y un `session_close` confirmado autoriza la bajada igual que un
`reset`: liberar el KV es su razón de ser, no una anomalía.

## Estado

| | |
|---|---|
| Chats (servidor + motor) | 29 · 0 |
| Conmutación en el runtime | 21 · 0 |
| Aislamiento de sesiones (C++) | 19 · 0 |
| Ruta tipada con memoria | 29 · 0 |
| HERA: almacén / mente / cola | 59 · 31 · 31, 18 sabotajes, 21 puertas con cerrojo |
| Conformidad del protocolo | 0 violaciones |

Falta la UI.
