# E0 — Inventario de prompts activos y su propietario

**Base auditada:** `Hector-engine@1bca9b5` · **Fecha:** 2026-08-02

Segundo entregable de E0 del [plan de evacuación](PLAN_EVACUACION_COGNITIVA.md).
Antes de mover nada hay que saber **cuánto texto cognitivo vive dentro del
motor y quién debería ser su dueño**. Este inventario es el mapa de lo que la
fase E5 tendrá que centralizar.

`helios_chat.cpp` son **1.958 líneas**. Ningún bloque de abajo pertenece a
Héctor según la tabla de propiedad del plan: Héctor solo puede poseer las
plantillas sintácticas del modelo (ChatML, Gemma) y el tokenizer.

## Bloques de prompt activos

| # | Bloque | Dónde | Dueño destino | Familia E5 |
|---|---|---|---|---|
| 1 | Identidad de Helios (voz independiente, "no inventes biografía", regla de parada) | `helios_chat.cpp` prefijo de sesión | HERA | 1 · identidad estable |
| 2 | Ejemplos de voz (tres intercambios «»→«») y prohibición de coletilla | `helios_chat.cpp` prefijo | HERA | 1 · identidad estable |
| 3 | Nombre del perfil actual / "todavía no conoces a la persona" | `helios_chat.cpp` prefijo | HERA | 2 · contexto autoritativo |
| 4 | Encabezado de `facts.md` ("PERFIL DE LA PERSONA ACTUAL…") | `helios_chat.cpp::load_memories` | HERA | 2 · contexto autoritativo |
| 5 | Encabezado de memoria episódica ("MEMORIA DE ESTA RELACIÓN…") | `helios_chat.cpp::load_memories` | HERA | 2 · contexto autoritativo |
| 6 | Puente de compactación ("lo que llevas hablado en ESTA MISMA sesión") | `helios_chat.cpp` prefijo | CK (continuidad) | 2 · contexto autoritativo |
| 7 | Recordatorio final ("sigues siendo Helios… cumple el acto y termina") | `helios_chat.cpp` prefijo | HERA + CK | 1 y 3 |
| 8 | Contrato por acto (18 instrucciones, una por `ResponseAct`) | `ck_policy.cpp::act_instruction` | CK | 3 · contrato efímero |
| 9 | Envoltorio del contrato ("Contrato CK interno; no lo cites…") | `ck_policy.cpp::response_contract` | CK | 3 · contrato efímero |
| 10 | Encuadre para Gemma ("[INSTRUCCION INTERNA DEL CK]…") | `ck_policy.cpp::frame_user_message` | CK + adaptador | 3 · contrato efímero |
| 11 | Freno social (tres frases, sin listas ni elogios) | `ck_policy.cpp::social_steer` | CK | 3 · contrato efímero |
| 12 | Normalización de relaciones en recall ("loro llamado X" → mascota=X) | `ck_policy.cpp::prepare_recall_context` | HERA | 2 · contexto autoritativo |
| 13 | Prompt de destilación ("3 a 6 frases en PRIMERA PERSONA…") | `helios_chat.cpp::distill_from_transcript` | HERA | 4 · extracción posterior |
| 14 | Prompt de extracción de candidatos ("eres un extractor de datos") | `helios_chat.cpp` | HERA | 4 · extracción posterior |
| 15 | Encuadre de `/pegar` ("Te paso un texto. Léelo y coméntame lo esencial") | `helios_chat.cpp` | UI o CK | 3 · contrato efímero |

**Ninguno de los 15 pertenece a Héctor.** Los dos únicos textos que sí son
suyos son las plantillas de turno (`<|im_start|>`/`<|turn>`) y los tokens
especiales del tokenizer.

## Reglas de comportamiento que NO son prompt

Estas viven como código en el motor y también deben evacuarse, pero no son
texto y por tanto no entran en la familia de renderers de E5:

| Mecanismo | Dónde | Dueño destino |
|---|---|---|
| Clasificador de actos | `ck_policy.cpp::classify_turn` | CK |
| Registro social con histéresis | `helios_chat.cpp` (estado del bucle) | CK |
| Continuidad de artefacto (3 turnos) | `helios_chat.cpp` (estado del bucle) | CK |
| Presupuestos visible y de pensamiento | `ck_policy.cpp` | CK |
| Suelos de temperatura por registro | `helios_chat.cpp::temperature_for` | CK |
| Rienda de pensamiento e inyección de cierre | `helios_chat.cpp` bucle de decode | CK propone, Héctor ejecuta |
| Detector de bucles y corte por presupuesto | `helios_chat.cpp` bucle de decode | CK propone, Héctor ejecuta |
| Deduplicación de memoria | `helios_chat.cpp` | Memory Core |
| Validación de la destilación (`looks_like_memory`) | `helios_chat.cpp` | HERA |
| Cuarentena de entradas tóxicas al leer | `helios_chat.cpp::load_memories` | HERA |
| Compactación en caliente | `helios_chat.cpp` | CK decide, Héctor ejecuta |

## Observación para E5

El literal más peligroso no es el más largo, es el que **contradice a otro**.
Hoy conviven la identidad ("no adoptas un papel de servicio"), los ejemplos de
voz (calidez con emoji) y un `facts.md` que puede decir "prefiere que le
hablen sin emojis". Nada arbitra entre ellos y el modelo elige por recencia.
Cuando los prompts sean renderizaciones de estado estructurado, esa
contradicción se resuelve **en los datos, antes de renderizar** — que es
exactamente lo que hoy no se puede hacer.
