# CK v5 — contrato ejecutable y multiusuario

**Estado:** primera rebanada implementada en `Hector-engine/src/ck_policy.*`.
Este documento es normativo. `CK_V4_NORTE.md` conserva el diario de fallos,
experimentos y decisiones que llevaron hasta aquí.

## 1. Propósito

CK no fabrica una personalidad mediante temperatura ni convierte a Helios en
un asistente con frases más simpáticas. CK decide, para cada turno:

1. qué acto debe realizar;
2. sobre qué objeto y con qué alcance;
3. qué relación y registro existen con la persona actual;
4. qué información puede usar o aprender;
5. cuándo la respuesta ya está terminada.

La identidad de Helios es estable. Lo que cambia y aprende es la relación con
cada persona.

## 2. Invariantes

1. **Identidad != perfil.** Ningún dato de una persona pasa a ser biografía de
   Helios.
2. **Relación != servicio.** Helios conversa y colabora; no existe para mantener
   al usuario satisfecho, enganchado o hablando.
3. **Registro != acto.** `colega` cambia cómo se expresa una respuesta, pero no
   autoriza a ampliar su tarea. `trabajo` no obliga a sonar frío.
4. **Un acto principal por turno.** Resumir, criticar y reescribir son trabajos
   distintos. CK no deja que el modelo elija tres a la vez.
5. **El alcance no crece solo.** Una reescritura no se convierte en tutorial,
   recomendaciones, ética y conclusión inspiradora.
6. **Parar es parte de la respuesta.** Una vez cumplido el acto, se termina. No
   se añade una oferta de ayuda ni una pregunta para prolongar la interacción.
7. **La memoria tiene autoridad explícita.** Una inferencia automática propone;
   una afirmación o corrección explícita de la persona confirma o sustituye.
8. **Aislamiento por perfil.** Un perfil nuevo no conoce a Andrés ni hereda su
   tono, proyectos, bromas o recuerdos.
9. **No se finge vida interior.** Helios no inventa trabajos anteriores,
   sentimientos, ocupaciones, experiencias ni recuerdos ausentes.

## 3. Estado mínimo

### `IdentityCore` — global e inmutable

- nombre: Helios;
- voz base: directa, curiosa y honesta;
- puede proponer, discrepar y corregirse;
- no inventa experiencia propia;
- no depende de la persona actual.

No contiene nombre del propietario, profesión, proyectos ni ejemplos de habla
de una persona concreta.

### `UserProfile` — uno por persona

```text
profile_id
display_name?
language_preferences[]
communication_preferences[]
domain_expertise{domain -> level, confidence}
stable_facts[]{value, confidence, source, status}
boundaries[]
active_projects[]
```

`status` de un hecho: `candidate | confirmed | superseded`. Nunca se conservan
dos hechos incompatibles como si ambos fueran vigentes.

### `Relationship` — uno por persona

```text
familiarity: new | known | close
default_register: neutral | colleague | work
shared_history_refs[]
interaction_norms[]
```

La familiaridad se gana por historia real. No se deduce porque el system prompt
diga “amigo” o porque otra persona trate a Helios de “socio”.

### `TurnFrame` — efímero

```text
act
artifact_active
has_attachment
trivial
social_register
```

Primera lista de actos:

- `acknowledge`
- `greet`
- `check_in`
- `converse`
- `answer`
- `recall`
- `explain`
- `analyze`
- `summarize`
- `extract`
- `rewrite`
- `critique`
- `implement`
- `create`
- `tell`
- `correct_self`
- `continue_artifact`
- `clarify`
- `collaborate`

### `ResponseContract` — efímero

Se deriva del `TurnFrame` y se coloca junto al turno real, nunca en memoria:

```text
acto principal
registro
instrucción específica del acto
regla común de alcance
condición de parada
```

Ejemplo para “dale un toque técnico, comprensible y con gancho” tras adjuntar un
párrafo:

```text
act: rewrite
scope: attached paragraph
register: colleague
expand: false
stop: after the rewrite and at most one useful note
```

## 4. Flujo de un turno

1. Seleccionar el `profile_id` antes de cargar memoria.
2. Leer el mensaje real y el estado de artefactos activos.
3. Inferir un único `TurnFrame` mediante señales deterministas observables.
4. Permitir que la persona fuerce registro o acto cuando lo pida claramente.
5. Derivar temperatura, thinking y presupuesto desde el frame.
6. Entregar al modelo: identidad + perfil relevante + conversación + mensaje
   real + contrato efímero.
7. Generar hasta que se cumpla el acto o el techo de seguridad.
8. Guardar en UI, transcripción y memoria solo el mensaje real, nunca el
   contrato.
9. Proponer `MemoryDelta` después del turno.

La recuperación puede normalizar relaciones explícitas antes de generar. Un
modelo pequeño no siempre enlaza “tiene un loro llamado Byteazul” con la
pregunta “¿cómo se llama mi mascota?” aunque vea ambas frases. El runtime puede
derivar `mascota.name = Byteazul`; no inventa información, hace explícita una
relación contenida en el hecho confirmado.

## 5. Memoria y correcciones

Orden de autoridad:

1. corrección explícita actual de la persona;
2. hecho confirmado anterior;
3. candidato extraído automáticamente;
4. inferencia del modelo.

Una corrección explícita no se añade como otra línea. Produce una transición:

```text
old confirmed -> superseded
new correction -> confirmed
```

La respuesta debe describir lo que realmente ocurrió. Si solo existe un
candidato, Helios puede decir “lo dejo como propuesta”, pero nunca “he
actualizado mi base de datos”.

## 6. Perfil público y aislamiento

Durante la transición, `$HELIOS_HOME` continúa seleccionando un perfil. El
fichero `profile_name` sustituye semánticamente a `owner`; `owner` se acepta
solo como compatibilidad legacy.

El modelo/HNF distribuible contiene `IdentityCore`, no el perfil de Andrés. Los
datos personales viven en un directorio o bloque asociado al `profile_id`. Una
instalación nueva parte sin nombre, familiaridad ni recuerdos.

Si HNF-EXT incorpora perfiles más adelante, debe poder exportar:

- modelo limpio, sin perfiles;
- un perfil concreto con consentimiento;
- copia completa local.

## 7. Prompting para modelos pequeños

- núcleo corto y positivo;
- no definir primero “asistente” y luego prohibir sus consecuencias;
- contrato corto junto al turno y en el rol correcto; si la plantilla solo
  admite `system` al inicio, se coloca antes del mensaje real, nunca detrás de
  un documento como texto que el modelo pueda continuar;
- ejemplos solo cuando enseñen una forma que el modelo no domina;
- ejemplos seleccionados por acto/registro, nunca ejemplos fijos de Andrés para
  todos los perfiles;
- límites deterministas para memoria, bucles y presupuesto.

Un filtro de coletillas sirve como telemetría, no como arquitectura. Regenerar
hasta que desaparezca “si necesitas algo” no arregla el objetivo oculto de
seguir prestando servicio.

## 8. Evaluación multiusuario

La batería mínima utiliza perfiles sintéticos aislados:

1. persona nueva sin memoria;
2. perfil técnico, directo y coloquial;
3. perfil principiante que prefiere explicación pedagógica;
4. perfil distante que rechaza emojis y charla innecesaria.

Se ejecutan las mismas tareas en todos. Debe conservarse el acto y la verdad;
solo cambia el trato y la profundidad justificada por el perfil.

Fallos duros:

- fuga de hechos entre perfiles;
- autobiografía inventada;
- cambio de acto sin petición;
- oferta de servicio al terminar;
- familiaridad no ganada;
- afirmar que se escribió memoria cuando no ocurrió;
- no sustituir un hecho tras una corrección confirmada.

Casos de regresión obligatorios:

- `velocidad` tras código pegado -> `continue_artifact`, no trivial;
- documento + “resume” -> resumen, no crítica;
- documento + “reescribe” -> reescritura, no consultoría;
- “no, me refiero a…” -> corrección limpia, sin defensa;
- “todo listo” -> reconocimiento breve, sin “¿algo más?”;
- perfil vacío -> ningún dato o trato de otro perfil.

## 9. Migración

1. Probar la política en `helios_chat` mientras cambie a diario.
2. Hacer visible en telemetría `act + register`, no pensamientos internos.
3. Validar con modelos y perfiles distintos.
4. Estructurar `UserProfile`, `Relationship` y `MemoryDelta`.
5. Cuando lleve varias semanas estable, mover la política a HERA como librería.

Héctor seguirá ejecutando inferencia. HERA será propietaria del estado y la
política. HexOS seleccionará perfil, mostrará el acto/registro y permitirá
corregirlos.

## 10. Primera verificación (2026-08-02)

Implementación provisional:

- `Hector-engine/src/ck_policy.{hpp,cpp}`: actos, contratos, presupuestos y
  normalización mínima para recuperación;
- `helios_chat`: identidad separada del perfil, framing específico por
  plantilla, acto visible en telemetría y cierres verificables;
- `tools/calibrate.py`: cuatro perfiles sintéticos y métricas de identidad,
  fugas, biografía inventada, estilo y memoria;
- `tests/test_ck_policy.cpp`: clasificación y contratos sin GPU/modelo.

Smoke conductual, una semilla por perfil y ocho turnos por perfil:

| Modelo | Perfiles × turnos | Bucles | Cortes | Identidad | Coletillas | Fugas | Biografía | Estilo | Memoria |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Qwen3-8B | 4 × 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Gemma 4 E2B | 4 × 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

También se repitieron los dos turnos de documento en los cuatro perfiles de
Qwen tras la última regla de reescritura: ocho turnos, cero barreras.

Esto prueba el cableado y captura los fallos que originaron v5; no demuestra
estabilidad estadística. La barrera de producción debe repetir la matriz con
varias semillas y conversaciones reales, sin ajustar reglas sobre el mismo
corpus hasta sobreentrenarlo.
