# Helios · interfaz React

**Estado revisado: 2026-09-19.** La interfaz está conectada al agente Python de
Hexos. Los mensajes llegan al modelo; no es la antigua demostración visual.

## Desarrollo local

Requiere Node.js >= 22.13 y el agente Python en `127.0.0.1:8080`.
Desde la raíz del repositorio, arrancar el agente según el [README](../README.md).
Después, desde `interfaz/`:

```sh
npm ci
npm run dev -- --host 127.0.0.1 --port 3000
```

Abrir `http://localhost:3000`. Vite reenvía `/api/helios/*` a `/api/*` del
agente. No conectar ese proxy al servidor C `hexos_serve`: es otra API.
La compilación por sí sola no arranca el modelo ni instala un proxy de producción.

## Funciones conectadas

Chat e historial, texto progresivo, botón Detener, telemetría CPU/RAM/GPU/VRAM,
notas, adjuntos, credenciales de equipos y control de pensamiento. La ventana
Código/Interfaz permite revisar código con color y una vista previa HTML aislada;
no es un entorno general de ejecución de proyectos React.

El escritorio sigue el concepto HUD: sistema y núcleo a la izquierda, conversación
al centro y `ContentDock` a la derecha con Código / Interfaz / NAS. El visor NAS
comparte componente y API entre el panel y la ventana ampliada. Cambiar de pestaña
conserva su lectura; ampliar abre el mismo archivo en un visor independiente.
Las ventanas son internas a la aplicación, no ventanas del sistema operativo.

`themes.css` contiene las cuatro paletas; `hud.css` organiza paneles y controles.
`hud-frames.css` reproduce los marcos recortados del concepto en paneles y ventanas;
`SystemGauges` presenta la telemetría existente en indicadores circulares.
El selector persiste el tema y lo comparte con los visores. AUTO permanece en la
cabecera y usa el control existente del agente. La esfera ya no se monta.
El panel inferior muestra actividad de herramientas real; todavía no hay gráfica
de tokens por segundo conectada.

No hay micrófono ni síntesis de voz conectados.

## Comprobaciones

```sh
npm run check
npm run lint
npm test
npm run build
npm run test:render
```

`build` ya incluye la prueba de HTML servido. Las pruebas no garantizan una tasa
de fotogramas en todos los equipos. [Arquitectura y contratos](docs/ARQUITECTURA.md).
