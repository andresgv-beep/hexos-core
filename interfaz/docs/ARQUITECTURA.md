## Organización HUD (2026-09-24)

Primera etapa sobre main fd15f38: distribución en tres columnas, sin montar
NebulaOrb ni sus ajustes. `app/hud.css` contiene la distribución; los estilos
compartidos de ventanas siguen en globals.css. `ToolActivityPanel` presenta la
actividad del transporte existente sin posiciones orbitales.

Sistema y favoritos quedan a la izquierda; turno actual y compositor en el
centro; accesos a contenido y actividad a la derecha. El historial tiene botón
explícito. NAS, código, notas y credenciales conservan sus visores y acciones.
Móvil conserva MobileWorkspace y su compositor compartido. No se modifica el
backend ni se fabrica telemetría. Acoplar el contenido al lateral y separar
ventanas del navegador quedan para una etapa posterior.

La documentación siguiente describe la base anterior; la sección de esfera
solo se aplica al componente antiguo, que ya no se monta en el producto.

# Arquitectura actual de la interfaz

Revisión documental del 2026-09-19, contrastada con `HeliosExperience.tsx`,
`NebulaOrb.tsx`, `hexos.ts`, `CodeWorkspace.tsx` y `vite.config.ts`.

## Flujo conectado

```text
HeliosExperience
  ├─ HeliosTransport → /api/helios → proxy Vite → agente Python :8080
  ├─ ConversationStream → respuesta provisional/final y herramientas
  ├─ CodeWorkspace → código coloreado / iframe de preview
  ├─ paneles de notas, acceso y telemetría
  └─ NebulaOrb → estado visual de conversación
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
| POST `/api/model/warmup` | Carga anticipada al escribir; cuerpo `{}`, devuelve el estado sin esperar a la GPU |
| POST `/api/cancel` | Detener el turno identificado; espera confirmación del backend |
| GET `/api/history` | Historial y eventos conservados |
| GET `/api/telemetry` | Métricas del sistema, no estimaciones del modelo |
| GET `/api/core`, `/api/notes` | Recursos persistidos y notas |

HexOS mantiene el modelo nativo descargado hasta recibir actividad. React avisa
al escribir (como máximo una vez cada 30 segundos); el turno espera el `ready`
real y muestra «Cargando el modelo…» mientras tanto. Una reserva cubre el turno
completo, también las herramientas. Tras 600 segundos inactivo cierra el proceso
de Héctor. El historial persiste y el siguiente turno reconstruye su contexto.
Consultar `/api/status` no despierta el modelo ni reinicia el temporizador.

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

- WebGL 2 directo con un único rectángulo y un fragment shader procedural,
  limitado a `MAX_FPS=30` y `MAX_DPR=1.4`.
- La esfera, la nebulosa y su halo se componen en una sola pasada, sin Three.js,
  geometría 3D ni postprocesado. Los píxeles alejados del halo salen antes de
  calcular el ruido procedural.
- `HeliosExperience` habilita movimiento. Se detiene cuando se oculta la página,
  la esfera sale del área visible o el navegador solicita movimiento reducido.
- `sampleAmplitude` es una entrada opcional de animación, no audio real.
- Programa, shaders y buffer se liberan al desmontar. El coste depende del tamaño
  del canvas, GPU y carga del equipo; no inferirlo solo por ser una única pasada.

## Desarrollo y validación

`vite.config.ts` configura el proxy de desarrollo y el plugin local de adjuntos.
Cambiar el puerto del agente requiere cambiar el destino de ese proxy. Un build
no configura por sí solo el despliegue remoto ni su enrutado.

Tipos, pruebas de contratos/componentes y build/render están en `package.json`.
La validación de cancelación/texto progresivo se hizo también en navegador real;
la evidencia está en [integración progresiva](../../docs/PROGRESSIVE_NATIVE_RUNTIME.md).
No hay telemetría emocional ni voz real inferibles del movimiento de la esfera.

### Temas HUD

`app/themes.css` declara las cuatro paletas del concepto en variables `--hud-*`
sobre `html`, para que también las hereden los diálogos y los portales.
`ThemeSelector` solo gestiona una preferencia local (`helios.hud.theme`), valida
el valor almacenado y sincroniza cambios entre pestañas. No usa el modelo, notas
ni preferencias de HERA. `hud.css` consume las variables sin duplicar componentes.
Los colores de error/advertencia pueden mantener su significado propio.
