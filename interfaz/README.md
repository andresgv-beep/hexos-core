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

La esfera usa Three.js/React Three Fiber, hasta 30 fps, DPR 2 y bloom mediante
EffectComposer. Se anima cuando está visible y no se solicita movimiento reducido.
Esto sustituye la documentación antigua de 24 fps, DPR 1 y ausencia de bloom.
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
