#!/usr/bin/env python3
"""
Barrera del registro de chats, antes de la UI.

Los siete puntos, contra el servidor y el motor de verdad:
  1. A y B recuerdan únicamente su conversación.
  2. Cambiar y volver conserva el KV vivo (no se rehace el contexto).
  3. Reiniciar el runtime y volver reconstruye desde la transcripción.
  4. Cerrar libera el KV pero no borra el chat.
  5. Borrar borra solo el chat elegido.
  6. Una respuesta cancelada a medias queda representada honestamente.
  7. La ruta /api/chat antigua sigue funcionando.

uso: chats_test.py --model <hnf> --runtime <bin> --serve <bin>
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

PUERTO = 8131
BASE = f"http://127.0.0.1:{PUERTO}"
fallos = pruebas = 0


def ok(cond, nombre, detalle=""):
    global fallos, pruebas
    pruebas += 1
    if cond:
        print(f"  \033[32m✓\033[0m {nombre}")
    else:
        fallos += 1
        print(f"  \033[31m✗ {nombre}\033[0m — {detalle}")


def pedir(ruta, datos=None, metodo=None):
    # OJO: `b""` es falsy en Python. Deducir el método de si hay cuerpo mandaba
    # GET en todas las acciones sin cuerpo y no se activaba ningún chat — la
    # prueba "fallaba" por su propio cliente, no por el servidor.
    if metodo is None:
        metodo = "POST" if datos is not None else "GET"
    req = urllib.request.Request(BASE + ruta, data=datos or b"",
                                 method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.read().decode("utf-8", "replace")


class Servidor:
    def __init__(self, args, home, traza):
        self.args, self.home, self.traza = args, home, traza

    def __enter__(self):
        self.proc = subprocess.Popen(
            [self.args.serve, "--model", self.args.model,
             "--runtime", self.args.runtime, "--port", str(PUERTO),
             "--no-probe", "--no-distill"],
            env=dict(os.environ, HELIOS_HOME=self.home, HELIOS_CTX="8192",
                     HELIOS_EMBED_IN_RAM="1", HEXOS_RT_TRACE=self.traza),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid)
        for _ in range(150):
            try:
                if "idle" in pedir("/api/status"):
                    return self
            except Exception:
                pass
            time.sleep(1)
        raise RuntimeError("no arrancó")

    def __exit__(self, *_):
        os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
        self.proc.wait(timeout=60)

    def hablar(self, texto, espera=120):
        antes = self.texto_total()
        pedir("/api/chat", texto.encode("utf-8"))
        for _ in range(espera):
            time.sleep(1)
            if "idle" in pedir("/api/status"):
                time.sleep(0.4)
                break
        return self.texto_total()[len(antes):]

    def eventos(self):
        if not os.path.exists(self.traza):
            return []
        out = []
        with open(self.traza, encoding="utf-8", errors="replace") as f:
            for l in f:
                if l.strip():
                    try:
                        out.append(json.loads(l))
                    except json.JSONDecodeError:
                        pass
        return out

    def texto_total(self):
        return "".join(e["payload"].get("text", "") for e in self.eventos()
                       if e["direction"] == "event"
                       and e["payload"].get("type") == "text_delta")

    def peticiones(self):
        return [e["payload"] for e in self.eventos() if e["direction"] == "request"]


def main():
    ap = argparse.ArgumentParser()
    for f in ("model", "runtime", "serve"):
        ap.add_argument(f"--{f}", required=True)
    args = ap.parse_args()

    raiz = tempfile.mkdtemp(prefix="chats_")
    home = os.path.join(raiz, "perfil")
    os.makedirs(home)
    traza = os.path.join(raiz, "t.jsonl")

    with Servidor(args, home, traza) as s:
        print("\n[1] dos chats, cada uno con lo suyo")
        a = json.loads(pedir("/api/chats", b"Libro"))["id"]
        b = json.loads(pedir("/api/chats", b"CUDA"))["id"]
        ok(a != b, "se crean dos chats distintos", f"{a} {b}")

        pedir(f"/api/chats/{a}/activar", b"")
        s.hablar("Recuerda: mi perro se llama Byteazul. Di solo: vale.")
        pedir(f"/api/chats/{b}/activar", b"")
        s.hablar("Recuerda: mi gato se llama Nube. Di solo: vale.")

        pedir(f"/api/chats/{a}/activar", b"")
        ra = s.hablar("¿Cómo se llama mi perro? Solo el nombre.")
        ok("byteazul" in ra.lower(), "A recuerda lo de A", repr(ra[:80]))
        ok("nube" not in ra.lower(), "y nada de B", repr(ra[:80]))

        pedir(f"/api/chats/{b}/activar", b"")
        rb = s.hablar("¿Cómo se llama mi gato? Solo el nombre.")
        ok("nube" in rb.lower(), "B recuerda lo de B", repr(rb[:80]))
        ok("byteazul" not in rb.lower(), "y nada de A", repr(rb[:80]))

        print("\n[2] cambiar y volver NO rehace el contexto")
        # Si el KV siguiera vivo, el turno no reenvía la transcripción: el
        # mensaje al motor lleva solo el contrato y el mensaje nuevo.
        pedir(f"/api/chats/{a}/activar", b"")
        antes = len(s.peticiones())
        s.hablar("Di solo: vuelvo.")
        turnos = [p for p in s.peticiones()[antes:] if p.get("type") == "turn"]
        roles = [m["role"] for m in turnos[0]["messages"]] if turnos else []
        ok(roles and roles.count("user") == 1 and "assistant" not in roles,
           "al volver a A no se reenvía la transcripción: su KV sigue vivo",
           str(roles))
        ok(not any(p.get("type") == "reset" for p in s.peticiones()[antes:]),
           "y no hace falta ningún reset", "reseteó sin motivo")

        print("\n[3] el chat elegido llega al motor como `session`")
        ok(turnos and turnos[0].get("session") == a,
           "el turno viaja con el id del chat activo",
           str(turnos[0].get("session") if turnos else None))

        print("\n[4] cerrar libera el KV y CONSERVA la conversación")
        pedir(f"/api/chats/{a}/cerrar", b"")
        lista = json.loads(pedir("/api/chats"))
        ficha = [c for c in lista["chats"] if c["id"] == a][0]
        ok(ficha["sesion_viva"] is False, "la sesión consta cerrada", str(ficha))
        ok(ficha["turnos"] > 0, "y el chat conserva sus turnos", str(ficha))

        antes = len(s.peticiones())
        ra2 = s.hablar("¿Cómo se llama mi perro? Solo el nombre.")
        turnos = [p for p in s.peticiones()[antes:] if p.get("type") == "turn"]
        roles = [m["role"] for m in turnos[0]["messages"]] if turnos else []
        ok("assistant" in roles,
           "al volver a hablar se reconstruye desde la transcripción",
           str(roles))
        ok("byteazul" in ra2.lower(),
           "y sigue sabiendo lo de antes", repr(ra2[:80]))

        print("\n[5] la ruta antigua sigue funcionando")
        rv = s.hablar("Di solo: compatible.")
        ok("compatible" in rv.lower(),
           "/api/chat sin saber de chats manda al activo", repr(rv[:80]))

        print("\n[6] borrar es otra cosa, y solo borra el elegido")
        pedir(f"/api/chats/{b}/borrar", b"")
        lista = json.loads(pedir("/api/chats"))
        ids = [c["id"] for c in lista["chats"]]
        ok(b not in ids, "B desaparece de la lista", str(ids))
        ok(a in ids, "y A sigue ahí", str(ids))

    print("\n[7] reiniciar el motor: los chats sobreviven")
    with Servidor(args, home, traza + ".2") as s:
        lista = json.loads(pedir("/api/chats"))
        ids = [c["id"] for c in lista["chats"]]
        ok(a in ids, "el chat sigue en el registro tras reiniciar", str(ids))
        vivas = [c["sesion_viva"] for c in lista["chats"]]
        ok(not any(vivas),
           "y ninguna sesión se declara viva: el motor acaba de nacer",
           str(vivas))

        pedir(f"/api/chats/{a}/activar", b"")
        r = s.hablar("¿Cómo se llama mi perro? Solo el nombre.")
        turnos = [p for p in s.peticiones() if p.get("type") == "turn"]
        roles = [m["role"] for m in turnos[-1]["messages"]] if turnos else []
        ok("assistant" in roles,
           "hablar reconstruye el contexto desde la transcripción", str(roles))
        ok("byteazul" in r.lower(),
           "y el chat continúa donde estaba", repr(r[:80]))

        print("\n[8] lo cancelado a medias se guarda honestamente")
        # Un turno largo, y se cambia de chat a mitad: lo emitido se conserva.
        c = json.loads(pedir("/api/chats", b"Largo"))["id"]
        pedir(f"/api/chats/{c}/activar", b"")
        antes_txt = len(s.texto_total())
        pedir("/api/chat", b"Escribe un ensayo muy largo sobre la Luna.")
        # Esperar a que HAYA texto visible antes de cambiar. Con un modelo que
        # piensa antes de hablar, dos segundos pueden ser todo razonamiento y
        # entonces no hay nada parcial que conservar: la prueba comprobaría
        # una cosa distinta de la que dice.
        for _ in range(120):
            time.sleep(0.5)
            if len(s.texto_total()) > antes_txt + 20:
                break
        # Activar otro chat con el motor generando: eso ES la pausa. Si no
        # cancelara, el motor seguiría ocupado y el turno siguiente recibiría
        # un 409 — la persona esperando a un chat que ya no mira.
        pedir(f"/api/chats/{a}/activar", b"")
        ok("idle" in pedir("/api/status"),
           "activar otro chat deja el motor libre al momento",
           pedir("/api/status"))
        pedir("/api/chat", b"Di solo: corto.")
        for _ in range(120):
            time.sleep(1)
            if "idle" in pedir("/api/status"):
                break
        ficha = json.loads(pedir(f"/api/chats/{c}"))
        asis = [t for t in ficha["turnos"] if t["rol"] == "assistant"]
        ok(len(asis) == 1 and len(asis[0]["texto"]) > 0,
           "lo que alcanzó a decir queda guardado, no se tira",
           str([len(t['texto']) for t in asis]))
        ok(len(ficha["turnos"]) == 2,
           "y el turno queda representado entero: pregunta y lo que hubo",
           str([t["rol"] for t in ficha["turnos"]]))

        print("\n[9] perfil/sesion/turno llega a la cola de reflexión")
        # Encolar no ejecuta nada: no hay trabajador. Lo que se comprueba es
        # que el job existe, que su identidad es la que toca y que la entrada
        # viene congelada — sin contrato ni razonamiento, que no tienen campo.
        cola = os.path.join(home, "hera_cola.jsonl")
        jobs = []
        if os.path.exists(cola):
            with open(cola, encoding="utf-8") as f:
                jobs = [json.loads(l) for l in f
                        if l.strip() and '"encolado"' in l]
        ok(jobs, "se han encolado turnos", "la cola está vacía")
        ids = [j["job"] for j in jobs]
        ok(all(x.count("/") == 2 for x in ids),
           "cada job es perfil/sesion/turno", str(ids[:3]))
        ok(any(x.split("/")[1] == a for x in ids),
           "y la sesión del job es el chat que hablaba", str(ids[:3]))
        ok(len(set(ids)) == len(ids), "sin ids repetidos", str(ids))
        uno = jobs[0] if jobs else {}
        ok(all(k in uno for k in ("mensaje", "respuesta", "acto",
                                  "evidencia", "perfil_hash")),
           "el job trae la entrada congelada entera", str(sorted(uno))[:120])
        ok(not any("contrato" in k or "razon" in k for k in uno),
           "y ni contrato ni razonamiento: no tienen campo", str(sorted(uno)))
        # El turno cancelado de [8] NO debe haberse encolado.
        ok(not any(x.split("/")[1] == c for x in ids),
           "un turno cancelado no se encola", str(ids))

    shutil.rmtree(raiz, ignore_errors=True)
    print(f"\n{pruebas} pruebas · {fallos} fallos")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
