# Tkinter: repartir el espacio con grid y pesos
aplica: tkinter, ttk

En Tkinter nada se estira si no se le dice. Sin pesos, cada control se queda en su tamaño mínimo y todo se amontona en una esquina.

- No mezcles `pack` y `grid` dentro del mismo contenedor. Divide la ventana en marcos (`ttk.Frame`) por zonas y usa `grid` dentro de cada uno.
- Lo que debe crecer necesita las dos cosas: peso en su fila y columna, y `sticky`.
- Usa `ttk` (Button, Entry, Treeview, LabelFrame) y no los controles clásicos: se ven actuales.
- Márgenes con `padx`/`pady` siguiendo una escala (8 entre controles, 16 en el borde), no a ojo.
- Pon `minsize` a la ventana para que no se pueda aplastar.
- Tkinter no dibuja esquinas redondeadas ni transparencias. Si piden eso, se hace en PyQt6.
- Un estilo de `ttk` no es un nombre cualquiera: se llama `Algo.TButton` (acaba en la clase del control) y hay que definirlo antes con `ttk.Style().configure('Algo.TButton', …)`. Con `style='operador'` a secas el programa muere con «Layout operador not found».

```python
root.columnconfigure(1, weight=1)      # la columna del contenido se estira
root.rowconfigure(1, weight=1)         # y su fila
barra.grid(row=0, column=0, columnspan=2, sticky='ew', padx=16, pady=(16, 8))
lateral.grid(row=1, column=0, sticky='ns', padx=(16, 8))
tabla.grid(row=1, column=1, sticky='nsew', padx=(8, 16), pady=(0, 16))
root.minsize(720, 420)
```

En un formulario: etiquetas en la columna 0 con `sticky='w'`, campos en la 1 con `sticky='ew'` y `columnconfigure(1, weight=1)` en el marco, para que todos midan lo mismo.
