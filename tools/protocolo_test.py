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

# Esquema: tipo -> (campos obligatorios, campos opcionales). Se valida por
# LISTA BLANCA: un campo superior desconocido es un fallo, no algo que ignorar.
# Así la frontera cognitiva no depende de acertar la lista de palabras
# prohibidas — cualquier campo que nadie declaró queda fuera.
ESQUEMA_EVENTOS = {
    "ready":             ({"protocol", "model"}, set()),
    "prefill":           ({"request_id", "tokens", "ms"}, set()),
    "thinking":          ({"request_id", "tokens"}, set()),
    "text_delta":        ({"request_id", "text"}, set()),
    "notice":            ({"request_id", "text"}, set()),
    "context_compacted": ({"request_id", "cache_position_before",
                           "cache_position_after"}, set()),
    "completed":         ({"request_id", "visible_text", "finish_reason",
                           "usage", "timings", "model_state"}, set()),
    "result":            ({"request_id", "ok", "model_state"}, {"detail"}),
    # `error` de un turno debe traer además el texto parcial y sus contadores:
    # si el modelo llegó a emitir, el cliente ya lo pintó y el resultado final
    # tiene que ser coherente con el streaming.
    "error":             ({"request_id", "code", "message", "model_state"},
                          {"visible_text", "usage", "timings"}),
    # Sesiones. Héctor ofrece sesiones GENÉRICAS sobre unos mismos pesos: no
    # sabe que unas son chats. `session_paused` dice qué sesión dejó de generar
    # y por qué — hoy solo por conmutación, y el motivo va declarado para que
    # mañana no se cuele otro sin que nadie lo apruebe.
    "session_opened":    ({"session"}, set()),
    "session_closed":    ({"session"}, set()),
    "session_paused":    ({"session", "reason"}, set()),
}
PAUSE_REASONS = {"switch"}
ESQUEMA_PETICIONES = {
    # `session` es OPCIONAL: sin él va a la sesión por defecto, así que el
    # protocolo anterior sigue valiendo palabra por palabra.
    "turn":       ({"request_id", "messages"},
                   {"attachment_ids", "generation", "session"}),
    "session_open":  ({"request_id", "session"}, set()),
    "session_close": ({"request_id", "session"}, set()),
    "attachment": ({"request_id", "kind", "width", "height", "stride", "bytes"},
                   set()),
    "cancel":     ({"request_id", "target"}, set()),
    "reset":      ({"request_id"}, {"session"}),
    "status":     ({"request_id"}, set()),
    "shutdown":   ({"request_id"}, set()),
}
FINISH_REASONS = {"eos", "max_tokens", "stop", "cancelled"}
# Mismo tope que el /adjunto-rgb8 de helios_chat: la cabecera no puede pedir
# que se reserve una cantidad arbitraria de memoria.
MAX_ADJUNTO = 300 * 1024 * 1024

# Vocabulario cognitivo prohibido EN LAS CLAVES del esquema (invariante 10).
# Nunca en los valores: el modelo puede hablar de memoria o perfiles y eso es
# contenido legítimo, no una fuga del transporte.
CLAVES_PROHIBIDAS = {"acto", "act", "registro", "register", "contrato",
                     "contract", "perfil", "profile", "memoria", "memory",
                     "identidad", "identity", "candidato", "candidate",
                     "presupuesto"}
# `text` y `visible_text` llevan salida opaca del modelo: no se inspeccionan.
CLAVES_OPACAS = {"text", "visible_text", "message", "content"}


def validar_adjunto(i, p):
    """`kind: rgb8` obliga a una geometría coherente: sin esto la cabecera
    puede pedir que se reserve cualquier cosa o describir una imagen
    imposible."""
    if p.get("kind") != "rgb8":
        return [f"inv8: [{i}] adjunto de tipo desconocido: {p.get('kind')!r}"]
    fallos, g = [], {}
    for campo in ("width", "height", "stride", "bytes"):
        v = p.get(campo)
        if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
            fallos.append(f"inv8: [{i}] adjunto con {campo} inválido: {v!r}")
        else:
            g[campo] = v
    if len(g) == 4:
        if g["stride"] < g["width"] * 3:
            fallos.append(f"inv8: [{i}] stride {g['stride']} < width*3 "
                          f"({g['width'] * 3})")
        if g["bytes"] != g["stride"] * g["height"]:
            fallos.append(f"inv8: [{i}] bytes {g['bytes']} != stride*height "
                          f"({g['stride'] * g['height']})")
        if g["bytes"] > MAX_ADJUNTO:
            fallos.append(f"inv8: [{i}] adjunto de {g['bytes']} bytes supera "
                          f"el tope de {MAX_ADJUNTO}")
    return fallos


def escanear_cognitivo(payload, tipo, fallos):
    """Invariante 10, sobre CLAVES del esquema en peticiones y eventos.

    Antes solo miraba eventos, así que un `turn` con `"memory": {...}` pasaba
    limpio: la mente podía entrar por la puerta del cliente. El texto opaco
    (contenido de mensajes y salida del modelo) queda excluido: que Héctor
    hable de memoria o de perfiles es contenido legítimo, no una fuga.
    """
    def rec(obj, ruta=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() in CLAVES_PROHIBIDAS:
                    fallos.append(f"inv10: clave cognitiva '{k}' en "
                                  f"{ruta or tipo}")
                if k not in CLAVES_OPACAS:
                    rec(v, f"{ruta}.{k}" if ruta else k)
        elif isinstance(obj, list):
            for x in obj:
                rec(x, ruta)
    rec(payload)


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
            obligatorios, opcionales = ESQUEMA_PETICIONES[tipo]
            faltan = obligatorios - set(p)
            if faltan:
                fallos.append(f"inv8: [{i}] petición {tipo} sin {sorted(faltan)}")
            sobran = set(p) - obligatorios - opcionales - {"type"}
            if sobran:
                fallos.append(f"inv10: [{i}] petición {tipo} con campos no "
                              f"declarados: {sorted(sobran)}")
            if tipo == "attachment":
                fallos += validar_adjunto(i, p)
            rid = p.get("request_id")
            if rid in peticiones:
                fallos.append(f"inv7: [{i}] request_id duplicado: {rid!r}")
            peticiones[rid] = tipo
            # OJO: el permiso para que baje el KV NO se concede aquí. Un reset
            # que termina en error autorizaría retrocesos para siempre. Se
            # concede al procesar su terminal exitoso.
            escanear_cognitivo(p, tipo, fallos)
            continue

        # ---------------- eventos ----------------
        if tipo == "session_paused" and d.get("reason") not in PAUSE_REASONS:
            fallos.append(f"inv8: [{i}] motivo de pausa no declarado: "
                          f"{d.get('reason')!r}")
        if tipo not in ESQUEMA_EVENTOS:
            fallos.append(f"inv8: [{i}] tipo de evento desconocido: {tipo!r}")
            continue
        obligatorios, opcionales = ESQUEMA_EVENTOS[tipo]
        faltan = obligatorios - set(p)
        if faltan:
            fallos.append(f"inv8: [{i}] evento {tipo} sin {sorted(faltan)}")
        sobran = set(p) - obligatorios - opcionales - {"type"}
        if sobran:
            fallos.append(f"inv10: [{i}] evento {tipo} con campos no "
                          f"declarados: {sorted(sobran)}")

        if tipo == "ready":
            ready_vistos += 1
            if i != 0:
                fallos.append(f"inv1: 'ready' no es el primer evento (línea {i})")
            continue

        # Eventos de CICLO DE VIDA de una sesión: no responden a una petición
        # concreta y por eso no llevan `request_id`, igual que `ready`. Su
        # esquema ya se validó arriba, así que aquí solo hay que no confundir
        # "no tiene id" con "tiene un id inventado".
        if tipo in ("session_opened", "session_closed", "session_paused"):
            if "request_id" in p:
                fallos.append(f"inv7: [{i}] {tipo} no debe traer request_id")
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
            # El permiso para bajar el KV nace AQUÍ y solo si el reset salió
            # bien; un error lo revoca en vez de dejarlo colgando.
            if peticiones.get(rid) == "reset":
                autoriza_bajada = rid if (tipo == "result" and
                                          p.get("ok") is True) else None
            elif tipo == "error":
                autoriza_bajada = None

        if tipo == "text_delta" and "prefill" not in eventos_por_id.get(rid, []):
            fallos.append(f"inv4: [{i}] {rid} emite text_delta sin 'prefill' previo")

        # Coherencia streaming/resultado: vale para `completed` y también para
        # un `error` de turno que ya había emitido texto.
        es_error_de_turno = (tipo == "error" and peticiones.get(rid) == "turn")
        if tipo == "completed" or es_error_de_turno:
            unido = "".join(
                l["payload"]["text"] for l in traza[:i]
                if l.get("direction") == "event"
                and l["payload"].get("type") == "text_delta"
                and l["payload"].get("request_id") == rid)
            if es_error_de_turno and unido and "visible_text" not in p:
                fallos.append(f"inv5: {rid} el error llega tras emitir "
                              f"{len(unido)} chars y no trae visible_text")
            elif "visible_text" in p and unido != p.get("visible_text", ""):
                fallos.append(f"inv5: {rid} los text_delta concatenados no dan "
                              f"visible_text ({len(unido)} vs "
                              f"{len(p.get('visible_text',''))} chars)")
            if es_error_de_turno and unido:
                for campo in ("usage", "timings"):
                    if campo not in p:
                        fallos.append(f"inv9: {rid} error con texto parcial "
                                      f"sin '{campo}'")
        if tipo == "completed":
            if p.get("finish_reason") not in FINISH_REASONS:
                fallos.append(f"inv9: {rid} finish_reason inválido: "
                              f"{p.get('finish_reason')!r}")

        # `model_state` con AMBAS posiciones en los tres terminales: es lo que
        # permite auditar el efecto de cada petición sin inferirlo.
        if tipo in TERMINALES:
            st = p.get("model_state") or {}
            if not {"cache_position_before", "cache_position"} <= set(st):
                fallos.append(f"inv9: {rid} '{tipo}' sin ambas posiciones en "
                              f"model_state")

        # ---- invariante 6: el KV solo baja con permiso ----
        if tipo == "context_compacted":
            antes_c, despues_c = (p.get("cache_position_before"),
                                  p.get("cache_position_after"))
            if not (isinstance(antes_c, int) and isinstance(despues_c, int)
                    and despues_c < antes_c):
                fallos.append(f"inv6: {rid} context_compacted no reduce el "
                              f"contexto ({antes_c} → {despues_c})")
            autoriza_bajada = rid
            # La posición observada pasa a ser la de después: si no, la bajada
            # real se detectaría más tarde y fuera de su permiso.
            if isinstance(despues_c, int):
                ultima_pos = despues_c
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

        escanear_cognitivo(p, tipo, fallos)

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
    [READY] + turno("r0", "previo", ("pre", "vio"), antes=0, despues=3900)
    + [req(type="turn", request_id="r1",
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
     ev(type="result", request_id="c1", ok=True,
        model_state={"cache_position_before": 0, "cache_position": 6,
                     "max_seq_len": 4096}),
     ev(type="completed", request_id="r1", visible_text="Empeza",
        finish_reason="cancelled",
        usage={"prefill_tokens": 5, "generated_tokens": 3, "thinking_tokens": 0},
        timings={"prefill_ms": 1.0, "decode_ms": 5.0, "tokens_per_second": 1.0},
        model_state={"cache_position_before": 0, "cache_position": 8,
                     "max_seq_len": 4096})], True)
F["conforme_adjunto_y_turno"] = (
    [READY,
     req(type="attachment", request_id="a1", kind="rgb8",
         width=192, height=192, stride=576, bytes=110592),
     ev(type="result", request_id="a1", ok=True,
        model_state={"cache_position_before": 0, "cache_position": 0,
                     "max_seq_len": 4096})]
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

# --- las cuatro trazas que GPT construyo y pasaban como conformes ---
F["inv6_reset_fallido_autoriza"] = (
    [READY] + turno("r1", antes=0, despues=7)
    + [req(type="reset", request_id="x1"),
       ev(type="error", request_id="x1", code="busy", message="ocupado",
          model_state={"cache_position_before": 7, "cache_position": 7,
                       "max_seq_len": 4096})]
    + turno("r2", "Vale", ("Va", "le"), antes=7, despues=2), False)
F["inv10_turn_con_campo_memory"] = (
    [READY,
     req(type="turn", request_id="r1",
         messages=[{"role": "user", "content": "x"}],
         memory={"facts": ["es fontanero"]}),
     ev(type="prefill", request_id="r1", tokens=1, ms=1.0),
     ev(type="completed", request_id="r1", visible_text="", finish_reason="eos",
        usage={}, timings={},
        model_state={"cache_position_before": 0, "cache_position": 1})], False)
F["inv8_rgb8_sin_geometria"] = (
    [READY,
     req(type="attachment", request_id="a1", kind="rgb8", bytes=110592),
     ev(type="result", request_id="a1", ok=True,
        model_state={"cache_position_before": 0, "cache_position": 0})], False)
F["inv9_error_sin_model_state"] = (
    [READY,
     req(type="turn", request_id="r1", messages=[{"role": "user", "content": "x"}]),
     ev(type="prefill", request_id="r1", tokens=1, ms=1.0),
     ev(type="error", request_id="r1", code="context_full", message="lleno")],
    False)
# Refuerzos propios
F["inv6_compactacion_no_reduce"] = (
    [READY,
     req(type="turn", request_id="r1", messages=[{"role": "user", "content": "x"}]),
     ev(type="prefill", request_id="r1", tokens=1, ms=1.0),
     ev(type="context_compacted", request_id="r1",
        cache_position_before=100, cache_position_after=300),
     ev(type="completed", request_id="r1", visible_text="", finish_reason="eos",
        usage={}, timings={},
        model_state={"cache_position_before": 300, "cache_position": 301})],
    False)
F["inv8_rgb8_bytes_no_cuadran"] = (
    [READY,
     req(type="attachment", request_id="a1", kind="rgb8",
         width=192, height=192, stride=576, bytes=99999),
     ev(type="result", request_id="a1", ok=True,
        model_state={"cache_position_before": 0, "cache_position": 0})], False)
F["inv5_error_tras_emitir_sin_texto"] = (
    [READY,
     req(type="turn", request_id="r1", messages=[{"role": "user", "content": "x"}]),
     ev(type="prefill", request_id="r1", tokens=1, ms=1.0),
     ev(type="text_delta", request_id="r1", text="Empeza"),
     ev(type="error", request_id="r1", code="context_full", message="lleno",
        model_state={"cache_position_before": 0, "cache_position": 8})], False)
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
