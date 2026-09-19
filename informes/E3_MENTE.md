# E3 · pasos 2 y 3 — perfil, recuperación previa y MemoryDelta

> **Documento histórico / evidencia de una fase.** Sus pendientes y pruebas
> describen ese corte, no el producto actual. [Estado vigente](../IMPLEMENTATION_STATUS.md)
> (revisado 2026-09-19).

Tres piezas sobre el almacén ya aprobado. Las dos propiedades que había que
demostrar no son "funciona", son **"no hace lo que no debe"**.

## 1 · `UserProfile` como vista derivada

`hera_perfil_t` **no guarda nada**. Se calcula leyendo
`hera_store_confirmados()` cada vez que se pide. Con estado propio habría dos
versiones de la verdad y llegaría el día en que discreparan — y la que gobierna
el prompt sería la copia, no el diario auditable.

La `Relationship` del plan no es una tabla aparte: es la clave
`sujeto/predicado` leída por sus dos mitades. `yo/nombre` → sujeto `yo`,
predicado `nombre`. Cada relación conserva con qué palabras se supo y con
cuáles se confirmó.

**Solo consume CONFIRMADO.** No es un filtro al final: es que la única fuente
es `hera_store_confirmados()`. Los candidatos y el legacy en cuarentena no
salen de ahí.

Consecuencia que conviene decir en voz alta: **el nombre sale de un `yo/nombre`
confirmado, no del `facts.md` legacy ni del fichero `owner`**. En un perfil que
solo tenga memoria legacy, la ruta nueva no sabrá cómo te llamas hasta que lo
confirmes. Es el precio directo de la cuarentena que aprobamos, no un olvido.

## 2 · Recuperación previa, determinista y solo lectora

`hera_recuperar()` renderiza el perfil para el prompt. **No escribe.** Si
recuperar pudiera escribir, leer la memoria la cambiaría y dos turnos iguales
dejarían de dar lo mismo.

La prueba no se fía de la intención: **compara el diario byte a byte antes y
después**. El sabotaje 21 (recuperar deja una anotación) la rompe.

El recorte por presupuesto corta siempre **por hecho entero**: media frase de
memoria no es media memoria, es una frase distinta.

Un perfil nuevo devuelve cadena vacía. Hablar sin saber quién eres es correcto;
inventarlo, no.

## 3 · `MemoryDelta` — tipado, validado y **desconectado**

**No hay función de aplicar, y no es un olvido.** Mientras el cableado no
exista, una puerta que escriba es una puerta por la que se cuela algo sin que
nadie lo haya revisado.

Por qué tipado y no prosa: el fallo del 2026-07-31 fue que el destilador
escribió un relato entero en el diario y el modelo lo recitaba al día siguiente
como recuerdo. Con campos declarados eso es **inexpresable** — no existe el
campo "párrafo libre". Lo que el modelo no puede decir, no lo puede colar.

Cada operación se ensaya contra las reglas **reales**:

| Operación del delta | Veredicto |
|---|---|
| `perro/color = Rufo` citando "mi perro se llama Rufo" | `ok` |
| `ana/ciudad = Bilbao` citando algo que no habla de Ana | `sujeto_ajeno` |
| `yo/gusto = "no me gusta el café"` citando "me gusta el café" | `polaridad` |
| propuesta sin citar nada | `sin_evidencia` |
| `"op":"inventar"` | `desconocida`, no se ejecuta |

Y **ni siquiera la válida se escribe**: la prueba confirma que el diario no
cambia ni un byte. El sabotaje 22 (aplicar al leer) la rompe.

Los `hera_store_ensayar_*` **comparten camino** con las funciones de escritura
mediante una bandera interna, no son una copia de las reglas. Una validación
escrita aparte acabaría divergiendo, y un ensayo que dice que sí a algo que el
almacén rechaza no sirve para nada.

## Estado

**31 pruebas · 0 fallos** en la mente. Tres sabotajes, los tres detectados.
El almacén sigue en **59 · 0** con sus nueve sabotajes tras el refactor.

## Dos fallos propios que salieron probando esto

**La vista derivada no era byte a byte reproducible.** `snprintf` termina la
cadena pero deja el resto del buffer como estuviera, así que cada relación
arrastraba basura de pila detrás del terminador y dos derivaciones idénticas
salían distintas. Lo destapó la prueba de determinismo. Arreglado poniendo la
relación a cero antes de rellenarla — una vista derivada tiene que poder
compararse de un `memcmp`.

**Una prueba pasaba por el motivo equivocado.** El caso de polaridad citaba una
frase que no hablaba de gustos, así que saltaba antes el filtro de literalidad y
el veredicto era `no_literal`. Verde habría sido, pero no probando la polaridad.
Reescrita con una evidencia que sí habla de café.

## Lo que falta para cerrar E3

Solo el cableado opt-in. La ruta `--runtime` sigue marcada **EXPERIMENTAL y sin
identidad persistente** hasta que eso pase su propia revisión.
