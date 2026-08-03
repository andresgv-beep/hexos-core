#!/usr/bin/env python3
"""
Barrera del cableado de E3: memoria POR LA RUTA REAL.

No prueba el almacén (eso ya son 59+31 pruebas en C). Prueba lo único que el
almacén no puede probar solo: que la ruta tipada, con un modelo de verdad
cargado, hace lo que dice con la memoria.

Las cuatro condiciones:
  1. El bloque de perfil es EFÍMERO: ni en el diario, ni en la transcripción,
     ni en lo que ve el usuario.
  2. No se reinyecta el perfil en cada turno; cuando cambia una memoria
     confirmada, se RECONSTRUYE el KV (reset + transcripción canónica).
  3. El MemoryDelta se puede ensayar, y sigue sin aplicador.
  4. Reinicio, corrección dentro de una sesión y aislamiento entre perfiles.

uso: ruta_memoria_test.py --model <hnf> --runtime <bin> --serve <bin> --hera <bin>
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

PUERTO = 8123
BASE = f"http://127.0.0.1:{PUERTO}"

fallos, pruebas = 0, 0


def ok(cond, nombre, detalle=""):
    global fallos, pruebas
    pruebas += 1
    if cond:
        print(f"  \033[32m✓\033[0m {nombre}")
    else:
        fallos += 1
        print(f"  \033[31m✗ {nombre}\033[0m — {detalle}")


def pedir(ruta, datos=None, metodo=None):
    req = urllib.request.Request(BASE + ruta, data=datos,
                                 method=metodo or ("POST" if datos else "GET"))
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode("utf-8", "replace")


class Servidor:
    """hexos_serve con la ruta tipada, sobre un perfil concreto."""

    def __init__(self, args, home, traza):
        self.args, self.home, self.traza = args, home, traza
        self.proc = None

    def __enter__(self):
        entorno = dict(os.environ,
                       HELIOS_HOME=self.home,
                       HELIOS_CTX="8192",
                       HELIOS_EMBED_IN_RAM="1",
                       HEXOS_RT_TRACE=self.traza)
        self.proc = subprocess.Popen(
            [self.args.serve, "--model", self.args.model,
             "--runtime", self.args.runtime, "--port", str(PUERTO),
             "--no-probe", "--no-distill"],
            env=entorno, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid)
        for _ in range(120):
            try:
                if "idle" in pedir("/api/status"):
                    return self
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(1)
        raise RuntimeError("el servidor no llegó a idle")

    def __exit__(self, *_):
        if self.proc:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            self.proc.wait(timeout=60)

    def turno(self, texto, espera=120):
        """Manda un mensaje y devuelve la respuesta visible entera."""
        antes = len(self._sse_texto())
        pedir("/api/chat", texto.encode("utf-8"))
        for _ in range(espera):
            time.sleep(1)
            if "idle" in pedir("/api/status"):
                time.sleep(0.5)
                break
        return self._sse_texto()[antes:]

    def _sse_texto(self):
        """Reconstruye lo dicho desde la traza del protocolo (los text_delta).

        Se lee de la traza y no del SSE porque aquí lo que importa es lo que
        pasó por el protocolo, que es donde se pueden comprobar las cuatro
        condiciones."""
        salida = []
        for ev in self.eventos():
            if ev.get("type") == "text_delta":
                salida.append(ev.get("text", ""))
        return "".join(salida)

    def _lineas(self):
        if not os.path.exists(self.traza):
            return []
        with open(self.traza, encoding="utf-8", errors="replace") as f:
            return [json.loads(l) for l in f if l.strip()]

    def peticiones(self):
        return [l["payload"] for l in self._lineas() if l["direction"] == "request"]

    def eventos(self):
        return [l["payload"] for l in self._lineas() if l["direction"] == "event"]


def hera(args, home, *orden):
    r = subprocess.run([args.hera, *orden], env=dict(os.environ, HELIOS_HOME=home),
                       capture_output=True, text=True)
    return r.stdout.strip(), r.returncode


PERFIL_MARCA = "PERFIL DE LA PERSONA ACTUAL"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--runtime", required=True)
    ap.add_argument("--serve", required=True)
    ap.add_argument("--hera", required=True)
    args = ap.parse_args()

    raiz = tempfile.mkdtemp(prefix="e3_ruta_")
    A, B = os.path.join(raiz, "A"), os.path.join(raiz, "B")
    os.makedirs(A); os.makedirs(B)
    tA, tB = os.path.join(raiz, "a.jsonl"), os.path.join(raiz, "b.jsonl")

    # --- Sembrar el perfil A por la MISMA API que usaría cualquiera ---
    u1, _ = hera(args, A, "dijo", "guarda esto: me llamo Andrés")
    hera(args, A, "guarda", "yo/nombre", "Andrés", "Se llama Andrés", u1)
    u2, _ = hera(args, A, "dijo", "guarda esto: mi perro se llama Byteazul")
    hera(args, A, "guarda", "perro/nombre", "Byteazul",
         "Su perro se llama Byteazul", u2)

    print("\n[1] el perfil vigente llega al modelo por la ruta tipada")
    with Servidor(args, A, tA) as s:
        r1 = s.turno("¿cómo me llamo?")
        ok("Andrés" in r1 or "andrés" in r1.lower(),
           "contesta con el nombre confirmado", repr(r1[:120]))

        peticiones = s.peticiones()
        turnos = [p for p in peticiones if p.get("type") == "turn"]
        sistemas = [m["content"] for m in turnos[0]["messages"]
                    if m["role"] == "system"]
        ok(any(PERFIL_MARCA in c for c in sistemas),
           "el perfil entra como system efímero en el primer turno",
           "no se inyectó")
        ok(not any("Girona" in c for c in sistemas),
           "y no arrastra nada sin confirmar", "algo sin confirmar viajó")

        print("\n[2] no se reinyecta el perfil en cada turno")
        s.turno("dime un número del uno al diez y nada más")
        turnos = [p for p in s.peticiones() if p.get("type") == "turn"]
        sis2 = [m["content"] for m in turnos[1]["messages"] if m["role"] == "system"]
        ok(not any(PERFIL_MARCA in c for c in sis2),
           "el segundo turno NO repite el perfil", "se reinyectó")
        ok(not any(p.get("type") == "reset" for p in s.peticiones()),
           "y no ha hecho falta reconstruir el KV", "reconstruyó sin motivo")

        print("\n[3] una corrección EN CALIENTE reconstruye el KV")
        u3, _ = hera(args, A, "dijo", "me equivoqué, el perro se llama Rufo")
        salida, codigo = hera(args, A, "corrige", "perro/nombre", "Rufo",
                              "Su perro se llama Rufo", u3, u3)
        ok(codigo == 0, "la corrección entra en el almacén", salida)

        r3 = s.turno("¿cómo se llama mi perro? responde solo el nombre")
        peticiones = s.peticiones()
        ok(any(p.get("type") == "reset" for p in peticiones),
           "la ruta manda un reset: el KV no se parchea, se tira",
           "no reconstruyó — el hecho viejo sigue físicamente en el KV")

        turnos = [p for p in peticiones if p.get("type") == "turn"]
        ultimo = turnos[-1]
        roles = [m["role"] for m in ultimo["messages"]]
        ok(roles.count("user") > 1 and "assistant" in roles,
           "y rearma el turno con la transcripción canónica", str(roles))
        sis3 = [m["content"] for m in ultimo["messages"] if m["role"] == "system"]
        ok(any("Rufo" in c for c in sis3),
           "con el perfil corregido dentro", "el perfil nuevo no viajó")
        ok(not any("Byteazul" in c for c in sis3),
           "y sin rastro del hecho sustituido", "el hecho corregido sobrevivió")

        canon = [m["content"] for m in ultimo["messages"]
                 if m["role"] in ("user", "assistant")]
        ok(not any(PERFIL_MARCA in c for c in canon),
           "la transcripción canónica no contiene el perfil: es efímero",
           "el perfil se coló en la transcripción")

        ok("Rufo" in r3, "y el modelo ya dice el nombre corregido", repr(r3[:120]))
        ok("Byteazul" not in r3, "sin repetir el viejo", repr(r3[:120]))

        print("\n[4] el MemoryDelta se ensaya y NO se aplica")
        delta = json.dumps({"memory_delta": [
            {"op": "proponer", "clave": "ana/ciudad", "valor": "Bilbao",
             "texto": "Ana vive en Bilbao", "evidencia": u1},
            {"op": "proponer", "clave": "perro/nombre", "valor": "Rufo",
             "texto": "Su perro se llama Rufo", "evidencia": u3},
        ]}).encode("utf-8")
        antes = open(os.path.join(A, "hera.jsonl"), "rb").read()
        res = json.loads(pedir("/api/memoria/ensayo", delta))
        ok(res["aplicado"] is False, "el ensayo se declara como tal", str(res))
        ok(res["ops"][0]["veredicto"] == "sujeto_ajeno",
           "\"Ana vive en Bilbao\" se rechaza también por la ruta",
           str(res["ops"][0]))
        despues = open(os.path.join(A, "hera.jsonl"), "rb").read()
        ok(antes == despues,
           "y el diario no cambia ni un byte: no hay aplicador",
           "el ensayo escribió")

        print("\n[5] el bloque de perfil no vive en ninguna parte permanente")
        diario = open(os.path.join(A, "hera.jsonl"), encoding="utf-8").read()
        ok(PERFIL_MARCA not in diario,
           "el diario no contiene el bloque de perfil", "se guardó")
        visible = s._sse_texto()
        ok(PERFIL_MARCA not in visible,
           "y el usuario nunca lo ve", "se emitió al usuario")

    print("\n[6] reiniciar conserva lo confirmado, por la ruta real")
    with Servidor(args, A, tA + ".2") as s:
        r = s.turno("¿cómo se llama mi perro? responde solo el nombre")
        ok("Rufo" in r, "tras reiniciar el servidor sigue sabiendo el corregido",
           repr(r[:120]))
        ok("Byteazul" not in r, "y el sustituido no vuelve", repr(r[:120]))

    print("\n[7] otro perfil no hereda nada")
    with Servidor(args, B, tB) as s:
        r = s.turno("¿cómo me llamo? si no lo sabes dilo claramente")
        ok("Andrés" not in r and "Byteazul" not in r and "Rufo" not in r,
           "un perfil nuevo no sabe nada del otro", repr(r[:160]))
        turnos = [p for p in s.peticiones() if p.get("type") == "turn"]
        sis = [m["content"] for m in turnos[0]["messages"] if m["role"] == "system"]
        ok(not any(PERFIL_MARCA in c for c in sis),
           "y no se inventa un bloque de perfil vacío", "inyectó perfil sin datos")

    print("\n[8] frontera multiproceso: nadie pisa a nadie")
    C = os.path.join(raiz, "C")
    os.makedirs(C)

    # N procesos `hera dijo` a la vez sobre el mismo diario. Sin cerrojo, dos
    # releen el mismo ultimo id, los dos calculan el siguiente y los dos lo
    # escriben: quedan dos evidencias distintas con el MISMO id, y una
    # correccion que cite ese id se lleva las palabras equivocadas.
    N = 24
    procs = [subprocess.Popen([args.hera, "dijo", f"frase numero {i}"],
                              env=dict(os.environ, HELIOS_HOME=C),
                              stdout=subprocess.PIPE, text=True)
             for i in range(N)]
    ids = [p.communicate()[0].strip() for p in procs]
    ids = [i for i in ids if i]
    ok(len(ids) == N, f"los {N} procesos escriben", f"solo {len(ids)}")
    ok(len(set(ids)) == len(ids), "y ningun id se repite",
       f"{len(ids) - len(set(ids))} ids duplicados")

    diario = os.path.join(C, "hera.jsonl")
    with open(diario, encoding="utf-8") as f:
        lineas = f.readlines()
    ok(all(l.endswith("}\n") for l in lineas),
       "el diario queda entero: ninguna linea partida ni pegada a otra",
       "hay lineas corruptas")
    vistos = set()
    dup = False
    for l in lineas:
        d = json.loads(l)
        if d.get("r") == "dijo":
            if d["id"] in vistos:
                dup = True
            vistos.add(d["id"])
    ok(not dup, "y en disco tampoco hay dos evidencias con el mismo id",
       "el diario tiene ids repetidos")
    ok(len(vistos) == N, f"estan las {N} evidencias", f"hay {len(vistos)}")

    # Dos /api/chat simultaneos: solo uno puede entrar.
    with Servidor(args, C, os.path.join(raiz, "c.jsonl")) as s:
        import threading
        res = []
        def disparar():
            try:
                req = urllib.request.Request(BASE + "/api/chat",
                                             data=b"dime hola y nada mas",
                                             method="POST")
                with urllib.request.urlopen(req, timeout=20) as r:
                    res.append(r.status)
            except urllib.error.HTTPError as e:
                res.append(e.code)
            except Exception:
                res.append(0)
        hilos = [threading.Thread(target=disparar) for _ in range(2)]
        for h in hilos: h.start()
        for h in hilos: h.join()
        ok(sorted(res) == [202, 409],
           "de dos peticiones a la vez, una entra y la otra se rechaza",
           f"respuestas {res}")
        for _ in range(120):
            time.sleep(1)
            if "idle" in pedir("/api/status"):
                break
        turnos = [p for p in s.peticiones() if p.get("type") == "turn"]
        ok(len(turnos) == 1, "y solo se manda UN turno al runtime",
           f"se mandaron {len(turnos)}")

    print(f"\n{pruebas} pruebas · {fallos} fallos")
    shutil.rmtree(raiz, ignore_errors=True)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
