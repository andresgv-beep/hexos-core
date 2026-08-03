# E3 · paso 1 — el almacén de HERA

El `hera/src/hera.c` de enero no tenía ni un `fopen`: umbrales en RAM,
`hera_query_memories()` devolviendo vacío y la integración con memory_core
detrás de `#ifdef` apagados. No había nada que portar hacia él. Lo que hay ya
escrito de verdad es la memoria de `helios_chat.cpp` — `append_fact`,
`append_candidate`, `memory_is_duplicate` — y esa sabe **añadir líneas pero no
sustituirlas**. Es el punto 6 de su propia lista de deuda.

Este paso construye el almacén: `hera/include/hera_store.h` +
`hera/src/hera_store.c`.

## Las tres reglas las hace cumplir el tipo, no quien llama

**1 · Ningún recuerdo nace sin evidencia.** Un hecho solo se crea citando el id
de algo que la persona escribió, y el valor tiene que aparecer *literalmente*
en esas palabras. `hera_store_dijo()` es la única fuente de evidencia y solo
registra a la persona: si el modelo pudiera fabricar su propia cita, la regla
no valdría nada. No hay segunda puerta.

**2 · Corregir sustituye.** `hera_store_corregir()` crea el hecho nuevo y marca
el viejo `SUSTITUIDO` con el puntero al que lo reemplaza. Las dos filas siguen
en el diario. Corregir algo que nunca se supo se rechaza: una corrección sin
corregido es un hecho nuevo, y llamarlo corrección esconde que la memoria no
tenía lo que creías.

**3 · Los candidatos no son hechos.** `hera_store_confirmados()` — lo único que
puede alimentar un prompt — no devuelve candidatos jamás.

El diario (`hera.jsonl` en el perfil) es de **solo añadir**. Eso es lo que hace
auditable una corrección: si el fichero se pudiera reescribir, la auditoría
contaría lo que quisiera el último que escribió. Así se ve una corrección en
crudo:

```json
{"r":"dijo","id":"u1","texto":"mi perro se llama Byteazul"}
{"r":"hecho","id":"f1","clave":"perro/nombre","valor":"Byteazul","estado":"confirmado","evidencia":"u1"}
{"r":"dijo","id":"u2","texto":"me equivoqué, el perro se llama Rufo"}
{"r":"hecho","id":"f2","clave":"perro/nombre","valor":"Rufo","estado":"confirmado","evidencia":"u2"}
{"r":"sustituye","viejo":"f1","nuevo":"f2"}
```

## "Ana vive en Bilbao" es imposible por construcción

No por una comprobación que alguien pueda olvidar, sino porque no existe camino
para escribirlo. Los tres intentos, y los tres rechazos:

| Intento | Veredicto |
|---|---|
| sin citar nada | `sin_evidencia` |
| citando una evidencia inventada (`u99`) | `sin_evidencia` |
| citando algo real que sí habla de Ana pero nunca dice Bilbao | `no_literal` |

Y la trampa fina: si la comparación fuera por subcadena, `"Ana"` colaría dentro
de `"me comí una manzana"`. Se compara por **palabra completa**, y esa prueba
está en la batería.

## Barrera de E3 del plan

| Condición | Estado |
|---|---|
| Perfil vacío no recibe datos de otro perfil | ✅ prueba 6 — y no puede ni citando el id ajeno |
| Una corrección sustituye al hecho anterior y puede auditarse | ✅ prueba 3 |
| Los candidatos no entran en el prompt como hechos | ✅ prueba 4 |
| Reiniciar conserva exactamente el estado confirmado | ✅ prueba 5 |

**32 pruebas · 0 fallos.**

## La batería se ha visto fallar

Una batería que solo se ha visto pasar no demuestra nada — esta sesión ya me ha
enseñado tres veces que el instrumento miente antes que el código. `make
sabotaje` compila el almacén roto de tres formas y exige que se detecte:

| Sabotaje | Detectado |
|---|---|
| 1 · la comprobación de literalidad siempre dice que sí | 4 fallos |
| 2 · corregir añade en vez de sustituir (la legacy) | 4 fallos |
| 3 · los candidatos se cuelan entre los confirmados | 3 fallos |

## Compatibilidad de lectura, y su asterisco

`hera_store_importar_legacy()` lee `facts.md` y `candidates.md` del mismo perfil
una sola vez (deja marca en el diario, así que ni reiniciando duplica).

**Los hechos legacy entran sin evidencia**, marcados `origen:"legacy"` y con la
cita vacía. Nacieron antes de que existiera la regla e inventarles una cita
sería exactamente falsificar lo que la regla protege. Quedan visibles en la
auditoría para poder distinguirlos de un vistazo. La puerta solo lee esos dos
ficheros, no texto arbitrario, y solo se abre una vez: todo lo que nazca a
partir de ahora pasa por la regla 1 sin excepción.

`episodic.md` no se importa: son resúmenes de sesión, no hechos.

## Lo que falta para cerrar E3

1. `UserProfile` explícito y recuperación previa al turno (hoy la clave
   `sujeto/predicado` ya modela la relación, pero no hay ensamblado de prompt).
2. Separar recuperación previa al turno de reflexión posterior.
3. Cablear el almacén a la ruta `--runtime`.

Hasta que eso cierre, la ruta tipada sigue marcada **EXPERIMENTAL y sin
identidad persistente**, y así lo dice ahora al arrancar y en `--help`.
