#!/usr/bin/env python3
"""
E1: conformidad del protocolo de `helios_runtime`.

Valida las ocho invariantes de docs/E1_PROTOCOLO_RUNTIME.md sobre una traza
JSONL. Corre sin GPU: primero contra fixtures sintéticas —incluidas varias
rotas a propósito, para demostrar que la prueba sabe fallar— y después contra
trazas reales del ejecutable.

    python3 tools/protocolo_test.py                 # autotest con fixtures
    python3 tools/protocolo_test.py traza.jsonl     # validar una traza real

El invariante 7 es el que sostiene la frontera de E1: si algún día un evento
trae `acto` o `registro`, la mente habrá vuelto a colarse en el transporte y
esta prueba lo dirá.
"""

import json
import sys

TERMINALES = {"completed", "error"}
# Vocabulario cognitivo: nada de esto pertenece al transporte (invariante 7).
PROHIBIDAS = {"acto", "act", "registro", "register", "contrato", "contract",
              "perfil", "profile", "memoria", "memory", "identidad", "identity",
              "candidato", "candidate", "presupuesto"}


def validar(eventos, peticiones=None):
    """Devuelve la lista de violaciones. Vacía = traza conforme."""
    fallos = []
    ids_pedidos = {p.get("request_id") for p in (peticiones or [])
                   if p.get("type") == "turn"}

    # 1) ready exactamente una vez y el primero
    readys = [i for i, e in enumerate(eventos) if e.get("type") == "ready"]
    if len(readys) != 1:
        fallos.append(f"inv1: 'ready' aparece {len(readys)} veces, debe ser 1")
    elif readys[0] != 0:
        fallos.append(f"inv1: 'ready' no es el primer evento (índice {readys[0]})")

    por_id = {}
    for e in eventos:
        if e.get("type") == "ready":
            continue
        rid = e.get("request_id")
        if rid is None:
            fallos.append(f"inv8: evento {e.get('type')} sin request_id")
            continue
        por_id.setdefault(rid, []).append(e)

    for rid, evs in por_id.items():
        tipos = [e["type"] for e in evs]

        # 2) exactamente un terminal
        terminales = [t for t in tipos if t in TERMINALES]
        if len(terminales) != 1:
            fallos.append(f"inv2: {rid} tiene {len(terminales)} eventos "
                          f"terminales ({terminales}), debe ser 1")

        # 3) tokens dentro de su ventana
        if "token" in tipos:
            i_tok = tipos.index("token")
            if "prefill" in tipos and tipos.index("prefill") > i_tok:
                fallos.append(f"inv3: {rid} emite 'token' antes de 'prefill'")
            for t in TERMINALES & set(tipos):
                if tipos.index(t) < len(tipos) - 1 - tipos[::-1].index("token"):
                    fallos.append(f"inv3: {rid} emite 'token' después de '{t}'")

        fin = next((e for e in evs if e["type"] == "completed"), None)
        if fin:
            # 4) el streaming y el texto final tienen que coincidir
            unido = "".join(e.get("text", "") for e in evs if e["type"] == "token")
            if unido != fin.get("visible_text", ""):
                fallos.append(
                    f"inv4: {rid} los tokens concatenados no dan visible_text "
                    f"({len(unido)} vs {len(fin.get('visible_text',''))} chars)")
            # 6) o generó, o explica por qué no
            uso = fin.get("usage", {})
            if uso.get("generated_tokens", 0) <= 0 and not fin.get("finish_reason"):
                fallos.append(f"inv6: {rid} no generó y no da finish_reason")
            for campo in ("finish_reason", "usage", "timings", "model_state"):
                if campo not in fin:
                    fallos.append(f"inv6: {rid} 'completed' sin campo '{campo}'")

        # 8) el id tiene que corresponder a una petición
        if ids_pedidos and rid not in ids_pedidos:
            fallos.append(f"inv8: {rid} no corresponde a ninguna petición")

    # 5) la posición del KV no retrocede sin reset ni aviso
    posiciones, hubo_reset = [], False
    for e in eventos:
        if e.get("type") == "notice":
            hubo_reset = True          # compactación: reinicia posición
        st = e.get("model_state") or {}
        if "cache_position" in st:
            p = st["cache_position"]
            if posiciones and p < posiciones[-1] and not hubo_reset:
                fallos.append(f"inv5: cache_position retrocede "
                              f"{posiciones[-1]} → {p} sin reset ni aviso")
            posiciones.append(p)
            hubo_reset = False
    for p in (peticiones or []):
        if p.get("type") == "reset":
            hubo_reset = True

    # 7) nada de vocabulario cognitivo en el transporte
    def escanear(obj, ruta=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() in PROHIBIDAS:
                    fallos.append(f"inv7: clave cognitiva '{k}' en {ruta or 'raíz'}")
                escanear(v, f"{ruta}.{k}" if ruta else k)
        elif isinstance(obj, list):
            for x in obj:
                escanear(x, ruta)

    for e in eventos:
        escanear(e)

    return fallos


# ---------------------------------------------------------------------------
# Fixtures. Cada invariante tiene una traza que la viola: si la prueba no sabe
# fallar, no sirve de nada.
# ---------------------------------------------------------------------------

def _completo(rid="r1", texto="Hola", tokens=("Ho", "la")):
    return [
        {"type": "prefill", "request_id": rid, "tokens": 5, "ms": 40.0},
        *[{"type": "token", "request_id": rid, "text": t} for t in tokens],
        {"type": "completed", "request_id": rid, "visible_text": texto,
         "finish_reason": "eos",
         "usage": {"prefill_tokens": 5, "generated_tokens": 2, "thinking_tokens": 0},
         "timings": {"prefill_ms": 40.0, "decode_ms": 20.0, "tokens_per_second": 50.0},
         "model_state": {"cache_position": 7, "max_seq_len": 4096}},
    ]


READY = {"type": "ready", "protocol": 1,
         "model": {"architecture": "qwen2", "max_seq_len": 4096,
                   "multimodal": False, "vision_adapter": None}}

FIXTURES = {}
FIXTURES["conforme"] = ([READY] + _completo(), 0)
FIXTURES["conforme_dos_turnos"] = (
    [READY] + _completo("r1") +
    [{"type": "prefill", "request_id": "r2", "tokens": 3, "ms": 10.0},
     {"type": "token", "request_id": "r2", "text": "Vale"},
     {"type": "completed", "request_id": "r2", "visible_text": "Vale",
      "finish_reason": "eos",
      "usage": {"prefill_tokens": 3, "generated_tokens": 1, "thinking_tokens": 0},
      "timings": {"prefill_ms": 10.0, "decode_ms": 5.0, "tokens_per_second": 40.0},
      "model_state": {"cache_position": 12, "max_seq_len": 4096}}], 0)
FIXTURES["turno_mudo_valido"] = (
    [READY,
     {"type": "prefill", "request_id": "r1", "tokens": 5, "ms": 40.0},
     {"type": "thinking", "request_id": "r1", "tokens": 48},
     {"type": "completed", "request_id": "r1", "visible_text": "",
      "finish_reason": "stop",
      "usage": {"prefill_tokens": 5, "generated_tokens": 0, "thinking_tokens": 48},
      "timings": {"prefill_ms": 40.0, "decode_ms": 90.0, "tokens_per_second": 0.0},
      "model_state": {"cache_position": 60, "max_seq_len": 4096}}], 0)

FIXTURES["sin_ready"] = (_completo(), 1)
FIXTURES["dos_terminales"] = (
    [READY] + _completo() +
    [{"type": "error", "request_id": "r1", "code": "x", "message": "y"}], 1)
FIXTURES["token_tras_completed"] = (
    [READY] + _completo() + [{"type": "token", "request_id": "r1", "text": "tarde"}], 1)
FIXTURES["streaming_no_cuadra"] = (
    [READY] + _completo(texto="Hola mundo"), 1)
# Aísla el invariante 5: todo lo demás conforme, solo retrocede el KV. Sin
# aislarlo, la fixture la cazaba el invariante 4 y el 5 no se probaba.
FIXTURES["kv_retrocede"] = (
    [READY] + _completo("r1") +
    [{"type": "prefill", "request_id": "r2", "tokens": 2, "ms": 5.0},
     {"type": "token", "request_id": "r2", "text": "x"},
     {"type": "completed", "request_id": "r2", "visible_text": "x",
      "finish_reason": "eos",
      "usage": {"prefill_tokens": 2, "generated_tokens": 1, "thinking_tokens": 0},
      "timings": {"prefill_ms": 5.0, "decode_ms": 2.0, "tokens_per_second": 50.0},
      "model_state": {"cache_position": 3, "max_seq_len": 4096}}], 1)
FIXTURES["completed_incompleto"] = (
    [READY,
     {"type": "prefill", "request_id": "r1", "tokens": 5, "ms": 40.0},
     {"type": "completed", "request_id": "r1", "visible_text": ""}], 1)
FIXTURES["fuga_cognitiva"] = (
    [READY,
     {"type": "prefill", "request_id": "r1", "tokens": 5, "ms": 40.0},
     {"type": "completed", "request_id": "r1", "visible_text": "",
      "finish_reason": "eos", "acto": "saludar",
      "usage": {"generated_tokens": 0}, "timings": {},
      "model_state": {"cache_position": 5, "max_seq_len": 4096}}], 1)
FIXTURES["evento_sin_id"] = (
    [READY, {"type": "token", "text": "huerfano"}], 1)


def autotest():
    ok = True
    print(f'{"fixture":<26} {"esperado":>9} {"obtenido":>9}  veredicto')
    print("-" * 62)
    for nombre, (eventos, esperado_min) in FIXTURES.items():
        fallos = validar(eventos)
        conforme_esperado = esperado_min == 0
        conforme = len(fallos) == 0
        bien = conforme == conforme_esperado
        ok &= bien
        print(f'{nombre:<26} {"conforme" if conforme_esperado else "  viola":>9} '
              f'{"conforme" if conforme else "  viola":>9}  {"OK" if bien else "MAL"}')
        if not bien:
            for f in fallos:
                print(f"      {f}")
        elif not conforme_esperado and fallos:
            print(f"      → {fallos[0]}")
    print()
    print("autotest del protocolo:", "TODO OK" if ok else "HAY FALLOS")
    return 0 if ok else 1


def main():
    if len(sys.argv) < 2:
        return autotest()
    eventos, peticiones = [], []
    with open(sys.argv[1], encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                obj = json.loads(linea)
            except json.JSONDecodeError as e:
                print(f"línea no es JSON válido: {e}")
                return 1
            (peticiones if obj.get("type") in
             ("turn", "reset", "status", "shutdown", "attachment")
             else eventos).append(obj)
    fallos = validar(eventos, peticiones)
    for f in fallos:
        print("✗", f)
    print(f'\n{len(eventos)} eventos · {len(fallos)} violaciones')
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
