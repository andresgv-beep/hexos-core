# Arquitectura actual de la interfaz

Revisión documental del 2026-09-19, contrastada con `HeliosExperience.tsx`,
`HeliosOrb.tsx`, `Bloom.tsx`, `hexos.ts`, `CodeWorkspace.tsx` y `vite.config.ts`.

## Flujo conectado

```text
HeliosExperience
  ├─ HeliosTransport → /api/helios → proxy Vite → agente Python :8080
  ├─ ConversationStream → respuesta provisional/final y herramientas
  ├─ CodeWorkspace → código coloreado / iframe de preview
  ├─ paneles de notas, acceso y telemetría
  └─ HeliosOrb → estado visual de conversación
```

`createHexosTransport` se instancia en el producto. Los mensajes se envían al
agente real. Durante un turno se consulta estado cada 450 ms; se muestra solo
la generación cuyo `request_id` coincide. La respuesta final viene de POST chat.
No se usa SSE en esta ruta ni se simula el streaming con una animación de escritura.
Las respuestas antiguas/no progresivas pueden conservar su presentación animada.

| Endpoint Python, detrás de `/api/helios` | Uso |
|---|---|
| GET `/api/status` | Estado, avances, herramientas activas, pensamiento, acceso y generación provisional |
| POST `/api/chat` | JSON con texto, ID y opciones; respuesta final, herramientas y cancelación si corresponde |
| POST `/api/cancel` | Detener el turno identificado; espera confirmación del backend |
| GET `/api/history` | Historial y eventos conservados |
| GET `/api/telemetry` | Métricas del sistema, no estimaciones del modelo |
| GET `/api/core`, `/api/notes` | Recursos persistidos y notas |

Los adjuntos locales usan también `/api/attachments`, atendido por el plugin de
Vite. El backend Python recibe la imagen codificada en el JSON del turno; no
utiliza el endpoint RGB8 del servidor C. El selector no certifica que todo HNF
sea visual: el adaptador rechaza imágenes si el modelo no declara esa capacidad.

## Cancelación y código

Detener envía una orden real al agente; no consiste en abortar el fetch. La
respuesta parcial queda marcada como interrumpida y puede continuarse el chat.
Al abandonar una petición se intenta enviar cancelación, sin garantía de entrega.
Las herramientas externas ya iniciadas no se matan a mitad de ejecución.

El código parcial no sustituye automáticamente el artefacto abierto. Las
respuestas finales pasan la selección y protección de revisiones existentes.
El preview es HTML mediante `srcDoc` en un iframe `sandbox="allow-scripts"`;
no instala dependencias ni compila cualquier proyecto React. La ventana se puede
mover y alterna Código/Interfaz. Ver los contratos en `lib/helios/preview.ts`
y los componentes actuales antes de añadir capacidades de ejecución.

## Esfera y coste gráfico real

- Three.js con React Three Fiber, `frameloop="demand"` y temporizador limitado a
  `MAX_FPS=30`; no equivale a una garantía de 30 fps.
- `dpr={2}` y `antialias: false` en Canvas.
- `Bloom.tsx` usa EffectComposer, RenderPass, UnrealBloomPass y OutputPass.
  Por tanto sí hay postprocesado y render targets; ya no es el diseño anterior
  de una sola pasada sin bloom.
- `HeliosExperience` habilita movimiento. Se detiene cuando se oculta la página,
  la esfera sale del área visible o el navegador solicita movimiento reducido.
- `sampleAmplitude` es una entrada opcional de animación, no audio real.
- Los recursos del composer se liberan al desmontar. El coste depende del tamaño
  del canvas, GPU y carga del equipo; no afirmar que DPR 1/24 fps siguen vigentes.

## Desarrollo y validación

`vite.config.ts` configura el proxy de desarrollo y el plugin local de adjuntos.
Cambiar el puerto del agente requiere cambiar el destino de ese proxy. Un build
no configura por sí solo el despliegue remoto ni su enrutado.

Tipos, pruebas de contratos/componentes y build/render están en `package.json`.
La validación de cancelación/texto progresivo se hizo también en navegador real;
la evidencia está en [integración progresiva](../../docs/PROGRESSIVE_NATIVE_RUNTIME.md).
No hay telemetría emocional ni voz real inferibles del movimiento de la esfera.
