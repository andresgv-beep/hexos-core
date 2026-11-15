# Comprobar una ventana sin verla
aplica: tkinter, pyqt6, pyside6, interfaz, ventana, gui

No ves lo que dibujas, pero puedes medirlo. Hazlo antes de decir que una interfaz está bien.

- Si arranca: lanza el programa con `timeout` 5. Si a los 5 segundos sigue en marcha y sin errores, arranca.
- Cómo queda: crea la ventana, actualízala, imprime la posición y el tamaño de cada control y ciérrala. Hazlo con `python3 -c "…"` importando tu clase, sin tocar ningún fichero. Nunca metas la medición en el programa (`main.py`): la ventana se le cerraría sola a la persona al abrirlo.
- Señales de que está mal: controles con 20 px de alto, todos con la misma `y`, una zona de contenido más pequeña que las barras, o la suma de alturas muy por debajo de la altura de la ventana (hay un hueco muerto).

```python
# Tkinter
app = Aplicacion(); app.update()
print('ventana', app.winfo_width(), app.winfo_height())
def medir(control, nivel=0):
    print(' ' * nivel, control.winfo_class(), control.winfo_x(), control.winfo_y(),
          control.winfo_width(), control.winfo_height())
    for hijo in control.winfo_children(): medir(hijo, nivel + 2)
medir(app); app.destroy()
```

```python
# PyQt6
app = QApplication([]); v = Ventana(); v.show(); app.processEvents()
for w in v.findChildren(QWidget):
    g = w.geometry(); print(type(w).__name__, w.objectName(), g.x(), g.y(), g.width(), g.height())
```

Corrige con esos números y vuelve a medir. A la persona dile la orden para abrir el programa ella.
