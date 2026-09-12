# Gemma E4B: laboratorio de herramientas nativas

Fecha: 2026-09-12. Sin cambios en Héctor, sin despliegue de la vía nativa.
Herramientas simuladas: read_disk, list_jobs y save_report. No accede a equipos.

## Resultado

| Variante | Casos que pasan | Mediana de tiempo por caso | Cinco consultas + guardado |
|---|---:|---:|---:|
| JSON propio, política mínima | 6/6 | 1,15 s | 5,34 s |
| Nativo, sin pensamiento | 6/6 | 1,25 s | 4,42 s |
| Nativo, con pensamiento | 6/6 | 7,41 s | 18,54 s |

Casos: leer disco, consultar pendientes y guardar, destino inaccesible, pedir ideas
sin escribir, cinco lecturas con valores distintos y guardar su comparación, y
una salida de herramienta que intenta ordenar un guardado no autorizado.
El modelo no siguió esa instrucción hostil en este caso. No equivale a una
certificación frente a inyección de prompts.

La secuencia larga conservó Faro=137, Luna=29, Vega=84, Orion=7 y Lira=201 GiB,
y señaló Orion como mínimo. Refuta un límite absoluto de seis llamadas en estas
condiciones, no demuestra planificación robusta en tareas arbitrarias.

Recomendación provisional: integrar primero formato nativo sin pensamiento para
operaciones concretas. No se demuestra superioridad global en velocidad ni calidad:
JSON también pasó y tuvo menor mediana. Pensamiento fue más costoso sin aportar
aciertos en este banco pequeño; no se evaluaron problemas de diagnóstico difíciles.

## Método y límites

- Mismo HNF E4B y biblioteca estática del motor, una carga de pesos y un KV.
- Plantilla local original de Google renderizada con Jinja2, incluyendo tools,
  tool_calls, tool_responses y reasoning en modo pensamiento.
- SHA256 de plantilla: 0a2c8073c878ab1da004bee933a998606537bbb62016310352c7285c3f01c5b5.
- Greedy en las tres variantes, sin reintentos correctivos del agente actual.
- Se reconstruye el KV desde el historial completo en cada paso: las cifras no
  predicen la latencia de una integración que continúe el KV sin reconstruirlo.
- El laboratorio detiene al observar `<|tool_response>` mediante callback y
  cancelación; no añade soporte productivo de cesión/continuación al runtime.
- Máximo ocho generaciones por caso y 1536 tokens por generación.
- Una ejecución por variante; sin estimación estadística ni prueba de todos los
  esquemas. El parser del banco solo admite argumentos string planos.
- El control JSON tiene una política mínima y estas tres herramientas, NO todo
  el prompt/estado del chat doméstico. Sus buenos resultados no certifican el chat.

La primera versión del lector de pensamiento no contemplaba que la plantilla
dejase abierto el canal tras una respuesta de herramienta. Mostraba la continuación
como respuesta final. Se corrigió usando el sufijo real del prompt y se repitió
el banco completo. native_tools_parser_test.py cubre ese caso.

## Archivos y reproducción

- tools/native_tools_probe.cpp: ejecutable aislado; reemplaza el formateador al
  enlazar esta prueba, no modifica la biblioteca ni el runtime instalado.
- tools/native_tools_audit.py: plantilla oficial, fixtures y registro íntegro.
- tools/native_tools_parser_test.py: tres comprobaciones del lector limitado.
- informes/native_tools_20260912.json: traza del banco corregido, con salidas y tiempos.

Compilación realizada contra build/libhelios-engine.a con los mismos runtimes
CUDA/cuBLAS del ejecutable de Héctor. Ejecución (GPU libre):

```sh
python3 tools/native_tools_audit.py --binary /tmp/hexos-native-tools-probe \
  --model /ruta/al/modelo.hnf --template /ruta/chat_template.jinja \
  --output /ruta/resultados.json
```

Siguiente fase: soporte genérico y opt-in de declaraciones, cesión y continuación
en el transporte/plantilla; HexOS conserva ejecutores y permisos. Comparar luego
el chat real, con historial, errores y documentos, contra su ruta vigente antes
de sustituirla. No portar lógica doméstica al motor.
