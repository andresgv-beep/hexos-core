# Agente doméstico: dirección vigente

Fecha: 2026-09-12. Base inspeccionada: HexOS `28deafc`, Héctor `a540432`.
Ambos repos estaban limpios al comenzar. Este documento fija el nuevo alcance;
no implica que las capacidades descritas como pendientes estén implementadas.

## Objetivo acordado

Un único chat persistente, un modelo principal, herramientas y un espacio de
trabajo propio. Helios consulta y administra el NAS, servidores y dispositivos
habilitados; busca información, prepara documentos y escribe código básico.
La interfaz central será la esfera neuronal, con estados reales de actividad.
Texto y visión forman la base; voz se incorpora tras verificar entrada y salida
de audio disponibles. No hay relevo TEXT/CORTEX/CODE en este producto.

## Qué hay en la base

- `hexos/src/serve/serve_main.c`: servidor con ruta legacy predeterminada y
  ruta tipada opt-in mediante `--runtime`.
- `hexos/src/serve/runtime_client.c`: comunicación con el motor, CK y HERA.
- `hexos/src/serve/http.c`: chat, eventos SSE, estado y adjuntos RGB8.
- `hexos/src/serve/chats.c`: historial durable y multichat existente. El nuevo
  producto usará una conversación; no hace falta borrar historiales previos.
- `hera/`: persistencia, evidencia, perfil y reflexión opcional. No es el
  almacén de archivos de trabajo ni el ejecutor de herramientas.
- Héctor dispone de `helios_runtime` y sesiones genéricas. La plantilla de
  chat inspeccionada no demuestra todavía soporte completo de tool calling.
- No se encontró un ejecutor de herramientas del modelo en la ruta inspeccionada.
- No había procesos `hexos_serve`, `helios_runtime` ni `helios_chat` activos.

El README mezcla estados históricos, incluidos apartados que llaman stub al
motor. No se usará como prueba de capacidades sin comprobar el código.

## Responsabilidades

| Pieza | Responsabilidad |
|---|---|
| Modelo principal | Interpretar la conversación, pedir herramientas, leer resultados y responder |
| HexOS | Ejecutar el ciclo del agente, permisos, historial, archivos de trabajo y eventos |
| Módulos de herramientas | Acceso a recursos concretos con entradas y resultados definidos |
| Héctor | Inferencia, plantillas, tokenizer, KV y adaptadores del modelo |
| Interfaz de esfera | Mostrar conversación y actividad real del sistema |

Una pregunta sobre posibilidades permite consultar y proponer. No autoriza a
inventar cambios. La decisión del modelo no otorga permisos nuevos. El contenido
de páginas, archivos y salidas remotas se entrega como datos de herramientas.

## Ciclo mínimo

1. La persona escribe o aporta una imagen en la conversación única.
2. El mismo modelo responde o solicita una herramienta con argumentos.
3. HexOS valida nombre, argumentos y permiso configurado; ejecuta el módulo.
4. Devuelve resultado con identificador de llamada, estado, origen y fecha.
5. El modelo continúa desde ese resultado y responde o pide otra herramienta.

El adaptador del modelo debe respetar su plantilla y formato de herramientas.
Primero se comprobará si hay soporte nativo utilizable. Si hace falta un formato
estructurado alternativo, se validará con el modelo real antes de conectarlo a
acciones. Las palabras «código», «integra» o «servidor» no serán autorización.
Habrá límites de llamadas, tiempo y salida por turno, con cancelación observable.

## Herramientas y espacio de trabajo

Propuesta de módulos dentro de HexOS, con registro común y ejecutores separados:

- `workspace`: listar, buscar, leer y escribir archivos dentro de una raíz
  configurada; trabajar sobre copias y conservar versiones de documentos.
- `servers`: estado de NAS, servicios, disco y recursos, con origen y hora.
- `ssh`: máquinas configuradas por alias, credenciales fuera del prompt,
  directorio de trabajo, salida estándar, error, código de retorno y timeout.
  Primer uso: consultas; acciones posteriores según permisos habilitados.
- `home`: estados y acciones específicas de los equipos domésticos existentes.
- `web`: búsqueda y lectura de fuentes con URL y fecha de consulta.

La raíz de trabajo se elegirá en configuración; no se crea ni se migra el perfil
durante esta revisión. Contendrá documentos, scripts, resultados y tareas
pendientes. Los archivos persisten en disco y se leen bajo demanda; no requieren
otro modelo ni otro KV residente. Los hechos personales de HERA siguen separados.

Restricciones heredadas: no modificar código ni configuración de Pi o ESP32.
No dar acceso genérico a toda la LAN por inferencia. Las luces y otros controles
se conectarán mediante las operaciones ya disponibles, al revisar sus endpoints.

## Orden de implementación y evidencia de salida

Primer componente disponible: [registro de fichas de trabajo](TRABAJOS.md),
en `hexos/agent/work.py`. El chat experimental `hexos/agent/chat.py` conecta
fichas, documentos y procedimientos consultables al único modelo. El primer
procedimiento prepara el resumen; report.save lo guarda por petición separada y
report.get lo recupera tras limpiar contexto. No ejecuta herramientas externas; visión, voz y esfera siguen pendientes
en esta ruta. Véase TRABAJOS.md para sus límites y pruebas reproducibles.

1. **Una conversación y una herramienta local de lectura.** Reutilizar transporte
   tipado y probar petición real del modelo → ejecución → resultado → respuesta.
   Comprobar texto, imagen y continuidad tras reiniciar. Sin nuevos KV auxiliares.
2. **Espacio de trabajo.** Crear un documento, releerlo, modificarlo por petición
   y recuperarlo tras reiniciar. Preguntar por mejoras no escribe archivos.
3. **NAS/SSH de consulta.** Conectar el destino configurado y responder con datos
   reales; un destino caído debe producir un error claro, no un estado inventado.
4. **Esfera neuronal.** Integrar la conversación única y estados de escucha,
   inferencia, herramienta activa y respuesta con eventos del servidor.
   No mostrar nodos ni lecturas simuladas como equipos conectados.
5. **Web y acciones habilitadas.** Fuentes trazables; ejecutar una acción y
   comprobar su resultado antes de anunciar éxito.
6. **Voz.** Verificar capacidades reales de reconocimiento y síntesis y conectar
   ambos al mismo ciclo, mostrando claramente cuándo está escuchando.

La primera entrega se juzga con uso completo, no solo con parsers: una charla
normal, una consulta que exige herramienta, un error de herramienta y una vuelta
al tema anterior. Registrar latencia y VRAM antes/después. No hacer commit hasta
que el usuario considere estable la entrega.

## Fuera del alcance actual

CORTEX, coder separado, conmutación de pesos, multichat de producto, multiusuario,
trabajadores de reflexión adicionales y nuevos formatos de cuantización.
`AGENTES_ESPECIALISTAS_PLAN.md` queda como antecedente aparcado, no como cola de
implementación. La carpeta experimental del usuario no se modifica ni se importa
automáticamente. Los componentes genéricos existentes se conservarán mientras
no interfieran con el alcance de una conversación y un modelo.
