# E5 — Gemma 4 12B «unified»: el texto corre en Héctor

> **Documento histórico / evidencia de una fase.** Sus pendientes y pruebas
> describen ese corte, no el producto actual. [Estado vigente](../IMPLEMENTATION_STATUS.md)
> (revisado 2026-09-19).

`google/gemma-4-12B-it` no es un E4B grande: es otra familia
(`Gemma4UnifiedForConditionalGeneration`). Mezcla 40 capas deslizantes con 8
globales de otra geometría, no tiene Per-Layer Embeddings y sus capas globales
ni siquiera traen `v_proj`. El decoder ya genera lenguaje correcto en la 4070
Ti; la visión se convierte y se valida, pero el motor todavía no la ejecuta.

## Los siete puntos de la barrera

| # | Condición | Estado | Evidencia |
|---|---|---|---|
| 1 | El conversor acepta la familia `gemma4_unified` | ✅ | `helios-convert --text ./models/gemma-4-12B-it` → 666 tensores, 11 saltados (los 9 de `vision_embedder`, `embed_vision`, `embed_audio`) |
| 2 | La geometría por capa sale del checkpoint, no del config | ✅ | GM4X del HNF real: 40 sliding `head_dim=256 KV_HEADS=8 K_EQ_V=no`, 8 full `head_dim=512 KV_HEADS=1 K_EQ_V=sí`, en las capas 5·11·17·23·29·35·41·47 |
| 3 | El registro binario de capa no crece | ✅ | `Gemma4LayerConfigBin` sigue en 40 B: los dos campos nuevos viajan en `flags` y en el antiguo `reserved`, que se escribían a cero |
| 4 | El motor genera lenguaje correcto | ✅ | `test_gemma4_generate … "La capital de Francia es" 24 0.0` → «La capital de Francia es **París**.»; fotosíntesis definida correctamente en 40 tokens |
| 5 | El E4B no se toca | ✅ | tras CADA cambio: 85,3 tok/s y misma salida. `helios_chat` con el E4B responde y captura el CUDA Graph igual que antes |
| 6 | El HNF multimodal valida | ✅ | `validate output/gemma4_12b_mm_hq51k.hnf` → **0 errores, 0 advertencias**. Bloque 0 texto 7,68 GB · bloque 1 visión 95,2 MB |
| 7 | La suite del conversor sigue verde | ✅ | `cargo test --release` → 47 passed, 0 failed |

## Números

| | valor |
|---|---|
| Parámetros | 11,96 B (23,9 GB bf16) |
| HNF sólo texto | 7868,7 MB · HQ5.1K + `--shared-embedding-hq51` |
| HNF con visión | 7963,9 MB · 676 tensores |
| VRAM en ejecución | 9114 MB de 11874 |
| Decode | **42,6 tok/s** (E4B: 85,3 tok/s) |
| Prefill | 178 ms |

## Tres cosas que hay que decir en voz alta

**Estuve adivinando cuando la referencia estaba a un `curl`.** Deduje la
semántica de `attention_k_eq_v` a partir de la ausencia del tensor y me lancé a
implementar. El modelo cargaba, ejecutaba… y emitía `<pad>` indefinidamente.
Descarté la vista del scratch, dudé del kernel de atención y perdí un buen rato.
Cuando por fin bajé `modeling_gemma4_unified.py` (65 KB), confirmó en un minuto
que mi lectura de `k_eq_v` **era correcta desde el principio** y señaló el fallo
real en diez. La regla para la próxima: leer el `modeling` ANTES de la primera
línea de código.

**El fallo real era el `layer_scalar`, y estaba escondido en el PLE.** La
referencia cierra cada capa con `hidden_states *= self.layer_scalar`. En Héctor
ese producto vivía DENTRO de la inyección de PLE; como el 12B no tiene PLE,
salté el bloque entero y me llevé por delante la escala de las 48 capas. No hay
error, no hay aviso: sólo logits degenerados. Ahora el `layer_scalar` es
independiente del PLE.

**Rompí el motor durante tres minutos.** Registré un kernel para un op cuyo tipo
no había declarado en `optype.cpp`, y eso tumbó el arranque de *todos* los
modelos, no sólo del 12B (`Cannot register kernel for invalid op`). Lo cazó la
comprobación de regresión del E4B, que es justo para lo que se hace. Si llego a
encadenar dos cambios más sin ejecutarla, el fallo aparece lejos de su causa.

## Dónde queda

### Visión — la mitad hecha

✅ Mapper propio (10 tensores, sin torre), bloque 0x1 escrito y validado,
contrato de hints `encoder_free`, y el kernel de posiciones factorizadas
(`g4u_pos_add`) compilando y registrado.

❌ Falta el **config binario** (el `GM4V` actual pide campos de torre que aquí no
existen y le faltan `mm_posemb_size`, `num_soft_tokens`, `model_patch_size`), el
**preprocesado** (parches de 48×48×3 = 6912, `do_normalize: false` → sólo rescale
1/255, y coordenadas `(x,y)` con `-1` de relleno) y el **grafo** que encadene
`LN₁ → Dense+bias → LN₂ → +pos → LN₃ → RMSNorm sin escala → Linear` y meta los
280 soft tokens en el decoder.

Nota útil: el resto **no necesita kernels nuevos**. `op::LAYERNORM()` ya acepta
bias en `ctx.in(2)`, y `MATMUL`, `ADD_BIAS` y la RMSNorm sin escala ya existen.

### Audio

❌ `embed_audio.embedding_projection.weight` `[3840, 640]` sin mapear. Es UN
tensor: el bloque 0x2 sería trivial.

### Dos fallos preexistentes, ajenos a esta etapa

- `test_smoke` fase 4 falla en **cualquier** modelo: `test_smoke.cpp:608` hace un
  `cudaMemcpy` sin comprobar el retorno tras `free_scratch()` +
  `allocate_scratch()`. El error queda pendiente y CUDA lo reporta en la
  siguiente llamada que sí lo mira — el `embedding` —, lo que hace parecer que
  falla el kernel de embeddings. Verificado con `git stash`: ya fallaba antes.
- `audits_local_gemma4_inventory_when_available` falla con `719 != 600`: está
  escrito para un E4B de 35 capas y el checkpoint local tiene 42.

## Commits

| Repo | Commit |
|---|---|
| `helios_convert_v9.1` | `e40a8c1` — el conversor entiende la familia «unified» |
| `Hector-engine` | `58f8a3f` — el motor ejecuta el decoder «unified» |

Ninguno subido: esta máquina no tiene credenciales de GitHub.
