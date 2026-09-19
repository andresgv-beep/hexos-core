# Política de residencia del runtime

## Alcance actualizado (2026-09-19)

Esta política automática corresponde a `hexos_serve` y `runtime/run-helios-chat`.
El agente nativo Python utiliza otra entrada: `NativeTransport` fija
`HELIOS_EMBED_MMAP=1` y `HELIOS_VISION_MMAP=1` al crear el proceso, incluso si
había otro valor en el entorno, y no ejecuta el probe automático descrito abajo.
No afirmar paridad de overrides ni autodetección entre ambas rutas.
La asignación de la sesión auxiliar en NDJSON es diferida y de 1024 tokens.

## Objetivo

HEXOS decide cómo arranca Héctor; Héctor valida y ejecuta el mecanismo. La
política no depende del nombre comercial de la GPU ni de una estimación por
compute capability.

Para activar automáticamente la visión respaldada por HNF/RAM deben cumplirse
las tres condiciones:

1. el proceso será persistente;
2. el dispositivo CUDA visible expone `pageableMemoryAccess`;
3. el dispositivo expone `concurrentManagedAccess`.

HEXOS consulta directamente esos dos atributos mediante `libcuda.so` cargada
con `dlopen`. No enlaza CUDA, no necesita el Toolkit y no crea un contexto.

## Variables que hereda Héctor

- `HELIOS_EMBED_MMAP=1` es el default de producto. Un valor definido por el
  usuario se conserva.
- `HELIOS_VISION_MMAP` acepta `auto`, `0` o `1`. Si no existe equivale a
  `auto`.
- `HELIOS_MMAP_DOUBLE_BUFFER` usa la misma semántica y es genérica para
  cualquier bloque file-backed. En `auto` exige proceso persistente, acceso
  pageable/managed concurrente y al menos un motor de copia asíncrono.
- En `auto`, un proceso persistente compatible recibe `1`; cualquier otro
  caso recibe `0`.
- Un `0` o `1` explícito siempre manda. El `1` forzado no evita la validación
  interna de Héctor: en hardware incompatible el loader debe fallar de forma
  visible.

Los sinónimos `on/off`, `true/false` y `yes/no` se aceptan en la frontera de
HEXOS y se normalizan a `1/0` antes de ejecutar el motor. Cualquier otro valor
es un error de configuración.

## Puntos de entrada

`hexos_serve` aplica la política en el proceso hijo inmediatamente antes de
`exec`. Así puede consultar el driver sin inicializar CUDA en el supervisor ni
hacer `fork` después de inicializarlo.

`runtime/run-helios-chat` usa `hexos_runtime_probe` y exporta la misma decisión
al chat de terminal. `make chat` construye el probe antes de arrancar.

La decisión puede inspeccionarse sin cargar un modelo:

```bash
make -C hexos runtime-probe
hexos/bin/hexos_runtime_probe vision-mmap persistent
hexos/bin/hexos_runtime_probe mmap-double-buffer persistent
```

En la RTX 5070 Laptop usada para certificar Gemma 4 V8, ambas salidas son
`auto-on`, con `pageable=1`, `concurrent=1` y dos motores asíncronos.

## Capacidades del modelo y separación de responsabilidades

HexOS ya puede consultar modalidades y adaptadores mediante
`helios_model_probe`, la frontera metadata-only de Héctor. No duplica el
parser HNF, no enlaza C++/CUDA y no decide por el nombre del fichero:

```bash
make -C hexos model-info
hexos/bin/hexos_model_info modelo.hnf /ruta/a/helios_model_probe
```

`hexos_serve` ejecuta la misma sonda antes de cargar pesos. `--probe` fija su
ruta, `HELIOS_MODEL_PROBE` hace lo mismo por entorno y `--no-probe` conserva
el arranque de compatibilidad. Si la sonda no está instalada, avisa y continúa
en texto para no romper despliegues existentes.

El resultado se publica en `GET /api/status`: arquitectura textual,
modalidades presentes, estado del adaptador e identificador estable. Así la UI
podrá mostrar adjuntos únicamente cuando el runtime los soporte sin conocer
Gemma, SigLIP o cualquier arquitectura futura.

No se cambia el binario ejecutado: `helios_chat` carga el adaptador declarado
por el HNF y HexOS ya acepta imágenes RGB8 para el siguiente turno. El
transporte se documenta en
[MULTIMODAL_TRANSPORT.md](MULTIMODAL_TRANSPORT.md). El selector de la interfaz
React actual ya está conectado al JSON del agente Python, no a ese endpoint C.
La capacidad de visión del HNF sigue siendo necesaria.

El doble buffer pertenece al pipeline genérico de Héctor, no a Gemma 4. Cada
arquitectura declara fases y el runtime común administra las dos ventanas,
eventos y stream de copia. En Gemma 4 reduce la torre caliente de 97,74 a
73,25 ms con 20 MiB adicionales.
