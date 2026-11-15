# Fichas de técnica

2026-11-15. Idea de Andrés: enseñarle a Helios las técnicas que no domina, no darle el
programa hecho.

## Qué es una ficha

Un fichero de texto corto con una técnica: cuándo se usa, la regla, por qué, y un ejemplo
mínimo. No un programa entero.

```
# Título de la técnica
aplica: tkinter, interfaz

El cuerpo: la regla, el porqué y un ejemplo de pocas líneas.
```

`aplica` son las palabras que la activan: un módulo que el proyecto importa (`tkinter`,
`sqlite3`), una extensión (`.cu`, `.html`) o una palabra de lo que se pide (`interfaz`).

## Dónde están

- De serie: `hexos/agent/tecnicas_fichas/`.
- Las tuyas: `~/Helios/tecnicas/` (o `HEXOS_TECNICAS_HOME`). Cualquier `.md` con esa forma.
  Una con el mismo nombre de fichero sustituye a la de serie; un fichero vacío la apaga.

Se leen en cada turno: editar una ficha vale al momento, sin reiniciar nada.

## Cuándo se le dan

En la ventana Agente y con un proyecto puesto. HexOS mira qué importan los ficheros del
proyecto, sus extensiones, el objetivo y el plan apuntados y lo que se pide en el turno, y le
pone delante las fichas que casan: hasta 4 de una vez, de 1.800 caracteres como mucho cada
una. Cada ficha va una vez por contexto; si el contexto se corta o se limpia, vuelven.

No hay herramienta para pedirlas: no dependen de que el modelo se acuerde.

## Las de serie

| Fichero | Técnica |
|---|---|
| `interfaz-jerarquia` | Márgenes, espacios y jerarquía, para cualquier interfaz |
| `tkinter-reparto` | Repartir el espacio con `grid` y pesos; estilos de `ttk` |
| `pyqt6-reparto` | Layouts, estiramiento y estilos en Qt |
| `sqlite-migrar` | Cambiar el esquema cuando ya hay datos |
| `ventana-comprobar` | Medir una ventana que no se ve |
| `interfaz-libreria` | Elegir con qué hacer una interfaz según lo instalado |

## Medido

Con el E4B, una pasada, la misma petición («una calculadora con ventana en Tkinter») con las
fichas y sin ellas, y las dos ventanas medidas en una pantalla virtual:

| | Sin fichas | Con fichas |
|---|---|---|
| Pesos de fila y columna | 0 | 7 |
| Tamaño mínimo de ventana | no | sí |
| Alto de los botones | 31 px | 46 px |
| Al agrandar la ventana | no se estiran | se estiran |

La versión con fichas no arrancaba: usó `style='operador'`, que no es un nombre de estilo
válido en `ttk`. Esa regla se añadió a la ficha de Tkinter. Sin medir con el 26B.

## Sin hacer

Que las escriba él: cuando algo le falla, lo arregla y funciona, proponer una ficha nueva con
lo aprendido para que la persona la apruebe.
