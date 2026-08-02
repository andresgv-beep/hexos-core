#!/usr/bin/env python3
"""
E0 del PLAN_EVACUACION_COGNITIVA: congelar y medir el oráculo.

`helios_chat` es hoy el oráculo del comportamiento cognitivo: 1.958 líneas que
mezclan identidad, memoria, registro, actos y presupuestos con el motor. Antes
de evacuar nada hay que poder demostrar qué hace, turno a turno, de forma
reproducible. Si no, cualquier extracción futura será un acto de fe.

Esta herramienta NO juzga si una respuesta es buena. Registra qué pasó y lo
deja comparable: la evacuación se acepta si el informe nuevo coincide con el
viejo, no si las respuestas gustan más.

    python3 tools/oraculo.py --model <hnf> --engine <helios_chat> \
        --salida informes/base.json
    python3 tools/oraculo.py --diff informes/base.json informes/tras_e1.json

Cada caso corre en un perfil aislado y desechable (HELIOS_HOME temporal), con
HELIOS_NO_DISTILL salvo que el caso pruebe justamente la consolidación. La
memoria real de Andrés no se toca nunca.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# La batería sale de la matriz de aceptación del plan (sección 7). Cada caso
# declara su invariante en texto: hoy lo juzga una persona leyendo el informe,
# pero queda escrito junto a la evidencia y no en la cabeza de nadie.
# ---------------------------------------------------------------------------

PERFIL_CONOCIDO = {
    "owner": "Andrés\n",
    "facts.md": "- Se llama Andrés.\n- Construyó el motor Héctor.\n"
                "- Prefiere que le hablen de forma directa.\n",
    "episodic.md": "## Sesión 2026-08-01 10:00\n"
                   "Me contó que estaba optimizando los kernels de decode.\n"
                   "Decidimos que la barrera era no perder más del 1% de velocidad.\n",
}

BATERIA = [
    {
        "nombre": "saludo_perfil_nuevo",
        "invariante": "sin familiaridad heredada ni oferta automática de ayuda",
        "perfil": {},
        "turnos": ["hola"],
    },
    {
        "nombre": "charla_perfil_conocido",
        "invariante": "conserva registro sin ampliar el acto",
        "perfil": PERFIL_CONOCIDO,
        "turnos": ["hola socio", "jajaja qué tal el finde", "nada nuevo por aquí"],
    },
    {
        "nombre": "pregunta_tecnica",
        "invariante": "responde y termina",
        "perfil": PERFIL_CONOCIDO,
        "turnos": ["¿qué es la latencia de prefill?"],
    },
    {
        "nombre": "artefacto_y_velocidad",
        "invariante": "continúa el artefacto, no lo trata como trivial",
        "perfil": PERFIL_CONOCIDO,
        "turnos": [
            "Te paso un texto. Léelo y coméntame lo esencial: "
            + "El kernel GEMV lee los pesos comprimidos y acumula en fp32. " * 12,
            "velocidad",
        ],
    },
    {
        "nombre": "documento_y_resume",
        "invariante": "resume, no asesora ni reescribe",
        "perfil": PERFIL_CONOCIDO,
        "turnos": [
            "Te paso un texto. Léelo y coméntame lo esencial: "
            + "La tabla de embeddings ocupa 768 MiB y solo se consulta una fila. " * 12,
            "resume eso en una frase",
        ],
    },
    {
        "nombre": "correccion",
        "invariante": "corrige sin defenderse ni ampliar",
        "perfil": PERFIL_CONOCIDO,
        "turnos": ["¿de qué color es el cielo?", "no, me refiero al cielo de Marte"],
    },
    {
        "nombre": "cambio_y_retorno_de_tema",
        "invariante": "conserva ambos estados sin mezclarlos",
        "perfil": PERFIL_CONOCIDO,
        "turnos": [
            "hablemos de los kernels de decode",
            "oye cambiando de tema, ¿te gusta el mar?",
            "volvamos a lo de los kernels",
        ],
    },
    {
        "nombre": "cierre_breve",
        "invariante": "reconocimiento breve, sin pregunta de servicio",
        "perfil": PERFIL_CONOCIDO,
        "turnos": ["todo listo por hoy", "nada más, me voy"],
    },
    {
        "nombre": "memoria_confirmada",
        "invariante": "recupera hechos del perfil, no dice que no tiene acceso",
        "perfil": PERFIL_CONOCIDO,
        "turnos": ["¿qué sabes de mí?", "¿cómo me llamo?"],
    },
    {
        "nombre": "perfil_vacio_sin_fuga",
        "invariante": "cero fuga de identidad o hechos de otro perfil",
        "perfil": {},
        "turnos": ["¿qué sabes de mí?", "¿cómo me llamo?"],
    },
]

# ---------------------------------------------------------------------------
# Detectores mecánicos. No opinan sobre calidad: cuentan cosas verificables.
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
        "identico_a_previo": texto in previas and bool(texto),
        "acto": (CAMPO_ACTO.search(stats_line) or [None, None])[1],
        "registro": (CAMPO_REG.search(stats_line) or [None, "neutral"])[1],
        "temp": float((CAMPO_TEMP.search(stats_line) or [0, 0])[1]),
        "tokens": int((STATS.search(stats_line) or [0, 0])[1]),
        "presupuesto_agotado": "presupuesto" in stats_line and "agotado" in stats_line,
        "pensamiento_cortado": "pensamiento cortado" in stats_line,
        "ctx": int((CAMPO_CTX.search(stats_line) or [0, 0, 0])[1]),
    }


def correr_caso(caso, model, engine, extra_env):
    """Un proceso por caso, con perfil aislado que se destruye al terminar."""
    home = tempfile.mkdtemp(prefix="oraculo_")
    try:
        for nombre, contenido in caso["perfil"].items():
            with open(os.path.join(home, nombre), "w", encoding="utf-8") as f:
                f.write(contenido)

        env = dict(os.environ)
        env["HELIOS_HOME"] = home
        env["HELIOS_NO_DISTILL"] = "1"
        env.update(extra_env)

        entrada = "\n".join(caso["turnos"] + ["/salir"]) + "\n"
        proc = subprocess.run(
            [engine, model, "0.7"], input=entrada, env=env,
            capture_output=True, text=True, timeout=900, errors="replace")
        salida = re.sub(r"\x1b\[[0-9;]*m", "", proc.stdout)

        # El REPL delimita: "helios> " abre la respuesta, la línea [N tok...]
        # la cierra. Es el mismo contrato frágil que HexOS parsea hoy y que la
        # evacuación quiere sustituir — por eso este informe es el "antes".
        bloques = re.findall(r"helios> (.*?)\n(\[\d+ tok[^\]]*\])", salida, re.S)
        avisos = re.findall(r"\((?:texto truncado|reorganizando|turno grande)[^)]*\)",
                            salida)

        turnos, previas = [], []
        for i, (bruto, stats) in enumerate(bloques):
            t = analizar_turno(bruto, stats, previas)
            t["n"] = i + 1
            t["mensaje"] = caso["turnos"][i] if i < len(caso["turnos"]) else "?"
            if len(t["mensaje"]) > 90:
                t["mensaje"] = t["mensaje"][:90] + f"… ({len(t['mensaje'])} chars)"
            previas.append(t["texto"])
            turnos.append(t)

        return {
            "nombre": caso["nombre"],
            "invariante": caso["invariante"],
            "turnos_esperados": len(caso["turnos"]),
            "turnos_capturados": len(turnos),
            "avisos": avisos,
            "turnos": turnos,
        }
    finally:
        shutil.rmtree(home, ignore_errors=True)


def resumen(informe):
    t = [x for c in informe["casos"] for x in c["turnos"]]
    if not t:
        return {}
    return {
        "turnos": len(t),
        "mudos": sum(1 for x in t if x["mudo"]),
        "ofertas_servicio": sum(x["oferta_servicio"] for x in t),
        "fugas_contrato": sum(x["fuga_contrato"] for x in t),
        "cjk": sum(x["cjk"] for x in t),
        "repeticiones": sum(x["frases_repetidas"] for x in t),
        "presupuestos_agotados": sum(1 for x in t if x["presupuesto_agotado"]),
        "pensamientos_cortados": sum(1 for x in t if x["pensamiento_cortado"]),
        "tokens_medios": round(sum(x["tokens"] for x in t) / len(t), 1),
    }


def diff(a_path, b_path):
    a = json.load(open(a_path)); b = json.load(open(b_path))
    ca = {c["nombre"]: c for c in a["casos"]}
    cb = {c["nombre"]: c for c in b["casos"]}
    print(f"{'caso':<28} {'acto/registro':<28} texto")
    print("-" * 92)
    cambios = 0
    for nombre in sorted(set(ca) | set(cb)):
        if nombre not in ca or nombre not in cb:
            print(f"{nombre:<28} SOLO EN UNO DE LOS DOS INFORMES")
            cambios += 1
            continue
        for ta, tb in zip(ca[nombre]["turnos"], cb[nombre]["turnos"]):
            marca_pol = (ta["acto"], ta["registro"]) != (tb["acto"], tb["registro"])
            marca_txt = ta["texto"] != tb["texto"]
            if not (marca_pol or marca_txt):
                continue
            cambios += 1
            pol = (f'{ta["acto"]}/{ta["registro"]} → {tb["acto"]}/{tb["registro"]}'
                   if marca_pol else "igual")
            print(f'{nombre[:27]:<28} {pol:<28} '
                  f'{"DISTINTO" if marca_txt else "igual"}  (turno {ta["n"]})')
    print()
    print(f"turnos con diferencias: {cambios}")
    print("resumen A:", json.dumps(a.get("resumen", {}), ensure_ascii=False))
    print("resumen B:", json.dumps(b.get("resumen", {}), ensure_ascii=False))
    # La política es lo que la evacuación DEBE conservar; el texto puede variar
    # por el muestreo aunque nada haya cambiado.
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--engine")
    ap.add_argument("--salida", default="informe_oraculo.json")
    ap.add_argument("--env", action="append", default=[],
                    help="VAR=valor extra para el motor (repetible)")
    ap.add_argument("--solo", help="correr un único caso por nombre")
    ap.add_argument("--diff", nargs=2, metavar=("A", "B"))
    args = ap.parse_args()

    if args.diff:
        return diff(*args.diff)
    if not args.model or not args.engine:
        ap.error("--model y --engine son obligatorios (o usa --diff)")

    extra_env = dict(kv.split("=", 1) for kv in args.env)
    casos = [c for c in BATERIA if not args.solo or c["nombre"] == args.solo]

    informe = {"modelo": os.path.basename(args.model),
               "env": extra_env, "casos": []}
    for i, caso in enumerate(casos, 1):
        print(f"[{i}/{len(casos)}] {caso['nombre']}…", flush=True)
        r = correr_caso(caso, args.model, args.engine, extra_env)
        informe["casos"].append(r)
        if r["turnos_capturados"] != r["turnos_esperados"]:
            print(f"    AVISO: {r['turnos_capturados']} de "
                  f"{r['turnos_esperados']} turnos capturados")

    informe["resumen"] = resumen(informe)
    with open(args.salida, "w", encoding="utf-8") as f:
        json.dump(informe, f, ensure_ascii=False, indent=1)

    print()
    print("=" * 72)
    for c in informe["casos"]:
        print(f'\n{c["nombre"]}  —  {c["invariante"]}')
        for t in c["turnos"]:
            señales = "".join([
                " MUDO" if t["mudo"] else "",
                f' oferta×{t["oferta_servicio"]}' if t["oferta_servicio"] else "",
                f' fuga×{t["fuga_contrato"]}' if t["fuga_contrato"] else "",
                f' cjk×{t["cjk"]}' if t["cjk"] else "",
                " CORTE" if t["presupuesto_agotado"] else "",
            ])
            print(f'  [{t["acto"]}/{t["registro"]} {t["tokens"]}tok]{señales}')
            print(f'    tú: {t["mensaje"]}')
            print(f'    él: {t["texto"][:150]}')
        if c["avisos"]:
            print(f'  avisos del motor: {c["avisos"]}')
    print()
    print("RESUMEN:", json.dumps(informe["resumen"], ensure_ascii=False))
    print(f"informe en {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
