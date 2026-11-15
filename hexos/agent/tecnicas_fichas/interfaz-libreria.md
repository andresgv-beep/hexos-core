# Elegir con qué hacer una interfaz
aplica: interfaz, ventana, gui, moderna, moderno, visual, diseño, bonita, redondos, redondeados, glass, glassmorphism

Decide la librería antes de escribir, por lo que hay instalado y por lo que se pide. Cambiar a mitad es rehacerlo todo.

1. Mira qué hay, sin suponer: `["python3","-c","import PyQt6"]`, y lo mismo con `PySide6`, `tkinter`, `gi`, `customtkinter`.
2. Elige de lo que ya está. No bases un programa en un paquete que habría que instalar con pip: en este sistema pip está bloqueado y la persona no tiene por qué instalar nada.
3. Qué da cada una:
   - **PyQt6 / PySide6**: aspecto moderno de verdad. Con hojas de estilo (QSS) hay esquinas redondeadas (`border-radius`), degradados, colores translúcidos (`rgba`), estados `:hover` y `:pressed`. Es la que hay que usar si piden «moderno», botones redondos, efecto cristal o animaciones.
   - **Tkinter con ttk**: sobrio y correcto para formularios, tablas y herramientas. No dibuja esquinas redondeadas ni transparencias: no las prometas ni des vueltas intentándolo.
   - **customtkinter** y parecidos: solo si el `import` funciona ya.
4. Si lo que piden no se puede con lo elegido, dilo una vez y propón la librería instalada que sí puede, en vez de pedir un paquete.

```python
# Qt: botón redondeado con efecto cristal
app.setStyleSheet('''
QPushButton { border-radius: 18px; border: 1px solid rgba(255,255,255,40);
              background: rgba(255,255,255,22); color: white; font-size: 18px; }
QPushButton:hover { background: rgba(255,255,255,40); }
QPushButton#operador { background: #ff9f0a; border: none; }''')
```
