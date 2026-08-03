# E4 · subhito — varios chats, uno activo

Héctor ya multiplexa sesiones y HexOS puede tener varios chats con uno solo
activo. **19 pruebas de conmutación contra el runtime real · 0 fallos**, además
de las 19 de aislamiento en C++.

Héctor sigue sin saber qué es un chat: recibe un `session` en el mensaje y
mantiene esa conversación. Quién es el chat visible lo decide HexOS.

## Las reglas, y dónde se cumple cada una

| Regla | Cómo |
|---|---|
| solo uno activo | el runtime procesa turnos en serie; nunca hay dos generando |
| interactuar con otro pausa el actual | al llegar trabajo para otra sesión, se cancela la que genera |
| pausar conserva KV, muestreador y posición | pausar es **no llamar a `run_turn`**; no hay nada que reiniciar |
| no reinicia ni reconstruye | probado: al volver, el caché sigue donde estaba y la conversación continúa |
| las pausadas no usan GPU | solo se ejecuta dentro de `run_turn`, y solo una a la vez |
| cancelación segura al cambiar | la cancelación que ya existía: para en un límite de token y conserva lo emitido |
| sin ejecución simultánea | el cerrojo del `Model` lo impide por construcción |

`session_paused` lleva el motivo (`switch`) y el validador **exige que el
motivo esté declarado**: mañana no se cuela otro sin que nadie lo apruebe.

## Lo que digo en vez de dejarlo implícito

**Pausar no libera VRAM.** Una sesión pausada no ejecuta nada, pero su KV sigue
ocupando memoria. Ese es el techo real al número de chats abiertos, no la CPU
ni la GPU. Conviene saberlo ahora y no descubrirlo con un OOM cuando alguien
abra el décimo chat.

**Cerrar un chat sí lo libera**, y empezar otro con el mismo nombre arranca en
blanco — probado, para que nadie cuente con que el KV viejo "sigue por ahí".

## El protocolo viejo no se ha movido

`session` es **opcional**. Un `turn` sin ese campo va a la sesión por defecto,
que es exactamente lo que hacía antes. La prueba lo comprueba explícitamente, y
la ruta tipada de E3 sigue pasando entera sin tocar una línea.

## Dos fallos propios, cazados por las puertas

**`session_opened` salía antes que `ready`.** Creaba la sesión por defecto
durante el arranque, y eso rompe el invariante 1 del protocolo: `ready` es el
primer evento, siempre. Ahora la sesión por defecto se abre justo después.

**Y una prueba mía pasaba sin probar nada.** La de "una sesión pausada no
ejecuta nada" filtraba eventos por un `request_id` con prefijo `"rA"` que
ningún id tenía: la lista salía vacía y la comprobación se cumplía sola. Ahora
compara contra el id real del turno en curso. De paso reforcé la de
conmutación: no basta con que el runtime **anuncie** la pausa, el turno largo
tiene que terminar con `finish_reason: cancelled` — si no, la prueba pasaría
igual con un turno que simplemente hubiera acabado solo.

## Estado

| | |
|---|---|
| Conmutación de chats (runtime real) | 19 · 0 |
| Aislamiento entre sesiones (C++) | 19 · 0 |
| Ruta tipada con memoria, extremo a extremo | 29 · 0 |
| Conformidad del protocolo (fixtures y traza real) | 0 violaciones |

## Lo que sigue sin existir

El trabajador de reflexión, el encolado desde la ruta, la autoridad por origen
y el checkpoint. La cola durable sigue vacía y esperando. Y la UI de varios
chats es de HexOS: el motor ya sabe hacer su parte.
