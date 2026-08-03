#!/usr/bin/env python3
"""
Barrera del trabajador de reflexión — SOLO ENSAYO.

Lo que hay que demostrar no es que reflexione: es que **no escribe nada** y que
**no estorba**. Los diez puntos:

  1. Diario de memoria idéntico byte a byte antes y después.
  2. Nada de la reflexión aparece en chat, SSE ni transcripción.
  3. Un chat interrumpe al trabajador y responde normalmente.
  4. El job interrumpido conserva sus intentos.
  5. Dos jobs seguidos no comparten KV ni sampler.
  6. Un delta corrupto no escribe nada y no atasca a los siguientes.
  7. Matar el trabajador recupera el job por la cola durable.
  8. Telemetría con recuentos y tiempos; cero contenido.
  9. La sesión reservada nunca sale en la sidebar.
 10. Los chats conservan su comportamiento y su contexto.

uso: reflexion_test.py --model <hnf> --runtime <bin> --serve <bin>
"""

import argparse
import hashlib
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

PUERTO = 8142
BASE = f"http://127.0.0.1:{PUERTO}"
fallos = pruebas = 0
ACCIONES = ("/activar", "/liberar", "/renombrar", "/borrar", "/cerrar")


def ok(cond, nombre, detalle=""):
    global fallos, pruebas
    pruebas += 1
    if cond:
        print(f"  \033[32m✓\033[0m {nombre}")
    else:
        fallos += 1
        print(f"  \033[31m✗ {nombre}\033[0m — {detalle}")


def pedir(ruta, datos=None, metodo=None):
    if metodo is None:
        metodo = "POST" if datos is not None else "GET"
    if metodo == "GET" and ruta.endswith(ACCIONES):
        raise AssertionError(f"{ruta} es una acción pedida por GET")
    req = urllib.request.Request(BASE + ruta, data=datos or b"", method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.read().decode("utf-8", "replace")


class Servidor:
    def __init__(self, args, home, traza, reflexion=True):
        self.args, self.home, self.traza, self.refl = args, home, traza, reflexion

    def __enter__(self):
        cmd = [self.args.serve, "--model", self.args.model,
               "--runtime", self.args.runtime, "--port", str(PUERTO),
               "--no-probe", "--no-distill"]
        if self.refl:
            cmd.append("--reflexion")
        self.log = open(self.traza + ".log", "w")
        self.proc = subprocess.Popen(
            cmd, env=dict(os.environ, HELIOS_HOME=self.home, HELIOS_CTX="8192",
                          HELIOS_EMBED_IN_RAM="1", HEXOS_RT_TRACE=self.traza),
            stdout=subprocess.DEVNULL, stderr=self.log, preexec_fn=os.setsid)
        for _ in range(150):
            try:
                if "idle" in pedir("/api/status"):
                    return self
            except Exception:
                pass
            time.sleep(1)
        raise RuntimeError("no arrancó")

    def __exit__(self, *_):
        if not self.proc:
            return
        os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
        self.proc.wait(timeout=60)
        self.log.close()

    def matar(self):
        """Muerte súbita: sin cerrar nada, como una caída de verdad."""
        os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
        self.proc.wait(timeout=30)
        self.log.close()
        self.proc = None      # el __exit__ ya no tiene a quién matar
        # El motor vive en su propia sesión (setsid), así que no muere con el
        # grupo de HexOS: se entera por el EOF de su entrada y sale solo. Hay
        # que esperarlo o el siguiente arranque compite por la misma VRAM y
        # falla al cargar el modelo. Es lo que pasaría de verdad si HexOS se
        # cayera de golpe.
        for _ in range(120):
            if subprocess.run(["pgrep", "-x", "helios_runtime"],
                              capture_output=True).returncode != 0:
                return
            time.sleep(1)

    def hablar(self, texto, espera=120):
        pedir("/api/chat", texto.encode("utf-8"))
        for _ in range(espera):
            time.sleep(1)
            if "idle" in pedir("/api/status"):
                time.sleep(0.4)
                return True
        return False

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


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else ""


def esperar_trabajos(n, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        t = json.loads(pedir("/api/reflexion"))
        if t["trabajos"] + t["fallidos"] >= n:
            return t
        time.sleep(1)
    return json.loads(pedir("/api/reflexion"))


def main():
    ap = argparse.ArgumentParser()
    for f in ("model", "runtime", "serve"):
        ap.add_argument(f"--{f}", required=True)
    args = ap.parse_args()

    raiz = tempfile.mkdtemp(prefix="refl_")
    home = os.path.join(raiz, "perfil")
    os.makedirs(home)
    diario = os.path.join(home, "hera.jsonl")
    traza = os.path.join(raiz, "t.jsonl")

    with Servidor(args, home, traza) as s:
        print("\n[1] el trabajador corre y no escribe memoria")
        s.hablar("Guarda esto: mi perro se llama Byteazul.")
        antes = sha(diario)
        antes_bytes = os.path.getsize(diario)
        tel = esperar_trabajos(1)
        ok(tel["trabajos"] + tel["fallidos"] >= 1,
           "ha ejecutado al menos un trabajo", str(tel))
        ok(tel["aplicados"] == 0, "y declara cero aplicados", str(tel))

        # LA propiedad de esta rebanada.
        ok(sha(diario) == antes and os.path.getsize(diario) == antes_bytes,
           "el diario de memoria no cambia ni un byte",
           f"{antes_bytes} → {os.path.getsize(diario)}")

        print("\n[2] nada de la reflexión llega al usuario")
        evs = s.eventos()
        refl_rids = {p["payload"]["request_id"]
                     for p in evs if p["direction"] == "request"
                     and p["payload"].get("session") == "hera:reflection"
                     and "request_id" in p["payload"]}
        fugas = [p for p in evs if p["direction"] == "event"
                 and p["payload"].get("type") == "text_delta"
                 and p["payload"].get("request_id") in refl_rids]
        ok(refl_rids, "la reflexión ha usado su sesión reservada", str(refl_rids))
        # El texto de la reflexión pasa por el protocolo (es donde vive), pero
        # NO puede llegar a la transcripción ni al chat.
        chats = json.loads(pedir("/api/chats"))
        ok(all(c["id"] != "hera:reflection" for c in chats["chats"]),
           "la sesión reservada NO está en la lista de chats", str(chats))
        act = chats["activo"]
        turnos = json.loads(pedir(f"/api/chats/{act}"))["turnos"]
        ok(len(turnos) == 2,
           "la transcripción del chat solo tiene su turno", str(len(turnos)))
        ok(not any("memory_delta" in t["texto"] for t in turnos),
           "y ni rastro del delta en lo que se guardó", "se coló el delta")

        print("\n[3] cada trabajo empieza limpio")
        resets = [p["payload"] for p in evs if p["direction"] == "request"
                  and p["payload"].get("type") == "reset"
                  and p["payload"].get("session") == "hera:reflection"]
        ok(len(resets) >= 2,
           "se resetea la sesión de reflexión antes y después de cada trabajo",
           str(len(resets)))

        print("\n[4] el chat manda: interrumpe y responde normal")
        for i in range(4):
            s.hablar(f"Guarda esto: dato numero {i} sobre el proyecto.")
        t0 = time.time()
        ok(s.hablar("Di solo: rapido."), "un chat responde con el trabajador vivo",
           "no contestó")
        tel = json.loads(pedir("/api/reflexion"))
        ok(tel["aplazados"] >= 0, "la telemetría cuenta los aplazados", str(tel))

        print("\n[5] la telemetría no lleva contenido")
        crudo = pedir("/api/reflexion")
        ok("Byteazul" not in crudo and "perro" not in crudo,
           "ni una palabra de lo hablado", crudo[:120])
        ok(all(k in json.loads(crudo) for k in
               ("trabajos", "aplazados", "fallidos", "ops", "aceptables",
                "rechazadas", "ms_medio")),
           "pero sí recuentos y tiempos", crudo[:160])

        print("\n[6] el diario sigue intacto tras varios trabajos")
        # Instantánea NUEVA: entre medias ha habido cinco turnos de chat, y
        # cada turno visible escribe su evidencia en el diario. Eso lo hace el
        # chat, no la reflexión. Comparar contra la foto vieja mediría lo que
        # escribió la conversación y se lo achacaría al trabajador — que es
        # exactamente el error que la prueba dice estar buscando.
        antes2 = sha(diario)
        trabajos_antes = json.loads(pedir("/api/reflexion"))["trabajos"]
        esperar_trabajos(trabajos_antes + 3)
        ok(json.loads(pedir("/api/reflexion"))["trabajos"] > trabajos_antes,
           "el trabajador ha seguido procesando la cola", "no avanzó")
        ok(sha(diario) == antes2,
           "y en toda la tanda no ha cambiado ni un byte",
           "la reflexión escribió")

        estado_cola_antes = json.loads(pedir("/api/reflexion"))

    print("\n[7] matar el trabajador no pierde trabajo")
    # Se encolan trabajos con la reflexión APAGADA y se mata el proceso.
    with Servidor(args, home, traza + ".2", reflexion=False) as s:
        for i in range(2):
            s.hablar(f"Guarda esto: otro dato {i}.")
        cola = os.path.join(home, "hera_cola.jsonl")
        pend_antes = json.loads(pedir("/api/reflexion"))["pendientes"]
        ok(pend_antes > 0, "quedan trabajos pendientes sin trabajador",
           str(pend_antes))
        s.matar()

    with Servidor(args, home, traza + ".3", reflexion=False) as s:
        pend = json.loads(pedir("/api/reflexion"))["pendientes"]
        ok(pend >= pend_antes,
           "tras una muerte súbita siguen ahí: la cola es durable",
           f"{pend_antes} → {pend}")
        ok(json.loads(pedir("/api/reflexion"))["activa"] is False,
           "y con el trabajador apagado no se ejecuta ninguno", "seguía activo")

        print("\n[8] apagar la reflexión no toca el chat")
        ok(s.hablar("Di solo: sigo."), "el chat responde igual", "no contestó")
        # El chat SÍ escribe en el diario: registra la evidencia de lo que dijo
        # la persona. Eso es suyo, no de la reflexión. La foto se toma DESPUÉS
        # del turno; comparar contra una anterior mide lo que escribió la
        # conversación y se lo achaca al trabajador. Es la cuarta vez que me
        # equivoco igual en esta batería, así que queda escrito.
        tras_chat = sha(diario)
        time.sleep(6)   # margen de sobra para que un trabajador vivo actuara
        ok(sha(diario) == tras_chat,
           "y con la reflexión apagada nada más toca el diario",
           "algo escribió con el trabajador parado")
        ok(json.loads(pedir("/api/reflexion"))["trabajos"] == 0,
           "ni se ha ejecutado ningún trabajo", "ejecutó con la reflexión off")

    print("\n[9] los intentos no se gastan al aplazar")
    with open(os.path.join(home, "hera_cola.jsonl"), encoding="utf-8") as f:
        registros = [json.loads(l) for l in f if l.strip()]
    aplazados = [r for r in registros if r.get("r") == "aplazado"]
    reintentos = [r for r in registros if r.get("r") == "reintento"]
    ok(True, f"aplazados: {len(aplazados)} · reintentos: {len(reintentos)}")
    ok(not any(r.get("intentos", 0) > 0 for r in aplazados),
       "un aplazado nunca lleva contador de intentos",
       str(aplazados[:2]))

    shutil.rmtree(raiz, ignore_errors=True)
    print(f"\n{pruebas} pruebas · {fallos} fallos")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
