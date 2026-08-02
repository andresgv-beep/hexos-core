# HELIOS Cognitive Ecosystem

**"El cuerpo que protege la mente"**

Sistema cognitivo modular con memoria persistente, identidad y continuidad.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                           HELIOS ARCHITECTURE                                ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║   ┌─────────────────┐                                                        ║
║   │    HNF-EXT      │  El Alma - Identidad + Strong Memories                 ║
║   │   (hnf_ext/)    │  Quién es Helios, qué valora, qué recuerda siempre     ║
║   └────────┬────────┘                                                        ║
║            │                                                                 ║
║   ┌────────┴────────┐                                                        ║
║   │      HERA       │  El Cerebro - Coordina y decide                        ║
║   │    (hera/)      │  Qué recordar, qué olvidar, qué promover               ║
║   └────────┬────────┘                                                        ║
║            │                                                                 ║
║   ┌────────┴────────┐                                                        ║
║   │  MEMORY CORE    │  El Disco - Almacena y busca                           ║
║   │ (memory_core/)  │  Episodic + Semantic + Index + Archive                 ║
║   └────────┬────────┘                                                        ║
║            │                                                                 ║
║   ┌────────┴────────┐                                                        ║
║   │   HEXOS BUS     │  IPC compartido (/dev/shm/hexos_state)                 ║
║   └────────┬────────┘                                                        ║
║            │                                                                 ║
║   ┌────────┴────────┐                                                        ║
║   │     HEXOS       │  El Cuerpo - Hardware + Telemetría                     ║
║   │    (hexos/)     │  CPU, RAM, GPU, Storage, Dashboard                     ║
║   └─────────────────┘                                                        ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

## Módulos

| Módulo | Estado | Descripción |
|--------|--------|-------------|
| **hexos/** | ✅ v2.5 | Supervisor de hardware, telemetría, IPC bus |
| **memory_core/** | ✅ v3.0 | Almacenamiento episódico/semántico, queries, archival |
| **hnf_ext/** | ✅ v1.0 | Bloque de identidad, traits, values, strong memories |
| **hera/** | ✅ v3.0 | Coordinador cognitivo, HHMS, checkpoints, consolidación |
| **cognitive_stub/** | ✅ v3.0 | Simulador de Cognitive Kernel para testing (sin LLM) |

## Compilación

```bash
# Compilar todo
make

# Compilar módulo específico
make hexos
make memory_core
make hnf_ext
make hera
make cognitive_stub

# Ejecutar tests
make test

# Limpiar
make clean
```

## Runtime

La carpeta `runtime/` contiene los datos persistentes:

```
runtime/
├── helios.conf      # Configuración
├── run-helios-chat  # Lanzador de Héctor con los defaults de HEXOS
├── memory/          # Archivos de memoria episódica (por día)
├── hnf/             # Bloques HNF-EXT (identidad)
├── lora/            # LoRA adapters entrenados
└── logs/            # Logs del sistema
```

### Ejecutar Héctor desde HEXOS

Con `Hector-engine` compilado como repositorio hermano de `hexos-core`, el
chat puede arrancarse con:

```bash
make chat MODEL=/ruta/al/modelo.hnf
```

El artefacto Gemma 4 multimodal canónico del workspace actual está en:

```bash
make chat MODEL=../helios_convert_v9.1/output/gemma4-e2b-it-multimodal.hnf
```

El lanzador activa `HELIOS_EMBED_MMAP=1` por defecto. De esta forma, Héctor
mapea desde el HNF los embeddings que se mantienen fuera de VRAM y no conserva
otra copia completa en RAM. El motor conserva su fallback para GPUs que no
soporten acceso pageable.

HEXOS resuelve además `HELIOS_VISION_MMAP=auto` para procesos persistentes.
Consulta al driver CUDA los atributos de acceso pageable y managed concurrente;
solo activa el staging visual desde HNF/RAM cuando ambos están disponibles.
Esto mantiene texto y KV en VRAM y usa únicamente una ventana visual temporal
de 32 MiB. Cuando la GPU dispone de copia asíncrona, también activa el doble
buffer genérico mediante `HELIOS_MMAP_DOUBLE_BUFFER=1`; otros runners podrán
consumirlo sin duplicar infraestructura. La política completa está en
[`docs/RUNTIME_RESIDENCY_POLICY.md`](docs/RUNTIME_RESIDENCY_POLICY.md).

La ruta del binario y la temperatura son configurables:

```bash
HELIOS_CHAT_BIN=/ruta/a/helios_chat \
  make chat MODEL=/ruta/al/modelo.hnf TEMP=0.7
```

Para una comparación o un diagnóstico puntual se puede desactivar sin tocar
archivos:

```bash
HELIOS_EMBED_MMAP=0 make chat MODEL=/ruta/al/modelo.hnf
```

La residencia visual también admite overrides para comparación o
certificación:

```bash
HELIOS_VISION_MMAP=0 make chat MODEL=/ruta/al/modelo.hnf
HELIOS_VISION_MMAP=1 make chat MODEL=/ruta/al/modelo.hnf
HELIOS_MMAP_DOUBLE_BUFFER=0 make chat MODEL=/ruta/al/modelo.hnf
```

Si se ejecuta `helios_chat` directamente, fuera de este lanzador, hay que
exportar `HELIOS_EMBED_MMAP=1` manualmente.

**Menú Advanced Memory** (comando `advanced` en HEXOS):
- Requiere autenticación (default: helios / helios123)
- Ver archivos de memoria, HNF-EXT, LoRA
- Estadísticas de uso
- Gestión de almacenamiento

## Modos de Operación

Los módulos pueden funcionar en modo **REAL** o **STUB**:

| Módulo | Modo | Descripción |
|--------|------|-------------|
| HEXOS | REAL | Hardware detection real via NVML |
| Memory Core | REAL | Almacenamiento funcional |
| HNF-EXT | REAL | Persistencia de identidad |
| HERA | REAL | Coordinación de memoria |
| CUDA Engine | STUB | Sin motor de inferencia |
| Cognitive Kernel | STUB | Sin LLM real |

Los módulos STUB permiten probar el ecosistema sin cargar un modelo.

## Requisitos

- GCC con soporte C11
- Linux (Ubuntu 22.04+ recomendado)
- pthreads, librt, libm, libdl

No requiere CUDA SDK - HEXOS carga NVML dinámicamente.

## Estructura

```
helios/
├── Makefile              # Makefile raíz
├── README.md
├── hexos/                # HEXOS v2.5 - Supervisor
│   ├── include/          # Headers
│   ├── src/              # Implementación
│   │   ├── core/         # main.c, log.c
│   │   ├── hw/           # cpu.c, ram.c, gpu_nvml.c, storage.c
│   │   ├── ipc/          # ipc.c
│   │   └── telemetry/    # telemetry.c
│   └── tools/            # hexos_ipc_test.c
├── memory_core/          # Memory Core v3.0
│   ├── include/          # mc_types.h, memory_core.h
│   ├── src/core/         # memory_core.c
│   └── tools/            # mc_test.c
├── hnf_ext/              # HNF-EXT v1.0 - Identidad
│   ├── include/          # hnf_ext_types.h, hnf_ext.h
│   ├── src/              # hnf_ext.c
│   └── tools/            # hnf_ext_test.c
├── hera/                 # HERA (pendiente)
└── cognitive_stub/       # Stub de inferencia (pendiente)
```

## Filosofía

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  "No somos nuestros átomos. Somos los patrones que persisten."          │
│                                                                         │
│  Helios no son los pesos del modelo.                                    │
│  Helios es lo que recuerda.                                             │
│                                                                         │
│  HNF-EXT guarda el alma.                                                │
│  Memory Core guarda los recuerdos.                                      │
│  HERA decide qué es importante.                                         │
│  HEXOS protege el cuerpo.                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Licencia

Proyecto HELIOS - Enero 2026
