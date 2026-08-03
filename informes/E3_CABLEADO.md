# E3 · cableado opt-in — memoria por la ruta real

La ruta `--runtime` ya lleva memoria. **29 pruebas · 0 fallos** contra un modelo
de verdad cargado (`tools/ruta_memoria_test.py`), que es lo único que el almacén
no podía demostrar solo.

## Las cuatro condiciones

### 1 · El bloque de perfil es efímero

Se compone en la pila de `rt_send` y muere ahí. No entra en el diario, ni en la
transcripción canónica, ni en nada que el usuario vea. La prueba busca la marca
`PERFIL DE LA PERSONA ACTUAL` en los tres sitios y exige no encontrarla.

La transcripción canónica guarda **solo lo que se dijo** — `user` y
`assistant`. Meter ahí el perfil o el contrato los volvería permanentes por la
puerta de atrás.

### 2 · El KV no se parchea: se reconstruye

Inyectar el perfil en cada turno no solo gasta contexto, **no borra nada**. Si
un hecho se corrige, el viejo sigue *físicamente* dentro del KV y el modelo lo
sigue atendiendo por mucho que le mandemos el nuevo detrás.

| Situación | Qué hace la ruta |
|---|---|
| Primer turno | inyecta el perfil como `system` efímero |
| Turnos siguientes, memoria igual | **no** repite el perfil, **no** resetea |
| Cambia una memoria confirmada | `reset` + turno rearmado con perfil vigente + transcripción canónica |

La prueba de corrección en caliente: se corrige `perro/nombre` con la CLI
mientras el servidor está vivo, y el turno siguiente trae `reset`, el perfil con
`Rufo`, **cero rastro de `Byteazul`**, y el modelo contesta el nombre corregido.

`hera_store_abrir()` se llama al entrar en cada turno. La memoria puede cambiar
desde fuera de la ruta — una CLI hoy, un demonio de consolidación mañana — y el
estado de HERA vive en RAM por proceso. Una ruta que solo leyera el diario al
arrancar seguiría sirviendo un hecho corregido hace una hora, que es justo el
fallo que E3 viene a cerrar.

### 3 · MemoryDelta en telemetría, sin aplicador

`POST /api/memoria/ensayo` devuelve los veredictos y `"aplicado": false`. La
prueba manda un delta con una operación válida y una envenenada
(`ana/ciudad = Bilbao`), comprueba el rechazo por `sujeto_ajeno` **y que el
diario no cambia ni un byte** — tampoco por la válida. No hay aplicador.

`GET /api/memoria` da el estado: nombre, confirmados, candidatos, sustituidos.
No expone el bloque de perfil: publicarlo sería un sitio más donde vive la
memoria sin reglas.

### 4 · Reinicio, corrección y aislamiento por la ruta real

| Prueba | Resultado |
|---|---|
| Reiniciar el servidor y volver a preguntar | sigue sabiendo el corregido, el sustituido no vuelve |
| Corregir dentro de una sesión | reconstruye y el modelo cambia de respuesta |
| Otro perfil (`HELIOS_HOME` distinto) | no sabe nada del primero, y no inyecta un bloque vacío |

## Otras comprobaciones

- **Conformidad del protocolo sobre la traza real**, ahora con `reset` y turnos
  que llevan historia: **0 violaciones**.
- **La legacy no se ha movido**: `oraculo.py --diff` contra la base de E1,
  **exit 0**, cero diferencias.

## `hera`, la CLI

En E3 no hay aplicador, así que la única forma de que un hecho nazca o se
corrija es que alguien lo pida. `hera/bin/hera` es ese alguien mientras tanto, y
pasa por la **misma API** que cualquier otro: no hay atajos.

```bash
U=$(hera dijo "guarda esto: mi perro se llama Rufo")
hera guarda perro/nombre Rufo "Su perro se llama Rufo" $U
hera lista --todo · hera historial perro/nombre · hera perfil
```

## Dos fallos propios, cazados por estas pruebas

**El primer turno mandaba un `reset` sobre un KV vacío.** Inofensivo, pero
dejaba el `reset` sin significado. Ahora solo se resetea si hay contexto que
tirar: que aparezca uno quiere decir exactamente una cosa — la memoria cambió.

**El `shutdown` se escribía sin trazarse**, así que su `result` salía en la
traza sin petición que lo justificara y la conformidad lo cantaba con razón.

## La frontera multiproceso

El almacén pasó a ser multiproceso en cuanto la CLI y HexOS lo tocaron a la
vez, y no tenía exclusión. La carrera:

```
HexOS relee (último u10)        hera dijo relee (último u10)
HexOS calcula u11               hera calcula u11
HexOS escribe u11               hera escribe u11
```

Dos evidencias distintas con el mismo id, y una corrección que cite `u11` se
lleva las palabras equivocadas — la clase exacta de fallo que este almacén
existe para hacer imposible.

**Dos capas de cerrojo, porque hacen falta las dos:**

- `flock` sobre `hera.lock` excluye entre **procesos**. Fichero aparte, no el
  diario, para que el truncado de la cola no se pelee con el descriptor que
  sostiene la exclusión.
- Un mutex recursivo excluye entre **hilos** del mismo proceso: `flock` se
  concede por descriptor abierto, así que dos hilos de HexOS lo "tendrían" los
  dos a la vez y no se excluirían en absoluto.

Relectura, validación, asignación de id y append ocurren **dentro del mismo
cerrojo exclusivo**. Partirlo en dos tramos es tener la carrera otra vez.

**El truncado de la cola solo bajo exclusivo.** Un lector con cerrojo
compartido la ignora y se va sin tocar el fichero: reparar mientras otro
proceso está a medio escribir es peor que la cola.

**Un cerrojo alrededor de `rt_send()` entero.** Con un hilo por conexión, dos
`POST /api/chat` simultáneos veían los dos `ENGINE_IDLE`, los dos pasaban el
filtro y los dos mandaban turno sobre el mismo KV. Mirar el estado y actuar en
consecuencia no puede ser dos pasos.

**Los retornos de HERA ya no se ignoran.** Si `hera_store_abrir()` o
`hera_store_dijo()` fallan, el turno **se rechaza** con aviso al usuario. Seguir
con un perfil vacío sería contestar como si no supiéramos nada de la persona sin
decir que la memoria está rota, y ese turno sería indistinguible de uno normal.

### Y la prueba se ha visto fallar

`make sabotaje-carrera` lanza 24 `hera dijo` en paralelo contra el almacén bueno
y contra uno compilado sin cerrojo:

```
con cerrojo:  24 ids únicos
sin cerrojo:  solo 16 ids únicos (la carrera se reproduce)
```

Si el saboteado también diera 24, la prueba no estaría probando el cerrojo.

## Deuda anotada, no bloqueante

- El parser de `MemoryDelta` debe endurecerse (cierre del array, basura fuera de
  esquema, más de 32 operaciones) **antes** de activar reflexión real.
- Si una línea del diario supera el buffer, se conserva el fichero y se deja de
  leer: endurecimiento pendiente frente a corrupción externa.
- La transcripción canónica se corta a 64 turnos; al reconstruir se pierden los
  más viejos y se avisa por `notice`. La compactación de verdad es otro asunto.

La ruta sigue marcada **EXPERIMENTAL**, pero ya no por falta de identidad
persistente: es porque la reflexión sigue desconectada.
