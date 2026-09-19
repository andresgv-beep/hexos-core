# E4 · condición 1 — el parser de `MemoryDelta`, estricto

> **Documento histórico / evidencia de una fase.** Sus pendientes y pruebas
> describen ese corte, no el producto actual. [Estado vigente](../IMPLEMENTATION_STATUS.md)
> (revisado 2026-09-19).

Primera condición de E4: endurecer el parser antes de que la salida de un
modelo entre por él. **45 pruebas · 0 fallos** en la mente, cuatro sabotajes.

## La línea: esquema todo o nada, semántica por operación

Son dos cosas distintas y conviene no mezclarlas:

| | Qué es | Qué pasa |
|---|---|---|
| **Esquema** | array sin cerrar, clave desconocida, verbo inventado, campo obligatorio ausente, valor que no cabe, elemento que no es objeto, clave repetida, basura detrás, más de 32 ops | **tumba el delta entero**, `motivo` dice cuál |
| **Semántica** | sin evidencia, sujeto ajeno, polaridad, duplicado | verdicto **por operación**, el delta sigue válido |

El motivo de la primera columna: si algún día hay aplicador, **aplicar la mitad
buena de un delta corrupto es peor que no aplicar nada** — no se sabe qué se
perdió en la mitad ilegible. Un rechazo entero es una señal; media aplicación
es una memoria con un agujero que nadie puede localizar.

Los veredictos semánticos solo se piden **después** de validar el esquema
entero. Al revés, un campo que falta produciría un `sin_evidencia` que esconde
un error de formato tras un rechazo que parece normal.

## Lo que se ha quitado de en medio

El parser viejo buscaba las claves con `strstr` y troceaba el array contando
llaves. Leía bien un delta bien escrito, y también leía "bien" media docena de
cosas que no lo eran. Ahora es un escáner que respeta strings y escapes desde el
primer byte.

La trampa que mejor lo resume, y que ahora es una prueba:

```json
{"nota": "escribe un \"memory_delta\" en el informe"}
```

El parser viejo habría encontrado esa cadena con `strstr` y habría intentado
leer un array donde solo había una frase. Ahora `memory_delta` solo cuenta si
es una **clave de nivel superior**.

Otras dos que valen la pena:

- **Un valor que no cabe se rechaza, no se recorta.** Guardar `"Rufo de la casa
  gr"` por `"Rufo de la casa grande"` es la clase de mentira pequeña que
  después nadie sabe de dónde salió.
- **Más de 32 operaciones se rechaza**, no se trunca en silencio con las 32
  primeras.

Escapes `\u` no se admiten: nadie los emite en este esquema y aceptarlos a
medias sería peor que no aceptarlos.

## La batería se ha visto fallar

El sabotaje 23 devuelve el parser a laxo (acepta claves desconocidas, deja pasar
campos obligatorios ausentes, recorta en silencio, tolera un array sin cerrar).
Rompe cinco pruebas.

**Un matiz honesto sobre dos de los casos.** Los fixtures de "array sin cerrar"
y "más de 32 operaciones" también los caza la guarda de "basura detrás del
delta", porque lo que queda sin consumir hace fallar el cierre del objeto. Para
que el cierre del array quedara probado **por su propia guarda** hubo que añadir
un caso donde el objeto sí cierra:

```json
{"memory_delta":[{...}}
```

Sin él, esa guarda habría estado sin probar mientras la batería decía que sí.
En el caso de las 32 operaciones no hace falta caso aparte: que el sobrante
siempre tropiece con la guarda de basura es justamente lo que hace imposible
truncar sin que se note.

## Estado

| | |
|---|---|
| Mente | 45 · 0, cuatro sabotajes |
| Almacén | 59 · 0, nueve sabotajes, auditor de cerrojos en 14/14 |
| Carrera multiproceso | ids únicos con cerrojo, reproducida sin él |
| Ruta real | 29 · 0 |

## Lo que viene, y no está hecho

Reflexión posterior al turno: fuera del camino de respuesta y sin que una
extracción del modelo adquiera autoridad por sí sola. **Sigue sin aplicador** —
el parser estricto es la puerta, no el permiso.
