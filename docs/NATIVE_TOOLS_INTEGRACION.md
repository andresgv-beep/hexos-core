# Herramientas nativas Gemma: integración opt-in

Estado: experimental, no sustituye por defecto la ruta JSON. Un modelo, un chat,
sin orquestación entre bloques. No habilita SSH ni acceso adicional a dispositivos.

Auditoría posterior: [conversación real y arquitectura](AUDITORIA_CONVERSACION_NATIVA.md).
Reproduce pseudollamadas mostradas como respuestas finales y documenta carencias
de contexto, autorización de guardado y presupuesto del ciclo. Las pruebas de
esta primera integración no constituyen aceptación del chat completo.

Corrección posterior aplicada: [recorrido conversacional](CONVERSACION_NATIVA_CORRECCION.md).
Los dos turnos del incidente responden con el nombre; el recorrido con corrección,
cambio de tema y recuperación tras reiniciar pasa. Las limitaciones restantes
de autorización y contexto largo siguen documentadas.

Estado más reciente: [contexto separado del diálogo](CONVERSACION_CONTEXTO_Y_FOCO.md).
La secuencia social ya no vuelca el encargo antiguo. Se recuperan citas recientes
y resultados locales como fuentes de contexto, y pasan 47 pruebas Python.

HexOS carga la plantilla oficial del checkpoint y transforma el catálogo existente
en declaraciones de funciones. Los nombres internos con punto tienen un alias con
guion bajo. El parser acepta llamadas completas, valida argumentos y devuelve los
resultados al modelo usando el formato nativo. Los ejecutores, validaciones de
esquema y registros siguen en HexOS. La autorización de guardado no tiene todavía
una comprobación independiente del modelo; véase la auditoría posterior.
No se evalúa texto como Python ni como shell.

Héctor solo añade mecanismos opt-in de entrada preformateada, tokens de parada y
supresión del cierre automático del turno. `helios_formatted` es un puente interno
experimental: recibe longitud y bytes, no contiene herramientas ni política. Los
valores predeterminados de `InferenceSession` conservan la ruta anterior.

## Arranque

Requiere Jinja2 y la plantilla oficial local del checkpoint. Detener primero el
servidor anterior: no cargar dos modelos en la GPU para comparar estas rutas.

```bash
python3 -m hexos.agent.chat --workspace runtime/workspace \
  --runtime ../Hector-engine/build/helios_formatted \
  --model ../helios_convert_v9.1/output/helios-gemma4-e4b_qwen3-8b_qwen25-coder-7b.hnf \
  --native-template ../helios_convert_v9.1/models/gemma-4-E4B-it/chat_template.jinja
```

La UI y `/api/status` identifican `native-experimental`. Para volver a JSON,
reiniciar sin `--native-template` y usar `helios_runtime`. El almacén es el mismo;
no es necesario borrar conversaciones ni informes.

## Evidencia y límites

- Prueba real con almacenes temporales: resumen → guardar ese resultado → limpiar
  contexto → recuperar informe, sin generar otro. También petición ambigua y
  aclaración posterior. Pasa en nativo y en JSON con el modelo E4B local.
- En la integración inicial pasaron 27 pruebas Python y dos CTest (ChatTemplateTest,
  mini_json). Tras la corrección conversacional pasan 40 Python. No equivale a
  haber ejecutado todos los tests del motor.
- El caso de ideas solo verifica ausencia de escrituras. Una corrida nativa produjo
  `procedure_list()` como respuesta final, sin ejecución: falla en utilidad aunque
  no modifique datos. No se certifica la calidad conversacional por ese test.
  En una segunda corrida respondió con propuestas de categorías y prioridades.
  Se conserva el fallo observado: no se considera resuelto por una pasada buena.
- Una llamada completa puede terminar por cesión nativa o EOS. Un corte por límite
  de tokens nunca autoriza ejecución. Llamadas múltiples se validan sintácticamente
  y contra el catálogo antes de ejecutar la primera; no son una transacción global.
- El puente reconstruye el KV en cada generación. No demuestra continuación
  incremental eficiente y aumenta el prefill en secuencias largas.
- El adaptador no aporta todavía las propuestas de clasificación que la respuesta
  estructurada JSON devolvía en `work`; devuelve `work: null`. No hay paridad total.
- La corrección conversacional añade un reintento de formato. Para pseudollamadas,
  genera una llamada nueva con prefijo nativo, restringida a lecturas; si persiste
  el fallo se muestra un error. La gramática sigue siendo acotada.

La integración permite comparar formatos con ejecutores reales. No demuestra que
el formato nativo por sí solo convierta el modelo en un agente fiable ni superior.
