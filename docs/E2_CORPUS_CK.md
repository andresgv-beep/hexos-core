# E2 — Corpus de comparación de CK

**Fase:** E2 del [plan de evacuación](PLAN_EVACUACION_COGNITIVA.md)
**Barrera:** el mismo corpus entra en el `ck_policy` de Héctor y en el CK de
HexOS, y ambos deben producir **`TurnFrame` idéntico campo por campo** y
**`ResponseContract` idéntico byte por byte**.

## Por qué un test diferencial y no una conversación

Conversar compara *resultados* del modelo, que dependen del muestreo, del
contexto y del hardware. Aquí lo que se porta es una **función determinista**:
mensaje + estado → acto, presupuestos y contrato. Se compara la función, no
sus consecuencias.

Dos volcadores —uno por implementación— leen el mismo corpus y emiten una
línea JSON por caso. Un comparador exige igualdad exacta. Cualquier diferencia
de orden o serialización es un fallo hasta que alguien la explique.

## Formato

Entrada (`corpus.jsonl`), una línea por caso:

```jsonc
{"id":"saludo_simple","message":"hola","trivial":true,
 "artifact_active":false,"has_attachment":false,"registro":"neutral",
 "recall_query":"","confirmed_facts":""}
```

Salida de cada volcador, una línea por caso:

```jsonc
{"id":"saludo_simple","act":"saludar","artifact_active":false,
 "has_attachment":false,"trivial":true,
 "visible_budget":60,"thinking_budget":0,
 "contract_needed":false,
 "contract":"…","social_steer":"…","framed_user":"…","recall_context":""}
```

`contract`, `social_steer`, `framed_user` y `recall_context` se comparan como
cadenas exactas: son el texto que verá el modelo, y un espacio de más cambia
la tokenización.

## Cobertura exigida

El corpus debe activar **todos** los actos del enum y los bordes que decidieron
su implementación, no solo los caminos felices:

| Grupo | Qué prueba |
|---|---|
| Sociales | saludar, reconocer, interesarse, conversar — y que **no** llevan contrato |
| Continuación | `sigue` con y sin artefacto activo (`continuar_artefacto` vs `colaborar`) |
| Corrección | prefijos de `corregirse`, incluido `me refiero a` |
| Recall | consultas de memoria y la normalización de relaciones |
| Tarea | resumir, extraer, reescribir, criticar, implementar, analizar, explicar, contar, crear |
| Aclaración | `ayúdame con`, y `cómo seguimos` con y sin artefacto |
| Fallback | pregunta con `?`, interrogativos iniciales, y el caso por defecto |
| Bordes | mensaje vacío, solo espacios, 700+ caracteres (el corte de `normalized`), acentos y mayúsculas, adjunto sin texto |
| Registro | cada acto con `trabajo`, `neutral` y `colega` |

Los **defectos conocidos entran en el corpus a propósito**: si el clasificador
etiqueta mal un caso, ambas implementaciones deben etiquetarlo mal igual. E2
mueve la política; no la cura.

## Criterio

- Igualdad exacta en todos los campos y todos los casos.
- Una diferencia sin explicación bloquea el cutover.
- `ck_policy` permanece en Héctor hasta superar la matriz completa.
