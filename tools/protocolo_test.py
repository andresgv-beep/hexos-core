#!/usr/bin/env python3
"""
E1: conformidad del protocolo de `helios_runtime` (v2).

Valida los diez invariantes de docs/E1_PROTOCOLO_RUNTIME.md sobre una traza
ORDENADA y CON DIRECCIÓN:

    {"direction":"request","payload":{"type":"turn","request_id":"r1", …}}
    {"direction":"event","payload":{"type":"prefill","request_id":"r1", …}}

La dirección y el orden no son adorno: sin ellos no se puede comprobar
causalidad — que una bajada del KV ocurrió *después* de su reset, que un
evento no llegó antes que su petición, que el terminal fue lo último.

    python3 tools/protocolo_test.py                 # autotest con fixtures
    python3 tools/protocolo_test.py traza.jsonl     # validar una traza real

Cada invariante tiene al menos una fixture que lo viola, aislada para que la
cace ese invariante y no otro. Una prueba que solo pasa con datos buenos no
demuestra nada.
"""

import json
import sys

# Terminal que corresponde a cada petición (§2 del protocolo).
TERMINAL_DE = {
    "turn": {"completed", "error"},
    "reset": {"result", "error"},
    "status": {"result", "error"},
    "attachment": {"result", "error"},
    "cancel": {"result", "error"},
    "shutdown": {"result", "error"},
}
TERMINALES = {"completed", "error", "result"}

# Esquema mínimo: tipo -> campos obligatorios. Un tipo desconocido es un fallo,
# no algo que ignorar en silencio.
ESQUEMA_EVENTOS = {
    "ready":             {"protocol", "model"},
    "prefill":           {"request_id", "tokens", "ms"},
    "thinking":          {"request_id", "tokens"},
    "text_delta":        {"request_id", "text"},
    "notice":            {"request_id", "text"},
    "context_compacted": {"request_id", "cache_position_before",
                          "cache_position_after"},
    "completed":         {"request_id", "visible_text", "finish_reason",
                          "usage", "timings", "model_state"},
    "result":            {"request_id", "ok"},
    "error":             {"request_id", "code", "message"},
}
ESQUEMA_PETICIONES = {
    "turn":       {"request_id", "messages"},
    "attachment": {"request_id", "kind", "bytes"},
    "cancel":     {"request_id", "target"},
    "reset":      {"request_id"},
    "status":     {"request_id"},
    "shutdown":   {"request_id"},
}
FINISH_REASONS = {"eos", "max_tokens", "stop", "cancelled"}

# Vocabulario cognitivo prohibido EN LAS CLAVES del esquema (invariante 10).
# Nunca en los valores: el modelo puede hablar de memoria o perfiles y eso es
# contenido legítimo, no una fuga del transporte.
CLAVES_PROHIBIDAS = {"acto", "act", "registro", "register", "contrato",
                     "contract", "perfil", "profile", "memoria", "memory",
                     "identidad", "identity", "candidato", "candidate",
                     "presupuesto"}
# `text` y `visible_text` llevan salida opaca del modelo: no se inspeccionan.
CLAVES_OPACAS = {"text", "visible_text", "message", "content"}


def validar(traza):
    """`traza` = lista ordenada de {"direction","payload"}. Devuelve fallos."""
    fallos = []
    peticiones = {}          # request_id -> tipo
    eventos_por_id = {}      # request_id -> [tipos, en orden]
    terminado = {}           # request_id -> tipo terminal
    ready_vistos = 0
    ultima_pos = None
    autoriza_bajada = None   # request_id que acaba de justificar un retroceso

    for i, linea in enumerate(traza):
        direccion = linea.get("direction")
        p = linea.get("payload")
        if direccion not in ("request", "event") or not isinstance(p, dict):
            fallos.append(f"[{i}] línea sin direction válida o sin payload")
            continue
        tipo = p.get("type")

        # ---------------- peticiones ----------------
        if direccion == "request":
            if tipo not in ESQUEMA_PETICIONES:
                fallos.append(f"inv8: [{i}] tipo de petición desconocido: {tipo!r}")
                continue
            faltan = ESQUEMA_PETICIONES[tipo] - set(p)
            if faltan:
                fallos.append(f"inv8: [{i}] petición {tipo} sin {sorted(faltan)}")
            rid = p.get("request_id")
            if rid in peticiones:
                fallos.append(f"inv7: [{i}] request_id duplicado: {rid!r}")
            peticiones[rid] = tipo
            if tipo == "reset":
                autoriza_bajada = rid
            continue

        # ---------------- eventos ----------------
        if tipo not in ESQUEMA_EVENTOS:
            fallos.append(f"inv8: [{i}] tipo de evento desconocido: {tipo!r}")
            continue
        faltan = ESQUEMA_EVENTOS[tipo] - set(p)
        if faltan:
            fallos.append(f"inv8: [{i}] evento {tipo} sin {sorted(faltan)}")

        if tipo == "ready":
            ready_vistos += 1
            if i != 0:
                fallos.append(f"inv1: 'ready' no es el primer evento (línea {i})")
            continue

        rid = p.get("request_id")
        if rid not in peticiones:
            fallos.append(f"inv7: [{i}] evento {tipo} con request_id {rid!r} "
                          f"sin petición previa")
        if rid in terminado:
            fallos.append(f"inv3: [{i}] evento {tipo} después del terminal "
                          f"'{terminado[rid]}' de {rid}")
        eventos_por_id.setdefault(rid, []).append(tipo)

        if tipo in TERMINALES:
            esperados = TERMINAL_DE.get(peticiones.get(rid), TERMINALES)
            if tipo not in esperados:
                fallos.append(f"inv2: [{i}] {rid} es una petición "
                              f"'{peticiones.get(rid)}' y su terminal fue "
                              f"'{tipo}' (esperado {sorted(esperados)})")
            terminado[rid] = tipo

        if tipo == "text_delta" and "prefill" not in eventos_por_id.get(rid, []):
            fallos.append(f"inv4: [{i}] {rid} emite text_delta sin 'prefill' previo")

        if tipo == "completed":
            unido = "".join(
                l["payload"]["text"] for l in traza[:i]
                if l.get("direction") == "event"
                and l["payload"].get("type") == "text_delta"
                and l["payload"].get("request_id") == rid)
            if unido != p.get("visible_text", ""):
                fallos.append(f"inv5: {rid} los text_delta concatenados no dan "
                              f"visible_text ({len(unido)} vs "
                              f"{len(p.get('visible_text',''))} chars)")
            if p.get("finish_reason") not in FINISH_REASONS:
                fallos.append(f"inv9: {rid} finish_reason inválido: "
                              f"{p.get('finish_reason')!r}")
            st = p.get("model_state") or {}
            if not {"cache_position_before", "cache_position"} <= set(st):
                fallos.append(f"inv9: {rid} model_state sin ambas posiciones")

        # ---- invariante 6: el KV solo baja con permiso ----
        if tipo == "context_compacted":
            autoriza_bajada = rid
        st = p.get("model_state") or {}
        if "cache_position" in st:
            pos = st["cache_position"]
            if ultima_pos is not None and pos < ultima_pos:
                permitido = (autoriza_bajada is not None and
                             (autoriza_bajada == rid or
                              peticiones.get(autoriza_bajada) == "reset"))
                if not permitido:
                    fallos.append(f"inv6: cache_position retrocede "
                                  f"{ultima_pos} → {pos} en {rid} sin reset "
                                  f"confirmado ni context_compacted")
            ultima_pos = pos
            autoriza_bajada = None

        # ---- invariante 10: claves cognitivas en el esquema ----
        def escanear(obj, ruta=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k.lower() in CLAVES_PROHIBIDAS:
                        fallos.append(f"inv10: clave cognitiva '{k}' en "
                                      f"{ruta or tipo}")
                    if k not in CLAVES_OPACAS:
                        escanear(v, f"{ruta}.{k}" if ruta else k)
            elif isinstance(obj, list):
                for x in obj:
                    escanear(x, ruta)
        escanear(p)

    if ready_vistos != 1:
        fallos.append(f"inv1: 'ready' aparece {ready_vistos} veces, debe ser 1")

    for rid, tipo in peticiones.items():
        if rid not in terminado:
            fallos.append(f"inv2: la petición {tipo} {rid!r} no recibió terminal")

    return fallos


# ---------------------------------------------------------------------------
# Fixtures: cada invariante con su violación aislada.
# ---------------------------------------------------------------------------

def req(**kw):
    return {"direction": "request", "payload": kw}


def ev(**kw):
    return {"direction": "event", "payload": kw}


READY = ev(type="ready", protocol=2,
           model={"architecture": "qwen2", "max_seq_len": 4096,
                  "multimodal": False, "vision_adapter": None})


def turno(rid="r1", texto="Hola", trozos=("Ho", "la"), antes=0, despues=7,
          razon="eos"):
    return ([req(type="turn", request_id=rid,
                 messages=[{"role": "user", "content": "hola"}]),
             ev(type="prefill", request_id=rid, tokens=5, ms=40.0)]
            + [ev(type="text_delta", request_id=rid, text=t) for t in trozos]
            + [ev(type="completed", request_id=rid, visible_text=texto,
                  finish_reason=razon,
                  usage={"prefill_tokens": 5, "generated_tokens": len(trozos),
                         "thinking_tokens": 0},
                  timings={"prefill_ms": 40.0, "decode_ms": 20.0,
                           "tokens_per_second": 50.0},
                  model_state={"cache_position_before": antes,
                               "cache_position": despues,
                               "max_seq_len": 4096})])


F = {}
F["conforme"] = ([READY] + turno(), True)
F["conforme_dos_turnos"] = ([READY] + turno("r1", antes=0, despues=7)
                            + turno("r2", "Vale", ("Va", "le"), 7, 12), True)
F["conforme_reset_baja_kv"] = (
    [READY] + turno("r1", antes=0, despues=7)
    + [req(type="reset", request_id="x1"),
       ev(type="result", request_id="x1", ok=True,
          model_state={"cache_position_before": 7, "cache_position": 0,
                       "max_seq_len": 4096})], True)
F["conforme_compactacion"] = (
    [READY] + [req(type="turn", request_id="r1",
                   messages=[{"role": "user", "content": "x"}]),
               ev(type="prefill", request_id="r1", tokens=5, ms=1.0),
               ev(type="context_compacted", request_id="r1",
                  cache_position_before=3900, cache_position_after=1200),
               ev(type="text_delta", request_id="r1", text="ok"),
               ev(type="completed", request_id="r1", visible_text="ok",
                  finish_reason="eos",
                  usage={"prefill_tokens": 5, "generated_tokens": 1,
                         "thinking_tokens": 0},
                  timings={"prefill_ms": 1.0, "decode_ms": 1.0,
                           "tokens_per_second": 1.0},
                  model_state={"cache_position_before": 3900,
                               "cache_position": 1205, "max_seq_len": 4096})],
    True)
F["conforme_cancelacion"] = (
    [READY,
     req(type="turn", request_id="r1", messages=[{"role": "user", "content": "x"}]),
     ev(type="prefill", request_id="r1", tokens=5, ms=1.0),
     ev(type="text_delta", request_id="r1", text="Empeza"),
     req(type="cancel", request_id="c1", target="r1"),
     ev(type="result", request_id="c1", ok=True),
     ev(type="completed", request_id="r1", visible_text="Empeza",
        finish_reason="cancelled",
        usage={"prefill_tokens": 5, "generated_tokens": 3, "thinking_tokens": 0},
        timings={"prefill_ms": 1.0, "decode_ms": 5.0, "tokens_per_second": 1.0},
        model_state={"cache_position_before": 0, "cache_position": 8,
                     "max_seq_len": 4096})], True)
F["conforme_adjunto_y_turno"] = (
    [READY,
     req(type="attachment", request_id="a1", kind="rgb8", bytes=110592),
     ev(type="result", request_id="a1", ok=True)]
    + [req(type="turn", request_id="r1",
           messages=[{"role": "user", "content": "¿qué ves?"}],
           attachment_ids=["a1"]),
       ev(type="prefill", request_id="r1", tokens=300, ms=200.0),
       ev(type="text_delta", request_id="r1", text="Un círculo"),
       ev(type="completed", request_id="r1", visible_text="Un círculo",
          finish_reason="eos",
          usage={"prefill_tokens": 300, "generated_tokens": 3,
                 "thinking_tokens": 0},
          timings={"prefill_ms": 200.0, "decode_ms": 10.0,
                   "tokens_per_second": 30.0},
          model_state={"cache_position_before": 0, "cache_position": 303,
                       "max_seq_len": 4096})], True)

F["inv1_sin_ready"] = (turno(), False)
F["inv1_ready_doble"] = ([READY, READY] + turno(), False)
F["inv2_sin_terminal"] = (
    [READY, req(type="turn", request_id="r1",
                messages=[{"role": "user", "content": "x"}]),
     ev(type="prefill", request_id="r1", tokens=5, ms=1.0)], False)
F["inv2_terminal_equivocado"] = (
    [READY, req(type="reset", request_id="x1"),
     ev(type="completed", request_id="x1", visible_text="", finish_reason="eos",
        usage={}, timings={},
        model_state={"cache_position_before": 0, "cache_position": 0})], False)
F["inv3_notice_tras_terminal"] = (
    [READY] + turno() + [ev(type="notice", request_id="r1", text="tarde")], False)
F["inv4_delta_sin_prefill"] = (
    [READY, req(type="turn", request_id="r1",
                messages=[{"role": "user", "content": "x"}]),
     ev(type="text_delta", request_id="r1", text="Hola"),
     ev(type="completed", request_id="r1", visible_text="Hola",
        finish_reason="eos",
        usage={"prefill_tokens": 0, "generated_tokens": 1, "thinking_tokens": 0},
        timings={}, model_state={"cache_position_before": 0,
                                 "cache_position": 4})], False)
F["inv5_streaming_no_cuadra"] = ([READY] + turno(texto="Hola mundo"), False)
F["inv6_kv_retrocede_sin_permiso"] = (
    [READY] + turno("r1", antes=0, despues=7)
    + turno("r2", "Vale", ("Va", "le"), antes=7, despues=3), False)
F["inv7_id_duplicado"] = ([READY] + turno("r1") + turno("r1", "Otra", ("Ot", "ra")),
                          False)
F["inv7_evento_sin_peticion"] = (
    [READY, ev(type="text_delta", request_id="zz", text="huérfano")], False)
F["inv8_tipo_desconocido"] = (
    [READY] + turno() + [ev(type="telepatia", request_id="r1")], False)
F["inv8_campos_faltantes"] = (
    [READY, req(type="turn", request_id="r1",
                messages=[{"role": "user", "content": "x"}]),
     ev(type="prefill", request_id="r1")], False)
F["inv9_finish_reason_invalido"] = ([READY] + turno(razon="porque_si"), False)
F["inv10_clave_cognitiva"] = (
    [READY, req(type="turn", request_id="r1",
                messages=[{"role": "user", "content": "x"}]),
     ev(type="prefill", request_id="r1", tokens=1, ms=1.0),
     ev(type="completed", request_id="r1", visible_text="", finish_reason="eos",
        acto="saludar", usage={}, timings={},
        model_state={"cache_position_before": 0, "cache_position": 1})], False)
# El modelo hablando de memoria NO es una fuga: solo se inspeccionan claves.
F["conforme_texto_menciona_memoria"] = (
    [READY] + turno(texto="Tu memoria y tu perfil están vacíos",
                    trozos=("Tu memoria y tu ", "perfil están vacíos")), True)


def autotest():
    ok = True
    print(f'{"fixture":<34} {"esperado":>9} {"obtenido":>9}  veredicto')
    print("-" * 70)
    for nombre, (traza, conforme_esperado) in F.items():
        fallos = validar(traza)
        conforme = not fallos
        bien = conforme == conforme_esperado
        ok &= bien
        print(f'{nombre:<34} {"conforme" if conforme_esperado else "  viola":>9} '
              f'{"conforme" if conforme else "  viola":>9}  {"OK" if bien else "MAL"}')
        if not bien:
            for f_ in fallos[:3]:
                print(f"      {f_}")
        elif not conforme_esperado:
            # Que la cace el invariante que le toca, no otro por accidente.
            esperado = nombre.split("_")[0]
            if not any(f_.startswith(esperado + ":") for f_ in fallos):
                print(f"      OJO: la caza '{fallos[0].split(':')[0]}', "
                      f"no '{esperado}' — fixture mal aislada")
                ok = False
            else:
                print(f"      → {next(f for f in fallos if f.startswith(esperado))}")
    print()
    print("autotest del protocolo:", "TODO OK" if ok else "HAY FALLOS")
    return 0 if ok else 1


def main():
    if len(sys.argv) < 2:
        return autotest()
    traza = []
    with open(sys.argv[1], encoding="utf-8") as f:
        for n, linea in enumerate(f, 1):
            linea = linea.strip()
            if not linea:
                continue
            try:
                traza.append(json.loads(linea))
            except json.JSONDecodeError as e:
                print(f"línea {n} no es JSON válido: {e}")
                return 1
    fallos = validar(traza)
    for f_ in fallos:
        print("✗", f_)
    print(f"\n{len(traza)} líneas · {len(fallos)} violaciones")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
