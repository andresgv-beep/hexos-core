# HELIOS / Hexos

Agente local con una conversación persistente, herramientas y una interfaz React.
**Estado revisado el 2026-09-19 sobre `76a75c0`.** La inferencia real la ejecuta
Héctor, en el repositorio hermano `Hector-engine`.

- [Estado de implementación y límites](IMPLEMENTATION_STATUS.md).
- [Índice documental: contratos, planes e historia](docs/INDICE.md).
- [Generación progresiva y cancelación](docs/PROGRESSIVE_NATIVE_RUNTIME.md).

## Ruta actual del agente

```text
React/Vinext :3000 → proxy /api/helios → agente Python :8080
                                          ↓
                         herramientas + historial SQLite + HERA opcional
                                          ↓
                          NativeRuntime → helios_runtime NDJSON → GPU
```

El agente ya ejecuta herramientas, conserva historial, gestiona notas e informes,
consulta equipos configurados y web pública, publica telemetría y muestra texto
progresivo con cancelación. La visión requiere un HNF con adaptador compatible;
el 12B textual usado en la última prueba no incorpora visión utilizable.

El repositorio también conserva el supervisor C, Memory Core, HNF-EXT, HERA,
`cognitive_stub` y el servidor C `hexos_serve`. La existencia de un stub de pruebas
**no significa que el motor o el agente sean simulados**.

## Arrancar agente e interfaz

Requisitos: Python 3, Jinja2 para la plantilla nativa, Pillow para imágenes,
Node.js >= 22.13 para la interfaz, y Héctor compilado con un HNF compatible.
Los modelos y plantillas no se descargan al instalar React.

Desde la raíz de `hexos-core`:

```bash
runtime/run-helios-native /ruta/modelo.hnf /ruta/chat_template.jinja /ruta/workspace 16384 8080
```

En otra terminal:

```bash
cd interfaz
npm ci
npm run dev -- --host 127.0.0.1 --port 3000
```

Abrir `http://localhost:3000`. El proxy de desarrollo apunta a `127.0.0.1:8080`.
El lanzador usa `helios_runtime`; `HELIOS_RUNTIME_BIN` permite cambiar el binario.
El contexto explícito de 16384 evita heredar el default Python de 32768; elegirlo
según modelo y VRAM. No garantiza que cualquier HNF quepa.

Para conectar un perfil HERA existente, usar la CLI completa con `--hera` y
`--memory-home` juntos (ver [estado](IMPLEMENTATION_STATUS.md)). El lanzador
básico no activa HERA automáticamente. El workspace contiene el historial y
trabajo; cambiarlo selecciona otro almacén.

## Dos servidores distintos

| Ruta | Función | Transporte |
|---|---|---|
| `python3 -m hexos.agent.chat` | Agente actual, herramientas, notas, telemetría, UI React | HTTP propio; nativo NDJSON con plantilla o decisiones JSON sin ella |
| `hexos_serve` (C) | Ruta anterior con CLI/cliente runtime y capacidades propias | API C, SSE y RGB8; no intercambiable con la del agente |
| `make chat MODEL=/ruta/modelo.hnf` | Chat de terminal | Lanza `helios_chat`; no arranca el agente ni React |

Ambos servidores HTTP pueden usar 8080. Para la interfaz actual debe estar ahí
el agente Python. Usar otro puerto si se levanta además el servidor C; cambiar
el puerto del agente exige ajustar también el proxy de desarrollo.

## Compilación y validación

```bash
# Componentes C; no compila Héctor ni React
make
make test

# Contratos de generación progresiva, sin GPU
python3 tools/native_progress_test.py

# Interfaz, desde interfaz/
npm run check
npm test
npm run build
```

`make test` no cubre por sí solo todas las pruebas Python, React o de modelos
reales. Los informes indican qué se ejecutó y con qué modelo. Los cambios de
esta revisión documental no constituyen nuevas mediciones de rendimiento.

## Organización

- `hexos/agent/chat_backend/`: ciclo, contexto, herramientas, verificación y HTTP.
- `hexos/agent/native*.py`: plantilla y transporte nativo de Gemma.
- `hexos/agent/`: catálogo, notas, documentos, inventario, web y almacén de trabajo.
- `interfaz/`: conversación, esfera, telemetría y ventana Código/Interfaz.
- `hexos/src/`: supervisor y servidor C conservados.
- `hera/`, `memory_core/`, `hnf_ext/`: memoria y componentes C.
- `runtime/`: lanzadores y datos locales; `tools/`: pruebas/utilidades.
- `docs/`, `informes/`: contratos y evidencia; `docs/historico/`: documentos sustituidos.

La voz, una autonomía general certificada y ejecutar cualquier proyecto generado
no están implementados por el hecho de disponer de chat, herramientas y preview.
La dirección del producto sigue siendo un modelo y un chat; el multichat del
servidor C no se anuncia como capacidad de esta interfaz.
