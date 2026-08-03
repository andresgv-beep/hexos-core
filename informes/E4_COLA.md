# E4 · paso 1 — cola durable, sin trabajador

**31 pruebas · 0 fallos**, cinco sabotajes y una carrera de trabajadores de
verdad. No hay nada que ejecute un job, y eso no es una fase a medias: la cola
tiene que ser demostrablemente durable e idempotente **antes** de que algo
escriba a partir de ella. Al revés, un fallo de la cola y un fallo del
trabajador se confunden y no hay forma de saber cuál duplicó un recuerdo.

## Lo que cubre, de tus condiciones

| # | Condición | Cómo |
|---|---|---|
| 3 | identidad `perfil/sesion/turno`, idempotente | encolar el mismo turno tres veces deja **un** job y **una** línea en el diario |
| 3 | reinicio recupera sin duplicar | prueba [2] y [4] |
| 4 | entrada congelada | mensaje, respuesta visible, `acto`/`registro`/presupuestos, evidencia y hash del perfil |
| 4 | nunca contratos ni razonamiento | **no existen los campos**, igual que en `MemoryDelta` |
| 9 | fallar no bloquea la cola | reintentos contados en el diario, luego `fallido`, y el siguiente pasa |
| 10 | telemetría sin contenido privado | solo recuentos por estado; la prueba busca el texto del recuerdo y exige no encontrarlo |

Un turno más largo del máximo **se rechaza, no se recorta**: reflexionar sobre
media respuesta es reflexionar sobre otra cosa.

## El defecto que destapó la carrera de trabajadores

Al abrir, la recuperación devolvía a `pendiente` **todo** job en `tomado`, sin
distinguir dos situaciones que sobre el papel se parecen:

- el trabajador murió → hay que devolverlo a la cola;
- el trabajador **sigue trabajando** → tocarlo es robárselo, y entonces dos
  reflexionan el mismo turno y el recuerdo se duplica.

Con doce trabajadores reales: **12 tomados · 4 distintos**. Cada proceso que
abría la cola le robaba el job al anterior.

Ahora cada job tomado guarda su dueño, `<boot_id>:<pid>`:

| Situación | Qué hace |
|---|---|
| proceso vivo | no se toca: está trabajando |
| proceso muerto | abandonado, vuelve a la cola con un intento más |
| `boot_id` distinto | la máquina se reinició, todos muertos |

El `boot_id` no es adorno: sin él, tras un reinicio un pid reutilizado por
cualquier otro programa haría que un job abandonado pareciera vivo para
siempre. Con la marca: **12 tomados · 12 distintos**; sin ella, 5.

Hacen falta procesos **exec'd**, no `fork`: tras un fork los hijos comparten la
misma descripción de fichero y `flock` no excluiría entre ellos — la prueba
pasaría sin probar nada.

## Tres pruebas que pasaban sin probar

Van aquí porque el patrón se repite y conviene tenerlo escrito.

**La recuperación se probaba reabriendo en el mismo proceso.** El dueño seguía
vivo, así que no era una caída: era exactamente el caso en que la cola debe
*no* tocar el job. Ahora un proceso hijo toma el job y muere de verdad.

**La idempotencia estaba en dos sitios y uno tapaba al otro.** Al escribir (no
se anota una línea repetida) y al releer (una línea repetida no crea otro job).
Desactivando solo la primera, la segunda mantenía la cuenta cuadrada mientras
el diario crecía sin fin. Ahora hay una prueba por guarda: una cuenta las
líneas del diario, la otra parte de un diario que ya trae la línea repetida —
que es lo que pasaría al leer un fichero escrito por una versión con el bug.

**El gate de carrera del almacén exigía 24 hechos también en la rama
saboteada.** Ahí perder escrituras *es* la carrera manifestándose, así que la
guarda hacía fallar la puerta por el motivo contrario al que buscaba.

## El auditor de cerrojos, ahora sobre los dos ficheros

`make auditar` cubre `hera_store.c` (14 puertas) y `hera_queue.c` (7). Señaló
tres puertas de la cola en cuanto existió: eran las exentas equivalentes a las
del almacén, y ahora están en la lista con su motivo por escrito.

## Estado

| | |
|---|---|
| Cola | 31 · 0, cinco sabotajes, carrera de 12 trabajadores |
| Mente | 45 · 0, cuatro sabotajes |
| Almacén | 59 · 0, nueve sabotajes, carrera multiproceso |
| Auditor | 21 puertas, cero sin cerrojo |
| Ruta real | 29 · 0 |

## Lo que NO está hecho

Todo lo demás de E4. En concreto: no hay trabajador, no se encola desde la ruta
(la condición 1 —solo tras un `completed` normal— aún no tiene dónde
aplicarse), no hay sesión de inferencia aislada, no hay autoridad por origen y
no hay checkpoint. La cola es una caja durable y vacía, que es justo lo que
tocaba.
