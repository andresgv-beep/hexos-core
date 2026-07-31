# CK v4 — EL NORTE (escrito el 2026-07-29, la noche que Héctor arrancó)

## ✅ ESTADO REAL (actualizado 2026-07-31)

**El proto-CK ya no es papel: es `helios_chat` (repo Hector-engine).**
Construido y verificado el 2026-07-30:

- Chat multi-turno con continuidad por KV (solo se prefillea el turno nuevo,
  ~200-450 ms; la historia jamás se reprocesa)
- System prompt de identidad, prefilleado una vez (el "prefijo permanente")
- Thinking adaptativo nivel 1: triviales → /no_think; rienda de pensamiento
  (techo 20/500/1000 + inyección forzada de </think>); rescate de turnos mudos
- Presupuesto de respuesta por tipo (80/350/1500 visibles, corte en fin de frase)
- Governor de ritmo: think a tope, texto visible a ritmo de lectura con
  aceleración progresiva (18→40→libre); /fast
- Penalty de repetición quirúrgico (jamás tokens especiales — lección: penalizar
  </think> rompe el cierre del pensamiento)
- **MEMORIA EPISÓDICA PERSISTENTE (nivel 1)**: al /salir el modelo destila su
  resumen → ~/.helios/episodic.md con fecha; al arrancar entra al prefijo.
  Verificado entre procesos: "Hola Andrés, recuerdo que eres el creador..."
- Memoria explícita determinista: "guarda en memoria: X" y /recuerda escriben
  a disco sin teatro del modelo; /memoria enseña el diario
- Framing de confianza (el reflejo "no tengo acceso a datos personales" le
  ganaba a la memoria cargada) + instrucciones privadas (anti-recitado)
- Privacidad por capas: código publicable / dueño en ~/.helios/owner /
  diario fuera de todo repo. Futuro: "exportar limpio" quita bloques 0x5/0x6
- Motor: sampling 100% GPU (temp = greedy, ~85-95 tok/s), panel HEXOS honesto,
  helios_chat anuncia COGNITIVE+INFERENCE en el blackboard

Lección madre del día: **cada mecanismo nació de un fallo real en uso, no de
especulación** — el camino inverso a los contratos v3.

**Principio de diseño (de Andrés, 2026-07-31): el instinto natural del usuario
es la spec.** Si el usuario pega texto a lo bruto, el sistema lo digiere — no
se le enseña un comando, se le quita el obstáculo. Nada de liturgias: lo que
haría cualquier persona con su asistente tiene que simplemente funcionar.
(Origen: dos READMEs pegados a pelo → detección automática de pegado, mejor
que el /pegar que la precedió.)

---

## La tesis (en palabras de Andrés)

> No es hacerlo más listo en el sentido vitaminado a un 200B. Es que sepa en
> cada momento lo que recuerda, por cada día recorrido. No sabrá crearte un
> kernel de Héctor de la nada — pero sí tendrá más conocimiento sobre lo que
> hay, a medida que le hablas y le pasas documentos.

**Cilindrada, la justa (4B). Kilometraje contigo, todo.** La continuidad entre
sesiones es la forma de inteligencia que hoy no existe en local y la que más
importa al usuario. "Helios no son los pesos. Helios es lo que recuerda."

## El reencuadre clave

El contexto NO es la memoria: es una **ventana sobre la memoria**. Contexto
lleno ya no significa fin de la conversación — significa consolidar (bajar lo
viejo a episódica, destilar lo esencial) y seguir. La conversación respira,
no muere.

## Los 4 mecanismos reales (cada uno con implementación, no fe)

1. **Incertidumbre por logits**: la entropía de la distribución antes de cada
   token es duda medible. Dispara búsqueda en memoria o un "no lo sé" honesto.
   Sustituye al CoherenceChecker/mood de los contratos v3 (que eran humo).
2. **Reflexión a coste cero**: la pasada post-turno (extraer hechos, actualizar
   episódica, proponer esenciales) corre en background mientras el usuario lee
   (1.5 s a 95 tok/s). El "sueño" consolida de noche: el cómputo ocioso local
   es gratis — ventaja estructural que la nube no puede copiar por usuario.
3. **Cirugía de KV cache**: identidad (HNF-EXT) como prefijo permanentemente
   cacheado; memoria inyectada sin re-prefill. Posible solo con motor propio.
4. **Razonamiento adaptativo**: thinking como presupuesto administrado por el
   CK — 0 tokens para lo trivial, 2000 para donde los logits dudan. Un 4B/E2B
   con thinking rinde como 3-4× su tamaño (no subestimar al Gemma E2B).

## Deuda nacida del uso real: estado conversacional multidimensional

El `bool trivial` del proto-CK ya se ha quedado pequeño. No basta convertir la
conversación en una escala única de frío/caliente, think/no-think o temperatura
alta/baja. El estado debe tener **varios ejes independientes y observables**:

- **intención**: social, pregunta factual, código, continuación, corrección o
  confirmación;
- **carga cognitiva**: inmediata, normal o profunda;
- **registro social**: neutral, cercano, humorístico o delicado, inferido del
  tono que trae el usuario y sin fingir emociones internas;
- **confianza**: alta, duda medible o contradicción activa;
- **estado de memoria**: ninguno, candidato, esperando confirmación,
  confirmado o sustituido;
- **continuidad**: depende del turno anterior, de un documento o de un bloque
  de código que sigue activo;
- **forma de respuesta**: breve, técnica, pedagógica o creativa.

No resucitar el `mood f32` de los contratos v3: cada eje debe tener una señal
real y una consecuencia concreta. La política resultante decide temperatura,
top-k/top-p, presupuesto visible, thinking, consulta/escritura de memoria y qué
información debe sobrevivir a la compactación.

### Fallos observados que fijan la especificación

1. Tras pegar 192 líneas de HQS, la respuesta corta `velocidad` fue marcada
   como trivial por longitud, elevó la temperatura a 0,90 y perdió el carácter
   de continuación técnica. Debe heredar intención y artefacto del turno
   anterior.
2. Al compactar cerca de 4096 tokens, el intercambio reciente conservó solo
   300 caracteres del mensaje grande. El modelo dejó de tener el código y
   respondió de forma genérica. Los documentos y bloques de código necesitan
   identidad propia y conservación explícita, no un `substr` ciego.
3. Ante datos falsos sobre Andrés, Gemma 4 pasó de defender el recuerdo a
   reconocer la contradicción, pedir confirmación y extraer el dato correcto.
   Sin embargo, el runtime solo escribió candidatos y el modelo afirmó haber
   actualizado su base de datos. Confirmar debe promover el hecho nuevo y
   marcar el anterior como sustituido; nunca acumular verdades incompatibles.

### Pruebas de aceptación para cuando se implemente

- `velocidad`, después de hablar de HQS, produce `continuación técnica + breve`,
  no `trivial`;
- una pregunta sobre código pegado sigue siendo contestable después de
  compactar;
- una corrección confirmada sustituye el hecho falso y sobrevive al siguiente
  proceso;
- antes de la promoción, Helios dice que ha tomado nota como propuesta, no que
  ya modificó su memoria;
- un saludo aislado continúa siendo social, breve y barato.

Esta política se descubre primero en `helios_chat` mediante uso diario. Cuando
se estabilice, pertenece al CK/HERA real, no al motor Héctor.

## Lo genuinamente único de HELIOS (el 20% que nadie tiene)

- Memoria + identidad DENTRO del archivo del modelo (HNF-EXT). Copias el
  .hnf = copias a la persona completa. Nadie más controla formato Y motor.
- Integración vertical: un binario, sin Python, sin servicios: inferencia
  CUDA propia + memoria persistente + monitor (HEXOS).
- Escritura de memoria esencial ultraconservadora (cuota 1-3/día, rechazar
  95%, aprobación del usuario al principio).
- Futuro (el moonshot semi-realista): HLORA nocturno — destilar el día en un
  adapter LoRA guardado en otro bloque del mismo HNF. Memoria en tres
  tiempos: KV (minutos), episódica (meses), pesos (para siempre).

## El claim honesto (leer esto cuando vengan las dudas)

NO somos "los primeros en IA local con memoria": Letta/MemGPT (corre contra
modelos locales), Mem0, Open WebUI y una docena de proyectos RAG ya lo hacen.
Competir por ese titular es perder contra equipos con años de ventaja.

Lo que SÍ es verdad y nadie puede quitarnos:

> El único runtime local donde memoria e identidad viven DENTRO del archivo
> del modelo, servido por un motor propio, en un solo binario, sin Python
> ni servicios externos.

Nadie más *puede* hacerlo: Letta no tiene motor; Ollama no tiene formato
propio con slots libres (GGUF no tiene dónde meter recuerdos). Héctor + HNF
son las dos piezas que lo habilitan, y ya funcionan juntas.

Y un territorio virgen de verdad: **HLORA nocturno** — memoria que acaba en
los pesos, destilada durmiendo, en otro bloque del mismo archivo. Las grandes
no lo harán: su negocio no soporta un modelo por usuario. Letta consolida a
TEXTO; nadie destila a pesos dentro del propio archivo del modelo.

### Mapa competitivo real (investigado 2026-07-29)

| Sistema | Historial | Mem. semántica | Compacta | Reflexión bg | Motor/KV propio |
|---|---|---|---|---|---|
| LM Studio | Sí | No | Trunca/desliza | No | Parcial |
| Open WebUI | Sí | Sí | Sí (resumen) | Vía funciones | No |
| AnythingLLM | Sí | RAG | Parcial | Limitado | No |
| **Letta/MemGPT** | Sí | Sí, jerárquica | Sí | **Sí (sleeptime)** | No |
| Helios HOY | ❌ | ❌ | ❌ | ❌ | **✅** |

CORRECCIÓN a lo dicho antes: el "ciclo de sueño" NO es original — Letta ya
tiene sleeptime/dreaming en producción. Lo nuestro solo aporta la *economía*
(atarlo a HEXOS: ejecutar con GPU fría y ociosa, presupuesto real de VRAM).

OJO al vicio: cualquier tabla donde "Helios" tenga todo ✅ es papel. Letta las
tiene funcionando con usuarios; nosotros en un .md. La única casilla nuestra
real hoy es motor/KV — y es la que nadie puede copiar.

### Qué desbloquea el co-diseño Héctor+HEXOS (imposible con motor ajeno)

1. **Compactación a nivel KV, no de texto**: desalojar rangos del cache y
   conservar el resto ya calculado → re-prefill cero. Los demás resumen y
   re-procesan el prompt entero. Prior art: StreamingLLM (attention sinks +
   ventana reciente). Ojo: posiciones RoPE quedan no contiguas — medir.
2. **Prefijo de identidad cacheado permanentemente** (HNF-EXT): se prefilla
   una vez por sesión, no por turno.
3. **Logits crudos**: distribución completa → incertidumbre medible. Único
   mecanismo honesto de metacognición.
4. **Embeddings en otro slot del mismo HNF**: bge/e5 pequeño cargado por
   Héctor, mismo pool de scratch, mismo presupuesto VRAM. Un binario.
5. **HEXOS con autoridad homeostática**: el sueño se dispara por estado real
   de la máquina (GPU <60°, 2 GB libres, 5 min ocioso, con corriente). Letta
   lanza su sleeptime a ciegas: no sabe nada del hardware.
6. **Spillover VRAM↔RAM**: estaba en los contratos al 0%; solo posible con
   motor propio.

**El precio del foso (honesto):** ningún bug es de otro. Ollama hereda gratis
cada mejora de llama.cpp; nosotros la implementamos o no la tenemos (ejemplo
vivo: el prefill naive de Héctor). Se paga en tiempo propio.

**Disciplina anti-papel:** la interfaz Héctor↔HEXOS se queda ESTRECHA — el
struct de shm ya escrito y nada más. Métricas y presupuestos por ahí, cero
acoplamiento profundo. Fusionar los proyectos "para hacerlo bien" = volver al
papel. (Nota práctica: el KV cache de los tests está a max_seq_len=128;
para trabajo real de contexto hay que subirlo.)

### Acción de reconocimiento (antes de construir)

**Instalar Letta contra Ollama y usarlo una semana.** Es el estado del arte de
lo que queremos, corriendo local y gratis. En 7 días se aprende lo que en papel
cuesta 3 meses: qué se siente que te recuerde, qué recupera mal, cuánto molesta
la latencia. Patrón a robar sin pestañear: sus **memory blocks persistentes en
contexto** (persona/usuario/proyecto) = nuestro HNF-EXT, pero con tamaños y
formatos ya validados en la práctica.

**Objetivo sano, no frágil:** no "ser el primero" (mañana sale algo en HN y
hunde el ánimo — y ya sabemos cómo acaba el ánimo hundido aquí), sino "ser el
único que lo hace así, y que funcione a diario para mí". Si en dos meses el
asistente recuerda solo lo del prefill de Héctor y ese archivo cabe en un USB
con su memoria dentro, ya ganamos. Lo demás llega después, y solo si eso existe.

## Qué se tira de los contratos v3

El CK de 6 módulos "pensantes" (IntentClassifier, Reasoner, IdentityGuard,
mood f32): sin mecanismo, no se construye. Se reduce a: system prompt bien
armado + reflexión post-turno + los 4 mecanismos de arriba. La filosofía,
fuera de las specs.

## Orden de construcción (anti-patrón papel: integrar antes de diseñar más)

1. **La boda** (1-2 semanas): Héctor escribe tokens/s y VRAM al shm de HEXOS
   (el struct ya tiene los campos). Dashboard vivo. Las dos mitades se conocen.
   - Fixes previos: Makefile hexos (-D_GNU_SOURCE), overflow en hnf_ext load,
     escritura atómica (tmp+rename), mutex process-shared en IPC.
2. **Memoria mínima que importa** (1-2 meses): modelo de embeddings pequeño
   real (bge/e5, NO el 4B), store con búsqueda por similitud (SQLite antes que
   JSON sin lectura), top-k al prompt, esenciales a HNF-EXT con aprobación.
   Ingesta de documentos al store semántico.
3. **Evaluación desde el día 1**: ¿la memoria recuperada era la correcta?
   Medido, no sentido. La gran ausente de los v3.
4. Después, y solo después: razonamiento adaptativo, enrutador multimodal
   (Gemma E2B de segundo cerebro en otro slot del HNF), sueño consolidador.

## Estado del motor (2026-07-29)

Héctor: Qwen3-4B a ~95 tok/s (RTX 5070 Laptop), formatos compactos
HQ4.1K/HQ5.1K, CUDA Graphs, codo a codo con Ollama (92-120). Detalles en
OPTIMIZATION_NOTES.md del repo Hector-engine.
