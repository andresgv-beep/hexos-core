# Márgenes, espacios y jerarquía en cualquier interfaz
aplica: interfaz, ventana, gui, tkinter, pyqt6, pyside6, gtk, kivy, .html, .css, formulario, botones, diseño, moderna, moderno, pantalla

Una pantalla se entiende por cómo está repartida, antes de leer nada.

- Una sola escala de espacios y nada fuera de ella: 4, 8, 12, 16, 24. Entre controles de un mismo grupo, 8; entre grupos, 16 o 24; margen de la ventana, 16.
- Agrupa por cercanía: lo que va junto, pegado; lo distinto, separado por más espacio. Un grupo con título mejor que una línea divisoria.
- Jerarquía: una acción principal por pantalla, destacada (color lleno). Las secundarias, neutras. La destructiva (borrar), aparte y nunca al lado de la principal.
- Alinea a una rejilla: etiquetas a la izquierda en su columna, campos todos del mismo ancho, botones de un grupo todos de la misma altura.
- Nada de huecos muertos: la zona de contenido (tabla, lista, lienzo) es la que se estira y ocupa lo que sobra; las barras y formularios tienen su tamaño natural.
- Tamaños que se puedan pulsar: un botón, 32 px de alto como mínimo; un campo, igual.
- Pocos colores con oficio: fondo, superficie, texto, texto apagado, acento. El contraste entre texto y fondo, alto.
- Orden de lectura: arriba lo que filtra o busca, en medio el contenido, abajo o a la derecha las acciones.

Antes de darlo por bueno, mira si queda media ventana vacía, controles de tamaños distintos sin motivo o dos botones compitiendo por ser el principal.
