# Generación progresiva conectada a la interfaz

Integración local del 19 de septiembre de 2026. La ruta nativa con plantilla de
Gemma utiliza ahora `helios_runtime` (NDJSON). Se conserva `helios_formatted` como
compatibilidad, sin progreso ni cancelación. No cambia la ruta JSON sin plantilla.

## Recorrido

1. React envía `/api/chat` con un `request_id` único.
2. El agente procesa el turno y el adaptador consume eventos de Héctor: inicio,
   progreso de prefill, fragmentos de texto y terminación.
3. `/api/status` expone una instantánea provisional, filtrada para ocultar los
   canales de pensamiento y llamadas a herramientas, incluso fragmentados.
4. La interfaz consulta el estado cada 450 ms durante el turno y muestra el texto
   real disponible. No es SSE. La respuesta final sigue llegando por `/api/chat`.
5. El código provisional no sustituye el artefacto abierto: se aplica únicamente
   la respuesta final validada. Una respuesta interrumpida tampoco lo sustituye.

El botón **Detener generación** envía `/api/cancel` con ese mismo identificador.
Una cancelación antigua no detiene un turno distinto. El motor cancela su trabajo;
el agente conserva la respuesta parcial marcada como interrumpida, restablece el
estado nativo y reconstruye el siguiente turno desde el historial y la traza.
Una herramienta externa que ya está ejecutándose termina y deja registro; no se
inician nuevas herramientas después de comprobar la cancelación. Al abandonar
la página se intenta también enviar la cancelación, sin garantía de entrega.

## Arranque

```bash
runtime/run-helios-native /ruta/modelo.hnf /ruta/chat_template.jinja /ruta/workspace 16384 8080
```

El script comprueba los archivos y usa el `helios_runtime` del repositorio hermano
`Hector-engine`; `HELIOS_RUNTIME_BIN` permite cambiarlo. La interfaz continúa en
3000, con su proxy al agente Python en 8080.

En este equipo se actualizó `/home/andres/Documentos/hexos-prueba-12b/iniciar.sh`
para usar el nuevo ejecutable, conservando modelo, contexto y almacén habituales.
La copia anterior queda junto al script con sufijo `.antes-ndjson-2026-09-19`.

## Memoria y adjuntos

La sesión auxiliar se crea al necesitar extracción de hechos, con capacidad de
1024 tokens. La sesión principal conserva la reutilización del prefijo textual.
Los píxeles enviados se liberan explícitamente al terminar el turno. Después de
una imagen se reconstruye el siguiente prompt textual, porque los tokens visuales
no se corresponden con ese historial textual. El reinicio de contexto durante la
preparación conserva la imagen nueva; al terminar el turno se elimina cualquier
adjunto pendiente. Un HNF que declara no tener visión rechaza el adjunto.

## Comprobaciones

- Contratos Python: filtrado de canales fragmentados, cancelación dirigida,
  conservación de respuesta parcial, continuación, adjuntos y sesión auxiliar.
- Interfaz: TypeScript, 72 pruebas, compilación y prueba del HTML servido.
- 12B HQ42/HQ52 real, almacén temporal: varios fragmentos visibles antes de terminar,
  rechazo de cancelación con ID incorrecto, cancelación correcta y siguiente turno.
  Una consulta `note.list` también pasó por el ejecutor habitual.
- Prueba desde el navegador: texto progresivo, botón Detener, respuesta parcial
  marcada y compositor disponible para continuar.
- E4B HQ62K real con visión: imagen azul reconocida como «Azul», siguiente turno
  textual correcto y extracción de nombre en una sesión auxiliar de 1024 tokens.
- Regresión del protocolo de cancelación de Héctor con el 12B: pasada.

En la prueba HTTP del 12B hubo cuatro instantáneas distintas antes de cancelar;
la cancelación se confirmó en unos 19 ms en esa ejecución. No es una garantía de
latencia ni un nuevo benchmark de velocidad del modelo.

La integración no certifica calidad de respuestas, todas las familias de modelos
ni comportamiento de todas las herramientas. El botón de cancelación se habilita
solo cuando el backend declara que el turno admite cancelación.
