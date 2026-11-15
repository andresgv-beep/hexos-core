# PyQt6: layouts, estiramiento y estilos
aplica: pyqt6, pyside6, pyqt5

En Qt el tamaño lo decide el layout. Un botón sin altura mínima queda en una tira de 20 px, y una rejilla a la que nadie le dice que crezca se queda apretada con la ventana medio vacía.

- Nunca posiciones a mano (`move`, `setGeometry`): todo dentro de layouts anidados (`QVBoxLayout`, `QHBoxLayout`, `QGridLayout`).
- Lo que debe llenar el espacio: `setSizePolicy(Expanding, Expanding)` y, en una rejilla, `setRowStretch`/`setColumnStretch` a 1 en todas las filas y columnas que crecen.
- Estiramiento solo a las filas y columnas que tienen controles, y con la cuenta sacada de los datos (`max(fila) + 1`), no de un número a mano: una fila vacía con estiramiento se queda con su parte y deja un hueco.
- Altura mínima a los botones (`setMinimumHeight(44)`), no tamaño fijo.
- Márgenes y separación explícitos y de la misma escala: `setContentsMargins(16, 16, 16, 16)`, `setSpacing(8)`.
- No fijes el tamaño de la ventana (`setFixedSize`) salvo que sea imprescindible; usa `resize` y `setMinimumSize`.
- Un solo estilo para toda la aplicación (`app.setStyleSheet`), con `objectName` o propiedades para distinguir clases de botón, en vez de estilos sueltos por control.

```python
rejilla = QGridLayout(); rejilla.setSpacing(8)
filas = max(f for _, f, _ in teclas) + 1; columnas = max(c for _, _, c in teclas) + 1
for f in range(filas): rejilla.setRowStretch(f, 1)
for c in range(columnas): rejilla.setColumnStretch(c, 1)
boton.setMinimumHeight(44)
boton.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
```

La pantalla de resultado va arriba con su altura propia; la rejilla de teclas debajo, con `layout.addLayout(rejilla, 1)` para que se lleve el espacio que sobra.
