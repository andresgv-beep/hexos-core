# Política de residencia del runtime

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

## Separación de responsabilidades

La política no detecta todavía modalidades dentro del HNF ni cambia el
binario que se ejecuta. Preparar el modelo, elegir el runner multimodal y
aceptar imágenes desde la UI son pasos de producto posteriores. Definir la
variable para un motor de solo texto es inocuo.

El doble buffer pertenece al pipeline genérico de Héctor, no a Gemma 4. Cada
arquitectura declara fases y el runtime común administra las dos ventanas,
eventos y stream de copia. En Gemma 4 reduce la torre caliente de 97,74 a
73,25 ms con 20 MiB adicionales.
