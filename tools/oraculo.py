#!/usr/bin/env python3
"""
E0 del PLAN_EVACUACION_COGNITIVA: congelar y medir el oráculo.

`helios_chat` es hoy el oráculo del comportamiento cognitivo: casi 2.000 líneas
que mezclan identidad, memoria, registro, actos y presupuestos con el motor.
Antes de evacuar nada hay que poder demostrar qué hace, turno a turno, de forma
reproducible. Si no, cualquier extracción futura será un acto de fe.

Esta herramienta NO juzga si una respuesta es buena. Registra qué pasó — texto,
política, memoria escrita y procedencia — y lo deja comparable: la evacuación
se acepta si el informe nuevo coincide con el viejo en POLÍTICA, no si las
respuestas gustan más.

    python3 tools/oraculo.py --model <hnf> --engine <helios_chat> \
        --env HELIOS_EMBED_MMAP=1 --salida informes/base.json
    python3 tools/oraculo.py --diff informes/base.json informes/tras_e1.json

El `--diff` devuelve 1 si cambia la política o la estructura. Un informe que
no puede fallar no sirve para nada.

Los perfiles son temporales y desechables; la memoria real no se toca nunca.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# Batería: matriz de aceptación del plan (sección 7).
#
# Un caso puede tener VARIAS sesiones: cada una es un proceso distinto sobre el
# mismo perfil. Eso permite probar reinicio y persistencia, que con un solo
# proceso son indemostrables. `destila` activa la consolidación al salir (por
# defecto NO, para no ensuciar); `adjunto` inyecta una imagen RGB8 por el
# mismo protocolo binario que usa HexOS.
# ---------------------------------------------------------------------------

PERFIL_CONOCIDO = {
    "owner": "Andrés\n",
    "facts.md": "- Se llama Andrés.\n- Construyó el motor Héctor.\n"
                "- Prefiere que le hablen de forma directa.\n",
    "episodic.md": "## Sesión 2026-08-01 10:00\n"
                   "Me contó que estaba optimizando los kernels de decode.\n"
                   "Decidimos que la barrera era no perder más del 1% de velocidad.\n",
}


def imagen_circulo(w=192, h=192):
    """Círculo rojo sobre blanco: inequívoco de describir y barato de generar."""
    cx, cy, r = w // 2, h // 2, min(w, h) // 3
    px = bytearray()
    for y in range(h):
        for x in range(w):
            dentro = (x - cx) ** 2 + (y - cy) ** 2 < r * r
            px += bytes((220, 30, 30) if dentro else (250, 250, 250))
    return bytes(px), w, h


BATERIA = [
    {
        "nombre": "saludo_perfil_nuevo",
        "invariante": "sin familiaridad heredada ni oferta automática de ayuda",
        "perfil": {},
        "sesiones": [{"turnos": ["hola"]}],
    },
    {
        "nombre": "charla_perfil_conocido",
        "invariante": "conserva registro sin ampliar el acto",
        "perfil": PERFIL_CONOCIDO,
        "sesiones": [{"turnos": ["hola socio", "jajaja qué tal el finde",
                                 "nada nuevo por aquí"]}],
    },
    {
        "nombre": "pregunta_tecnica",
        "invariante": "responde y termina",
        "perfil": PERFIL_CONOCIDO,
        "sesiones": [{"turnos": ["¿qué es la latencia de prefill?"]}],
    },
    {
        "nombre": "artefacto_y_velocidad",
        "invariante": "continúa el artefacto, no lo trata como trivial",
        "perfil": PERFIL_CONOCIDO,
        "sesiones": [{"turnos": [
            "Te paso un texto. Léelo y coméntame lo esencial: "
            + "El kernel GEMV lee los pesos comprimidos y acumula en fp32. " * 12,
            "velocidad"]}],
    },
    {
        "nombre": "documento_y_resume",
        "invariante": "resume, no asesora ni reescribe",
        "perfil": PERFIL_CONOCIDO,
        "sesiones": [{"turnos": [
            "Te paso un texto. Léelo y coméntame lo esencial: "
            + "La tabla de embeddings ocupa 768 MiB y solo se consulta una fila. " * 12,
            "resume eso en una frase"]}],
    },
    {
        "nombre": "correccion_de_tema",
        "invariante": "corrige sin defenderse ni ampliar (no prueba memoria)",
        "perfil": PERFIL_CONOCIDO,
        "sesiones": [{"turnos": ["¿de qué color es el cielo?",
                                 "no, me refiero al cielo de Marte"]}],
    },
    {
        # El caso que la matriz exige de verdad: la corrección tiene que
        # cambiar el ESTADO, no solo la frase. Hoy no hay transición
        # candidate|confirmed|superseded — eso llega en E3 — así que este caso
        # está para documentar el hueco, no para pasar.
        "nombre": "hecho_falso_corregido",
        "invariante": "el hecho anterior queda superseded y el nuevo confirmed",
        "perfil": {"owner": "Andrés\n"},
        "sesiones": [{"turnos": [
            "recuerda que soy fontanero",
            "no, me equivoqué: soy ingeniero, no fontanero",
            "¿a qué me dedico?"], "destila": False}],
        "revisa_memoria": True,
    },
    {
        # Dos procesos sobre el mismo perfil: sin esto, la persistencia es
        # indemostrable. La primera sesión SÍ destila.
        "nombre": "reinicio_con_recuperacion",
        "invariante": "recupera hechos confirmados y tareas abiertas tras reiniciar",
        "perfil": {"owner": "Andrés\n"},
        "sesiones": [
            {"turnos": ["recuerda que mi perro se llama Byteazul",
                        "estoy escribiendo un libro sobre el motor"],
             "destila": True},
            {"turnos": ["¿cómo se llama mi perro?", "¿en qué estaba trabajando?"]},
        ],
        "revisa_memoria": True,
    },
    {
        "nombre": "imagen_y_pregunta_posterior",
        "invariante": "conserva la referencia al artefacto visual en turnos siguientes",
        "perfil": PERFIL_CONOCIDO,
        "necesita_vision": True,
        "sesiones": [{"turnos": ["¿qué ves en esta imagen?",
                                 "¿de qué color era la figura?"],
                      "adjunto": "circulo"}],
    },
    {
        "nombre": "cambio_y_retorno_de_tema",
        "invariante": "conserva ambos estados sin mezclarlos",
        "perfil": PERFIL_CONOCIDO,
        "sesiones": [{"turnos": ["hablemos de los kernels de decode",
                                 "oye cambiando de tema, ¿te gusta el mar?",
                                 "volvamos a lo de los kernels"]}],
    },
    {
        "nombre": "cierre_breve",
        "invariante": "reconocimiento breve, sin pregunta de servicio",
        "perfil": PERFIL_CONOCIDO,
        "sesiones": [{"turnos": ["todo listo por hoy", "nada más, me voy"]}],
    },
    {
        "nombre": "memoria_confirmada",
        "invariante": "recupera hechos del perfil, no dice que no tiene acceso",
        "perfil": PERFIL_CONOCIDO,
        "sesiones": [{"turnos": ["¿qué sabes de mí?", "¿cómo me llamo?"]}],
    },
    {
        "nombre": "perfil_vacio_sin_fuga",
        "invariante": "cero fuga de identidad o hechos de otro perfil",
        "perfil": {},
        "sesiones": [{"turnos": ["¿qué sabes de mí?", "¿cómo me llamo?"]}],
    },
]

FICHEROS_MEMORIA = ("facts.md", "episodic.md", "candidates.md")

# ---------------------------------------------------------------------------
# Detectores mecánicos: cuentan cosas verificables, no opinan sobre calidad.
# ---------------------------------------------------------------------------

CJK = re.compile(r"[一-鿿぀-ヿ]")
OFERTA = re.compile(
    r"necesitas algo|si necesitas|necesites|ayudarte|echar una mano|"
    r"estar[ée] aqu[íi]|estoy aqu[íi]|en qu[ée] puedo|no dudes en", re.I)
CONTRATO = re.compile(
    r"contrato ck|instruccion interna|instrucción interna|\bacto:|"
    r"registro:|sin inventar experiencia|no ampl[íi]es la tarea", re.I)
STATS = re.compile(r"\[(\d+) tok[^\]]*\]")
CAMPO_ACTO = re.compile(r"acto (\w+)")
CAMPO_REG = re.compile(r"registro (\w+)")
CAMPO_TEMP = re.compile(r"temp ([\d.]+)")
CAMPO_CTX = re.compile(r"ctx (\d+)/(\d+)")
PENSANDO = re.compile(r"\(pensando[^)]*\)")


def sha256(path, trozo=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(trozo)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def git_head(repo):
    try:
        return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                              capture_output=True, text=True,
                              timeout=15).stdout.strip()[:12]
    except Exception:
        return None


def env_efectivo(extra_env):
    """TODAS las HELIOS_* que verá el motor, no solo las de --env.

    El proceso hijo hereda el entorno del shell: si alguien corre la batería
    con HELIOS_CTX=8192 exportado, el informe decía `env: {}` y la base
    quedaba irreproducible sin que nadie lo notara. Se registra lo que de
    verdad va a estar puesto.
    """
    efectivo = {k: v for k, v in os.environ.items() if k.startswith("HELIOS_")}
    efectivo.update(extra_env)
    return efectivo


def procedencia(model, engine, extra_env, con_sha):
    """Sin esto el informe no es reproducible: 'qwen3_8b.hnf' no identifica nada
    dentro de tres semanas."""
    eng_dir = os.path.dirname(os.path.dirname(os.path.abspath(engine)))
    heredadas = sorted(k for k in os.environ if k.startswith("HELIOS_")
                       and k not in extra_env)
    return {
        "modelo_ruta": os.path.abspath(model),
        "modelo_bytes": os.path.getsize(model),
        "modelo_sha256": sha256(model) if con_sha else None,
        "engine_ruta": os.path.abspath(engine),
        "engine_sha256": sha256(engine) if con_sha else None,
        "engine_mtime": int(os.path.getmtime(engine)),
        "hector_commit": git_head(eng_dir),
        "hexos_commit": git_head(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))),
        "env": env_efectivo(extra_env),
        "env_explicito": extra_env,
        "env_heredado": heredadas,
        "bateria_casos": len(BATERIA),
    }


def leer_memoria(home):
    out = {}
    for n in FICHEROS_MEMORIA:
        p = os.path.join(home, n)
        out[n] = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    return out


def delta_memoria(antes, despues):
    """Qué escribió el motor. E0 exige saberlo: la memoria es estado, y el
    estado es justo lo que la evacuación tiene que conservar."""
    d = {}
    for n in FICHEROS_MEMORIA:
        a, b = antes.get(n, ""), despues.get(n, "")
        if a == b:
            continue
        la = set(a.splitlines())
        nuevas = [l for l in b.splitlines() if l.strip() and l not in la]
        d[n] = {"bytes_antes": len(a), "bytes_despues": len(b),
                "lineas_nuevas": nuevas[:12]}
    return d


def analizar_turno(bruto, stats_line, previas):
    texto = PENSANDO.sub("", bruto).strip()
    texto = re.sub(r"^</think>\s*", "", texto)
    frases = [f.strip().lower() for f in re.split(r"[.!?\n]", texto)
              if len(f.strip()) > 15]
    return {
        "texto": texto,
        "chars": len(texto),
        "mudo": len(texto) == 0,
        "cjk": len(CJK.findall(texto)),
        "oferta_servicio": len(OFERTA.findall(texto)),
        "fuga_contrato": len(CONTRATO.findall(texto)),
        "frases_repetidas": len(frases) - len(set(frases)),
        "identico_a_previo": bool(texto) and texto in previas,
        "acto": (CAMPO_ACTO.search(stats_line) or [None, None])[1],
        "registro": (CAMPO_REG.search(stats_line) or [None, "neutral"])[1],
        "temp": float((CAMPO_TEMP.search(stats_line) or [0, 0])[1]),
        "tokens": int((STATS.search(stats_line) or [0, 0])[1]),
        "presupuesto_agotado": "presupuesto" in stats_line and "agotado" in stats_line,
        "pensamiento_cortado": "pensamiento cortado" in stats_line,
        "ctx": int((CAMPO_CTX.search(stats_line) or [0, 0, 0])[1]),
    }


def entrada_sesion(sesion):
    """Bytes, no str: el adjunto viaja por el mismo protocolo binario que usa
    HexOS (`/adjunto-rgb8 W H STRIDE N` + N bytes crudos)."""
    buf = b""
    turnos = sesion["turnos"]
    for i, t in enumerate(turnos):
        if i == 0 and sesion.get("adjunto") == "circulo":
            px, w, h = imagen_circulo()
            buf += f"/adjunto-rgb8 {w} {h} {w*3} {len(px)}\n".encode()
            buf += px + b"\n"
        buf += t.encode("utf-8") + b"\n"
    return buf + b"/salir\n"


def correr_caso(caso, model, engine, extra_env, tiene_vision):
    if caso.get("necesita_vision") and not tiene_vision:
        return {"nombre": caso["nombre"], "invariante": caso["invariante"],
                "estado": "SALTADO", "motivo": "el modelo no declara visión",
                "sesiones": [], "turnos": []}

    home = tempfile.mkdtemp(prefix="oraculo_")
    try:
        for nombre, contenido in caso["perfil"].items():
            with open(os.path.join(home, nombre), "w", encoding="utf-8") as f:
                f.write(contenido)

        sesiones, todos, previas = [], [], []
        for idx, sesion in enumerate(caso["sesiones"]):
            env = dict(os.environ)
            env["HELIOS_HOME"] = home
            if not sesion.get("destila"):
                env["HELIOS_NO_DISTILL"] = "1"
            else:
                env.pop("HELIOS_NO_DISTILL", None)
            env.update(extra_env)

            antes = leer_memoria(home)
            proc = subprocess.run([engine, model, "0.7"],
                                  input=entrada_sesion(sesion), env=env,
                                  capture_output=True, timeout=1200)
            salida = re.sub(r"\x1b\[[0-9;]*m", "",
                            proc.stdout.decode("utf-8", "replace"))
            despues = leer_memoria(home)
            # Un motor que muere a mitad puede dejar turnos capturados y
            # parecer una captura sana. El código de salida es la única señal
            # fiable de que la sesión terminó como debía.
            err_cola = proc.stderr.decode("utf-8", "replace").strip()[-300:]

            bloques = re.findall(r"helios> (.*?)\n(\[\d+ tok[^\]]*\])", salida, re.S)
            turnos = []
            for i, (bruto, stats) in enumerate(bloques):
                t = analizar_turno(bruto, stats, previas)
                t["sesion"] = idx + 1
                t["n"] = len(todos) + i + 1
                msg = sesion["turnos"][i] if i < len(sesion["turnos"]) else "?"
                t["mensaje"] = msg if len(msg) <= 90 else msg[:90] + f"… ({len(msg)} chars)"
                previas.append(t["texto"])
                turnos.append(t)
            todos.extend(turnos)

            sesiones.append({
                "indice": idx + 1,
                "destila": bool(sesion.get("destila")),
                "adjunto": sesion.get("adjunto"),
                "turnos_esperados": len(sesion["turnos"]),
                "turnos_capturados": len(turnos),
                "returncode": proc.returncode,
                "stderr_cola": err_cola if proc.returncode != 0 else "",
                "memoria_delta": delta_memoria(antes, despues),
                "avisos": re.findall(
                    r"\((?:texto truncado|reorganizando|turno grande|imagen "
                    r"lista|imagen rechazada)[^)]*\)", salida),
            })

        esperados = sum(len(s["turnos"]) for s in caso["sesiones"])
        malas = [s for s in sesiones if s["returncode"] != 0]
        if malas:
            estado = "FALLO_MOTOR"
        elif len(todos) != esperados:
            estado = "INCOMPLETO"
        else:
            estado = "OK"
        return {
            "nombre": caso["nombre"],
            "invariante": caso["invariante"],
            "estado": estado,
            "turnos_esperados": esperados,
            "turnos_capturados": len(todos),
            # Siempre, no solo en los casos marcados: una sustitución del
            # mismo tamaño no aparece en el delta y sí en el estado final.
            "memoria_final": leer_memoria(home),
            "sesiones": sesiones,
            "turnos": todos,
        }
    finally:
        shutil.rmtree(home, ignore_errors=True)


def resumen(informe):
    t = [x for c in informe["casos"] for x in c["turnos"]]
    if not t:
        return {}
    return {
        "casos": len(informe["casos"]),
        "saltados": sum(1 for c in informe["casos"] if c.get("estado") == "SALTADO"),
        "incompletos": sum(1 for c in informe["casos"] if c.get("estado") == "INCOMPLETO"),
        "fallos_motor": sum(1 for c in informe["casos"] if c.get("estado") == "FALLO_MOTOR"),
        "turnos": len(t),
        "mudos": sum(1 for x in t if x["mudo"]),
        "ofertas_servicio": sum(x["oferta_servicio"] for x in t),
        "fugas_contrato": sum(x["fuga_contrato"] for x in t),
        "cjk": sum(x["cjk"] for x in t),
        "repeticiones": sum(x["frases_repetidas"] for x in t),
        "respuestas_identicas": sum(1 for x in t if x["identico_a_previo"]),
        "presupuestos_agotados": sum(1 for x in t if x["presupuesto_agotado"]),
        "pensamientos_cortados": sum(1 for x in t if x["pensamiento_cortado"]),
        "tokens_medios": round(sum(x["tokens"] for x in t) / len(t), 1),
    }


def diff(a_path, b_path):
    """Devuelve 1 si cambia la POLÍTICA o la ESTRUCTURA. El texto puede variar
    por muestreo sin que nada haya cambiado, así que no marca fallo por sí
    solo — pero un turno que desaparece, sí."""
    a, b = json.load(open(a_path)), json.load(open(b_path))
    ca = {c["nombre"]: c for c in a["casos"]}
    cb = {c["nombre"]: c for c in b["casos"]}

    pa, pb = a.get("procedencia", {}), b.get("procedencia", {})
    for campo in ("modelo_sha256", "engine_sha256", "hector_commit"):
        if pa.get(campo) != pb.get(campo):
            print(f"· {campo}: {pa.get(campo)} → {pb.get(campo)}")
    print()

    fallos = 0
    for nombre in sorted(set(ca) | set(cb)):
        if nombre not in ca or nombre not in cb:
            print(f"[ESTRUCTURA] {nombre}: solo está en uno de los dos informes")
            fallos += 1
            continue
        ta, tb = ca[nombre]["turnos"], cb[nombre]["turnos"]
        if len(ta) != len(tb):
            print(f"[ESTRUCTURA] {nombre}: {len(ta)} turnos → {len(tb)}")
            fallos += 1
        if ca[nombre].get("estado") != cb[nombre].get("estado"):
            print(f"[ESTRUCTURA] {nombre}: estado "
                  f'{ca[nombre].get("estado")} → {cb[nombre].get("estado")}')
            fallos += 1
        # Recorrer la UNIÓN, no el mínimo: zip() escondía turnos perdidos.
        for i in range(max(len(ta), len(tb))):
            xa = ta[i] if i < len(ta) else None
            xb = tb[i] if i < len(tb) else None
            if xa is None or xb is None:
                print(f"[ESTRUCTURA] {nombre} turno {i+1}: "
                      f'{"falta en B" if xb is None else "falta en A"}')
                fallos += 1
                continue
            if (xa["acto"], xa["registro"]) != (xb["acto"], xb["registro"]):
                print(f'[POLÍTICA] {nombre} turno {i+1}: '
                      f'{xa["acto"]}/{xa["registro"]} → {xb["acto"]}/{xb["registro"]}')
                fallos += 1
            elif xa["texto"] != xb["texto"]:
                print(f"[texto] {nombre} turno {i+1}: distinto (informativo)")
        da = {s["indice"]: s["memoria_delta"] for s in ca[nombre].get("sesiones", [])}
        db = {s["indice"]: s["memoria_delta"] for s in cb[nombre].get("sesiones", [])}
        if da != db:
            print(f"[MEMORIA] {nombre}: cambió lo que se escribió en memoria")
            fallos += 1
        # El delta no ve una sustitución del mismo tamaño (mismo número de
        # bytes, otro contenido): hay que comparar también el estado final.
        # Solo si ambos informes lo traen, para no romper bases anteriores.
        fa, fb = ca[nombre].get("memoria_final"), cb[nombre].get("memoria_final")
        if fa is not None and fb is not None and fa != fb and da == db:
            for fich in sorted(set(fa) | set(fb)):
                if fa.get(fich) != fb.get(fich):
                    print(f"[MEMORIA] {nombre}: estado final distinto en {fich}")
            fallos += 1
        # `None` = informe anterior al registro de returncode; no es un cambio.
        rca = [s.get("returncode") for s in ca[nombre].get("sesiones", [])]
        rcb = [s.get("returncode") for s in cb[nombre].get("sesiones", [])]
        if None not in rca and None not in rcb and rca != rcb:
            print(f"[MOTOR] {nombre}: códigos de salida {rca} → {rcb}")
            fallos += 1

    print()
    print("resumen A:", json.dumps(a.get("resumen", {}), ensure_ascii=False))
    print("resumen B:", json.dumps(b.get("resumen", {}), ensure_ascii=False))
    print()
    print(f"diferencias de política/estructura/memoria: {fallos}")
    return 1 if fallos else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--engine")
    ap.add_argument("--probe", help="helios_model_probe, para saber si hay visión")
    ap.add_argument("--salida", default="informe_oraculo.json")
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--solo")
    ap.add_argument("--sin-sha", action="store_true",
                    help="omitir SHA256 del HNF (rápido, informe no certificable)")
    ap.add_argument("--diff", nargs=2, metavar=("A", "B"))
    args = ap.parse_args()

    if args.diff:
        return diff(*args.diff)
    if not args.model or not args.engine:
        ap.error("--model y --engine son obligatorios (o usa --diff)")

    extra_env = dict(kv.split("=", 1) for kv in args.env)

    tiene_vision = False
    if args.probe and os.path.exists(args.probe):
        try:
            r = subprocess.run([args.probe, args.model], capture_output=True,
                               text=True, timeout=120)
            tiene_vision = "vision" in r.stdout and "runtime_ready" in r.stdout
        except Exception:
            pass

    print("calculando procedencia (SHA256 del HNF)…" if not args.sin_sha else "")
    informe = {"procedencia": procedencia(args.model, args.engine, extra_env,
                                          not args.sin_sha),
               "vision_disponible": tiene_vision, "casos": []}

    casos = [c for c in BATERIA if not args.solo or c["nombre"] == args.solo]
    for i, caso in enumerate(casos, 1):
        print(f"[{i}/{len(casos)}] {caso['nombre']}…", flush=True)
        r = correr_caso(caso, args.model, args.engine, extra_env, tiene_vision)
        informe["casos"].append(r)
        if r.get("estado") == "FALLO_MOTOR":
            malas = [s for s in r["sesiones"] if s["returncode"] != 0]
            print(f'    FALLO DEL MOTOR: returncode '
                  f'{[s["returncode"] for s in malas]} — {malas[0]["stderr_cola"][-160:]}')
        elif r.get("estado") not in ("OK", "SALTADO"):
            print(f'    AVISO: {r["turnos_capturados"]}/{r["turnos_esperados"]} turnos')

    informe["resumen"] = resumen(informe)
    with open(args.salida, "w", encoding="utf-8") as f:
        json.dump(informe, f, ensure_ascii=False, indent=1)

    print("\n" + "=" * 72)
    for c in informe["casos"]:
        print(f'\n{c["nombre"]}  [{c.get("estado")}]  —  {c["invariante"]}')
        if c.get("estado") == "SALTADO":
            print(f'  {c["motivo"]}')
            continue
        for t in c["turnos"]:
            señales = "".join([
                " MUDO" if t["mudo"] else "",
                f' oferta×{t["oferta_servicio"]}' if t["oferta_servicio"] else "",
                f' fuga×{t["fuga_contrato"]}' if t["fuga_contrato"] else "",
                f' cjk×{t["cjk"]}' if t["cjk"] else "",
                " IDÉNTICA" if t["identico_a_previo"] else "",
                " CORTE" if t["presupuesto_agotado"] else "",
            ])
            print(f'  s{t["sesion"]} [{t["acto"]}/{t["registro"]} {t["tokens"]}tok]{señales}')
            print(f'    tú: {t["mensaje"]}')
            print(f'    él: {t["texto"][:150]}')
        for s in c["sesiones"]:
            if s["memoria_delta"]:
                print(f'  memoria escrita (sesión {s["indice"]}): '
                      f'{json.dumps(s["memoria_delta"], ensure_ascii=False)[:300]}')
            if s["avisos"]:
                print(f'  avisos: {s["avisos"]}')

    print("\nRESUMEN:", json.dumps(informe["resumen"], ensure_ascii=False))
    print(f'procedencia: hector@{informe["procedencia"]["hector_commit"]} · '
          f'modelo sha {str(informe["procedencia"]["modelo_sha256"])[:12]}')
    print(f"informe en {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
