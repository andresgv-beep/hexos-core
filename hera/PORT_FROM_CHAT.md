# HERA — nota de portación (2026-07-31)

> **Documento histórico / evidencia de una fase.** Sus pendientes y pruebas
> describen ese corte, no el producto actual. [Estado vigente](../IMPLEMENTATION_STATUS.md)
> (revisado 2026-09-19). La portación ya tiene almacén, perfil, deltas y cola en `hera/src/`; no está toda por comenzar.

> **Por qué este módulo parece inerte:** el código de `hera/src/hera.c` es el
> esqueleto de enero (umbrales fijos, `hera_query_memories` devuelve vacío,
> integración con memory_core detrás de `#ifdef` apagados). **No está muerto:
> está pendiente de sustitución por lógica que YA FUNCIONA en otro sitio.**

## Dónde vive HERA hoy (y por qué está mal)

Toda la política de memoria y orquestación corre dentro de
`Hector-engine/helios_chat.cpp`. Nació ahí por velocidad de iteración durante
los días 2-4 del proyecto, pero **ese es el repo del MOTOR**.

Eso viola la separación del contrato v3.0 §0:

    HERA ES LA MENTE. HEXOS ES EL CUERPO. ENGINE ES EL MÚSCULO.

Un motor de inferencia no debe saber consolidar recuerdos. Mezclarlos
significa que no se puede cambiar el motor sin tocar la memoria, ni al revés
— exactamente lo que el diseño original quería evitar.

## Mapa de portación

Funciones en `helios_chat.cpp` → responsabilidad del contrato HERA:

| En helios_chat.cpp | Contrato HERA | Notas |
|---|---|---|
| `load_memories()` | §2 HHMS · §7.1 `CK_EVENT_MEMORY_QUERY` | Hoy: recencia + dos niveles. Falta búsqueda semántica |
| `append_fact()` | §3.3 Esencialización → Nivel 1 | Cita atribuida cuando son palabras del dueño |
| `append_candidate()` | §7.1 `CK_EVENT_PROPOSE_CORE_MEMORY` | Los candidatos NO entran al contexto hasta que el usuario confirma |
| `append_memory()` | §2 Nivel 3 (disco) | |
| `memory_is_duplicate()` | §9.2 "rechazado si es redundante" | Contención entre entradas completas |
| `distill_from_transcript()` | §5.2 Consolidación (pasos 3-7) | Debe pasar a esquema estructurado (§6.3), no prosa libre |
| `consolidate()` | §5.1 triggers + §5.2 proceso | Triggers vivos: cierre de sesión y presión de contexto |
| `reflect_and_capture()` | §3.2 Evaluación de relevancia | **Viola §12: corre dentro del turno** |
| `prefill_prefix()` | §4 Identidad persistente | Identidad + memoria como prefijo permanente en KV |
| `ck_policy::classify_turn()` | CK v5 `TurnFrame` | Primer contrato ejecutable; aún en Héctor para iterar |
| `ck_policy::frame_user_message()` | CK v5 `ResponseContract` | Debe consumirlo HERA cuando la política se estabilice |

Ficheros de datos actuales (`~/.helios/`, o `$HELIOS_HOME`):
`facts.md` (nivel 1 provisional), `episodic.md` (nivel 3),
`candidates.md` (propuestas sin confirmar), `owner` (identidad del dueño).

## Deuda conocida frente al contrato

1. **§12 (prohibición absoluta)**: la reflexión y la destilación corren
   BLOQUEANDO el turno. Deben ir en segundo plano.
2. **§6.3 checkpoint estructurado**: hoy la destilación produce prosa libre.
   Con los campos del contrato (`conversation_summary`, `stable_facts[]`,
   `open_tasks[]`, `active_projects[]`, `user_intent_current`) el fallo del
   2026-07-31 —el destilador copió un relato entero al diario y el modelo
   luego lo recitaba— habría sido **imposible por construcción**.
3. **§7.3 cuota diaria** de propuestas esenciales (1-3): no implementada.
4. **§2 Nivel 2** (working memory en RAM): hoy es el KV cache + la
   transcripción de sesión; no hay gestión explícita. La compactación conserva
   solo 300 caracteres de cada mensaje reciente, por lo que un bloque de código
   o documento deja de estar disponible para preguntas posteriores. Los
   artefactos activos necesitan identidad, presupuesto y retención propios.
5. **HNF-EXT**: la memoria esencial vive en `facts.md`, no dentro del
   archivo del modelo. `hnf_ext/` ya está blindado y esperando.
6. **Reparación de hechos**: `append_candidate()` acumula propuestas, pero no
   existe la transición candidato → confirmado → hecho anterior sustituido.
   Una confirmación explícita del usuario debe resolver contradicciones de
   forma auditable; el modelo no puede afirmar que actualizó su memoria cuando
   solo escribió en `candidates.md`.
7. **Estado conversacional del CK**: el `bool trivial` no representa intención,
   continuidad, confianza, registro social y estado de memoria. El diseño y las
   pruebas de aceptación están en `docs/CK_V4_NORTE.md`; HERA debe consumir el
   estado de memoria y continuidad sin inventar un sistema de emociones.

## Cuándo portar

**Cuando la lógica deje de cambiar** — referencia: dos o tres semanas de uso
real sin tocarla. Extraerla antes congela un diseño que aún se está
descubriendo (la lección de enero: 250.000 palabras de especificación,
10.000 líneas de código, cero puentes).

Forma recomendada al portar:
- **HERA librería** enlazada por el chat, para lo que ocurre DENTRO del turno
  (cargar memoria, consolidar al compactar). Cruzar eso por IPC añade
  latencia y modos de fallo a cambio de nada.
- **HERA demonio** solo para el ciclo de sueño (§5.1 "fin del día"): consolidar
  de noche, fusionar recuerdos, promover a HNF-EXT. Eso sí corre sin sesión
  abierta y con la GPU fría — es el caso de uso que justifica un proceso.

El `hera.c` actual se sustituye en el mismo commit en que nazca el real.
No se completa: se reemplaza.
