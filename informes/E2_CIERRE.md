# E2 — Evacuación del CK: barrera de cierre

El CK ya no vive solo dentro de `helios_chat`. HexOS clasifica el turno con su
propio port en C, compone el contrato y manda mensajes tipados a
`helios_runtime`. La ruta legacy sigue siendo la predeterminada y el oráculo.

## Los siete puntos de la barrera

| # | Condición | Estado | Evidencia |
|---|---|---|---|
| 1 | Igualdad diferencial 71/71 | ✅ | `tools/ck_diff.py informes/e2_ref_ck_policy.jsonl <dump C>` → `71 casos · 0 diferencias` |
| 2 | HexOS usa el CK nuevo en la ruta opt-in | ✅ | `--runtime <bin>`; los `ck_frame` de la traza salen del port en C |
| 3 | La traza tipada pasa conformidad | ✅ | `protocolo_test.py informes/e2_traza_ruta_tipada.jsonl` → `367 líneas · 0 violaciones` |
| 4 | La telemetría muestra acto, registro y presupuestos | ✅ | evento SSE `ck_frame` |
| 5 | Cero contratos guardados | ✅ | `~/.helios/*.md` sin tocar; ninguna marca de contrato en la traza que ve el usuario |
| 6 | La legacy sigue funcionando | ✅ | `oraculo.py --diff` contra `e1_base_greedy.json` → **exit 0**, 0 diferencias de política/estructura/memoria |
| 7 | `ck_policy` intacto y congelado | ✅ | banner CONGELADO en el `.hpp`; sha re-armado tras re-probar |

## Dos cosas que hay que decir en voz alta

**El sha del `.hpp` cambió.** Al marcarlo como CONGELADO le añadí un banner de
comentarios, y eso dispara el propio tripwire que dice "si el sha cambia, la
referencia caduca". No lo di por bueno: recompilé `ck_dump` desde ese header y
produjo la referencia **byte a byte idéntica**, y el port en C siguió dando
71/71. Después re-armé el sha en `e2_ref_ck_policy.meta.json` con la nota de por
qué. Un tripwire que salta y se ignora deja de ser un tripwire.

**La primera comparación de la legacy fue inválida y la retiré.** Corrí el
oráculo con `qwen3_4b` contra una base capturada con `qwen3_8b` y salieron 13
diferencias de memoria. No eran una regresión: eran otro modelo destilando otra
cosa. Repetido con el modelo correcto, exit 0 y resúmenes idénticos. Lo dejo
escrito porque el informe de procedencia es lo que lo cazó — sin él me habría
pasado media tarde buscando un bug que no existía.

## Lo que esta ruta NO hace todavía (a propósito)

Identidad, memoria, reflexión y consolidación siguen atrapadas en
`helios_chat`. La ruta tipada es cognitivamente incompleta y se nota: contesta
bien al acto y al presupuesto, pero no sabe quién eres. Traerse aquí los quince
prompts del oráculo sería exactamente la mejora rápida que el plan prohíbe —
eso es E3 (identidad) y E5 (memoria).

`/api/command` se rechaza en la ruta tipada: los comandos son del REPL de
`helios_chat` y aquí no hay REPL. Se rechaza en vez de fingir que se hizo.

## Un hueco del clasificador, para cuando toque

"corrige esto: hexos ejcuta el ck" se clasifica como **conversar**, no como
corregir/reescribir: el clasificador solo engancha "corrige el bug", no
"corrige" a secas. Es fiel al oráculo — la igualdad 71/71 lo cubre — así que
**no se toca en E2**: cambiarlo ahora invalidaría la referencia congelada. Queda
apuntado para cuando el clasificador se pueda mover con red.

## Cómo se levanta

```bash
HEXOS_RT_TRACE=/tmp/traza.jsonl ./hexos/bin/hexos_serve \
  --model <modelo.hnf> --runtime <ruta a helios_runtime> --no-distill
```

Sin `--runtime` manda la legacy. `HEXOS_RT_TRACE` vuelca el tráfico real del
protocolo en el formato que come `protocolo_test.py`, para que la conformidad
se mida sobre lo que pasa de verdad y no sobre fixtures escritos a mano.
