# E3 · paso 1 — el almacén de HERA

> **Documento histórico / evidencia de una fase.** Sus pendientes y pruebas
> describen ese corte, no el producto actual. [Estado vigente](../IMPLEMENTATION_STATUS.md)
> (revisado 2026-09-19).

El `hera/src/hera.c` de enero no tenía ni un `fopen`. Lo que hay escrito de
verdad es la memoria de `helios_chat.cpp` — `append_fact`, `append_candidate`,
`memory_is_duplicate` — y esa sabe **añadir líneas pero no sustituirlas**. Es el
punto 6 de su propia lista de deuda.

Este paso construye el almacén: `hera/include/hera_store.h` +
`hera/src/hera_store.c`.

## Cuatro reglas que hace cumplir el tipo, no quien llama

**1 · Ningún recuerdo nace sin evidencia, y la evidencia cubre la frase entera.**
En UNA MISMA FRASE de algo que la persona escribió tienen que aparecer el
sujeto, el valor y la misma polaridad. `hera_store_dijo()` es la única fuente de
evidencia y solo registra a la persona: si el modelo pudiera fabricar su propia
cita, la regla no valdría nada.

**2 · Proponer y confirmar son puertas distintas.** `hera_store_proponer()` solo
crea candidatos y **no tiene parámetro** para ascender nada. Confirmar exige el
id de una intervención registrada de la persona, y esa cita queda guardada en el
hecho: después se puede preguntar "¿por qué crees esto?" y contestar con sus
palabras exactas.

**3 · Corregir sustituye, en un solo evento.** La corrección es UNA línea del
diario que crea el nuevo y jubila el viejo a la vez. Si el proceso muere
escribiéndola, la cola incompleta **se borra del disco al abrir**: ignorarla no
bastaba.

**4 · Los candidatos no son hechos** — y ahí entra todo lo importado del almacén
legacy.

El diario (`hera.jsonl`) es de **solo añadir**: si el fichero se pudiera
reescribir, la auditoría contaría lo que quisiera el último que escribió.

## Los cuatro refuerzos de la revisión

### Migración legacy en cuarentena

`facts.md` tiene hechos falsos e identidades inventadas. Importarlo como
autoridad mudaría la contaminación vieja al almacén nuevo y dejaría la regla 1
en un adorno: bastaría con haber ensuciado el fichero antes. **Todo entra como
`CANDIDATO` con origen `legacy` y sin cita**, y `hera_store_confirmados()` no lo
devuelve jamás hasta que la persona lo confirme una a una — y entonces ya tendrá
su evidencia. La legacy sigue leyendo sus ficheros exactamente como antes.

### Corrección atómica, y la cola borrada

Antes eran dos escrituras: crear el nuevo, después jubilar el viejo. Una caída
entre ambas dejaba dos confirmados contradiciéndose. Ahora es un registro
`{"r":"corrige","viejo":"f1","id":"f2",...}`, y la relectura **descarta entera**
toda línea que no venga terminada en `\n`.

Descartarla no bastaba. La cola seguía en disco, la siguiente escritura se
pegaba justo detrás, y en el reinicio siguiente esa mezcla se leía como un
registro terminado: **la corrección abortada resucitaba y el recuerdo nuevo se
perdía dentro de ella**. Ahora el diario se trunca físicamente hasta el último
registro completo.

Con una cautela: si una lectura LLENA el buffer sin ver `\n`, eso es
indistinguible de una cola incompleta, y truncar ahí se comería datos buenos.
En ese caso se para sin tocar nada. El buffer es cuatro veces el registro más
largo que el almacén puede escribir, así que el caso no debería darse — pero
"no debería" no es razón para arriesgar el diario.

### Autoridad de confirmación

| API | Qué hace |
|---|---|
| `proponer(clave, valor, texto, evidencia)` | siempre CANDIDATO — no hay forma de pedir otra cosa |
| `registrar(..., evidencia, confirmacion)` | confirmado de una, para "guarda en memoria: …" |
| `confirmar(id, confirmacion)` | asciende; exige intervención registrada **distinta y posterior** a la que originó el candidato |
| `corregir(clave, valor, texto, evidencia, confirmacion)` | un solo evento |

La confirmación tiene que ser **posterior**: aceptar la misma frase sería
contarse a sí mismo — de "creo que me mudo a Girona" saldrían el candidato y su
propia confirmación, y una extracción del modelo quedaría confirmada sin que
nadie asintiera. Que un "sí, guárdalo" signifique de verdad asentimiento es cosa
del CK; el almacén solo exige que exista un turno posterior al que señalar.

### Sujeto y polaridad, no solo el valor

De **"Luis vive en Bilbao"** no sale `ana/ciudad = Bilbao`: "ana" no está en esa
frase. De **"me gusta el café"** no sale "no me gusta el café": la negación es de
dos letras y se caía de cualquier filtro por longitud.

El sujeto reservado `yo` es el único que no necesita aparecer escrito — quien
dice "vivo en Sevilla" no se nombra, pero es el autor del texto y eso lo
acredita.

La comprobación de polaridad es **deliberadamente burda y rechaza de más**: en
"no tengo perro pero me gusta el café", el valor "me gusta el café" se rechaza
porque la frase lleva un "no" que era de otra cosa. Se acepta ese coste. Un
rechazo de más significa que el dato no se guarda solo y la persona puede
pedirlo a mano; un rechazo de menos significa guardar lo contrario de lo que
dijo y repetírselo mañana como si lo hubiera dicho ella.

## Barrera de E3 del plan

| Condición | Estado |
|---|---|
| Perfil vacío no recibe datos de otro perfil | ✅ prueba 10 — ni citando el id ajeno |
| Una corrección sustituye al hecho anterior y puede auditarse | ✅ pruebas 6 y 7 |
| Los candidatos no entran en el prompt como hechos | ✅ pruebas 8 y 11 |
| Reiniciar conserva exactamente el estado confirmado | ✅ prueba 9 |

**59 pruebas · 0 fallos.**

## Las cinco fronteras pedidas

| Frontera | Prueba |
|---|---|
| `Luis vive en Bilbao` no autoriza `ana/ciudad = Bilbao` | [3] `sujeto_ajeno` |
| `me gusta el café` no autoriza `no me gusta el café` | [4] `polaridad` |
| Caída entre las dos partes de una corrección | [7] queda 1 confirmado, el de antes |
| Confirmar sin intervención registrada | [5] `sin_confirmacion` |
| Legacy contaminado nunca aparece como confirmado | [11] 0 confirmados de 4 importados |
| La corrección abortada no resucita tras escribir encima | [7] se corta, se reinicia, se escribe, se reinicia |
| La frase que originó el candidato no vale de confirmación | [5] `sin_confirmacion` |

## La batería se ha visto fallar

`make sabotaje` compila el almacén roto de nueve formas y exige que se detecten.
Cada una rompe **exactamente** la frontera que le toca:

| Sabotaje | Rompe |
|---|---|
| 1 · el respaldo siempre dice que sí | 7 pruebas |
| 2 · corregir vuelve a ser dos escrituras | las 2 de la caída a media corrección |
| 3 · los candidatos se cuelan | 8 pruebas |
| 4 · no se comprueba el sujeto | las 2 de "Luis vive en Bilbao" |
| 5 · se ignora la polaridad | las 2 del café y el té |
| 6 · confirmar no exige autoridad ninguna | 4 pruebas de autoridad |
| 7 · el legacy envenenado entra como autoridad | 4 pruebas de cuarentena |
| 8 · confirmar acepta la frase que originó el candidato | las 2 de la confirmación posterior |
| 9 · la cola incompleta se ignora pero no se borra | la de la corrección resucitada |

**Y la puerta se endureció**, porque se tragaba fallos: un sabotaje que moría por
segfault no imprimía nada y `make sabotaje` seguía diciendo OK. Ahora un
sabotaje que no compila, que muere o que no se detecta hace fallar la puerta con
código de error. Es el mismo defecto que ya tuvo cuando corría tres de siete: un
gate que no comprueba lo que dice comprobar es peor que no tenerlo.

## Lo que falta para cerrar E3

1. `UserProfile` explícito y recuperación previa al turno.
2. Separar recuperación previa al turno de reflexión posterior.
3. Cablear el almacén a la ruta `--runtime`.

Hasta que eso cierre, la ruta tipada sigue marcada **EXPERIMENTAL y sin
identidad persistente**, y así lo dice al arrancar y en `--help`.
