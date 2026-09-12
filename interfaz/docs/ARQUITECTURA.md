# Helios: interfaz y esfera

## Estado actual

La interfaz usa React y TypeScript. La esfera vuelve a usar Three.js mediante React Three Fiber para recuperar el volumen, el halo y la profundidad de la tercera versión. Se retiraron el bloom HDR, EffectComposer, los render targets extra y MSAA multipasada tras el bloqueo y la saturación blanca que reportó el usuario. El resplandor se calcula dentro de cada luz en un único renderizado. El motor de conversación y los otros repositorios no se modificaron.

La animación arranca **pausada**. Solo se activa al pulsar «Activar movimiento». Restablecer la apariencia también deja el movimiento pausado. El código no guarda esta preferencia como activa entre recargas.

## Presupuesto gráfico

- Máximo de 24 dibujos por segundo con `frameloop="demand"`; React Three Fiber no mantiene un bucle libre a 60 fps.
- Resolución fija 1×, sin multiplicarla por la densidad de pantalla.
- 380 nodos conectados, 720 partículas tenues, tres órbitas y ocho cometas con estelas.
- Un único renderizado WebGL directo, sin bloom, postprocesado, render targets HDR ni pasadas adicionales.
- Ningún temporizador de dibujo queda activo al pausar, ocultar la pestaña, sacar la esfera del área visible o solicitar movimiento reducido.
- Al desmontar se cancelan temporizadores y observadores y se liberan las geometrías GPU.

Las pruebas acotan el número de instancias, segmentos, órbitas y cometas, y comprueban que el renderer no importe la cadena multipasada retirada. No son un benchmark del navegador ni garantizan el rendimiento del portátil con otras cargas.

## Componentes

```text
HeliosExperience (controles y demostración)
  └─ HeliosOrb (ciclo de vida, pausa y presupuesto)
       ├─ geometry (geometría estable y presupuesto)
       └─ shaders (deformación, luces, malla y cometas)

Integración futura:
React → HeliosTransport → HTTP de HexOS → orquestación → Héctor
```

`components/orb/HeliosOrb.tsx` conserva la interfaz del componente anterior:

```tsx
<HeliosOrb
  signal={{ phase: 'thinking', energy: 0.65 }}
  brightness={1}
  motion={false}
/>
```

`sampleAmplitude(timeSeconds)` acepta una amplitud normalizada 0–1 y se consulta durante el dibujo, sin actualizar React en cada fotograma. La demostración usa una envolvente de sílabas y pausas al responder. En el futuro puede leer la amplitud real de reproducción. No se activa el micrófono ni se genera voz.

El dibujo mantiene una escala suave, colores de azul a naranja, núcleos estables y cometas de 12–16 segundos por tramo. Los halos son gradientes locales dentro del shader de cada luz. La densidad se limita para conservar el aspecto tridimensional sin volver a la carga de la versión fallida.

## Contrato de integración existente

Se consultaron en modo lectura `hexos-core/hexos/agent/chat.py`, su cliente `chat.html` y `Hector-engine/src/hexos_bridge.hpp` el 12 de septiembre de 2026.

| Operación de HexOS | Contrato |
| --- | --- |
| GET `/api/status` | `{ state: 'idle' \| 'thinking' \| 'tool', mode: string }` |
| POST `/api/chat` | Cuerpo `text/plain; charset=utf-8`; JSON con `reply`, `tools` y `document` opcional |
| GET `/api/history` | Filas con `role`, `text` y metadatos |

`lib/helios/hexos.ts` implementa este contrato con validación y AbortSignal, pero no se instancia en la demostración. La esfera no conoce URLs ni protocolos del motor. El chat actual devuelve la respuesta completa: no se inventan streaming de tokens, telemetría emocional de CK ni datos de audio.

La integración posterior necesita servir la interfaz bajo el mismo origen de `/api` o un proxy fijo a HexOS. El servidor actual escucha en `127.0.0.1:8080`. Cancelar fetch no cancela la generación del motor; el endpoint actual carece de esa operación. Deben controlarse los envíos simultáneos y las respuestas tardías al cambiar de sesión.

## Verificación

- `npm run check`: tipos.
- `npm run lint`: análisis estático.
- `npm test`: contrato, amplitud, expansión, límites de geometría, render único y pausa inicial.
- `npm run build`: compilación.
- `npm run test:render`: HTML compilado; comprueba que el movimiento arranca pausado.

Estas pruebas no sustituyen una comprobación de estabilidad y color en el navegador real del usuario.
