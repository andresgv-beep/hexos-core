# Helios · Una presencia viva

Interfaz React con una esfera orgánica de luces, conexiones y cometas lentos. Cambia de azul a naranja y se expande con una envolvente de voz simulada.

La esfera recupera el volumen y el acabado luminoso de la tercera versión mediante WebGL directo. El resplandor está integrado en cada luz: no existe la cadena multipasada que produjo carga excesiva y saturación blanca. Arranca pausada, dibuja bajo demanda y está limitada a 24 fps con resolución 1×.

## Desarrollo local

Requiere Node.js >= 22.13.

```sh
npm ci
npm run dev
```

Abre la dirección que muestre el servidor. La esfera permanece pausada hasta pulsar «Activar movimiento». Los mensajes solo reproducen una demostración visual; no se envían al motor.

## Comprobaciones

```sh
npm run check
npm run lint
npm test
npm run build
npm run test:render
```

Las pruebas verifican los límites de geometría y que no vuelva a introducirse la cadena de bloom multipasada.

## Integración

El componente está en `components/orb`, y el adaptador HTTP para HexOS en `lib/helios/hexos.ts`. Sigue preparado pero sin conectar. [Arquitectura, presupuesto gráfico y límites](docs/ARQUITECTURA.md).

La base del proyecto sigue usando Vite/Vinext. No se ha publicado ni se han conectado servicios domésticos.
