#!/usr/bin/env python3
"""
Relevo text → coder → text en el mismo turno. EXPERIMENTO, no producto.

La pregunta que responde no es "¿escribe buen código?" —eso ya se sabe— sino
**¿el relevo se siente natural o es torpe?**. Y la responde en el PEOR CASO:
mata el proceso y arranca el otro, que son ~2,15 s medidos. Un `unload_block`
bien hecho costaría ~430 ms. Si a 2,15 s ya resulta cómodo, con 430 ms sobra;
si a 2,15 s cansa, ya sabes cuánto hay que bajar.

No toca Héctor ni HexOS: habla el protocolo tipado que ya existe.

LO QUE MIDE, y es lo que decide si hace falta la arena de KV:
  · cuánto cuesta el relevo de ida y de vuelta
  · cuánto cuesta que `text` RECUPERE el hilo — al morir, su KV muere, así que
    al volver hay que re-prefillear la conversación entera. Ese número es
    exactamente lo que ahorraría evacuar el KV a RAM.

uso:
  relevo_test.py --text <text.hnf> --coder <coder.hnf> [--runtime <bin>]
"""

import argparse
import json
import os
import subprocess
import sys
import time

RUNTIME = "/home/andres/Documentos/GitHub/Hector-engine/build/helios_runtime"

# Señales de que la petición es de código. Deliberadamente tonto: el
# experimento es sobre el relevo, no sobre el enrutado. Para decidirlo bien
# ya está el CK, que tiene el acto `implementar`.
PISTAS = ("código", "codigo", "script", "función", "funcion", "implementa",
          "escribe en python", "en c++", "en rust", "programa", "clase ",
          "algoritmo", "refactoriza", "arregla el bug")


def vram_libre_mib():
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.free",
                            "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=5)
        return int(r.stdout.strip().split("\n")[0])
    except Exception:
        return 999999


def esperar_vram_libre(minimo=5500, espera=40):
    t0 = time.monotonic()
    while time.monotonic() - t0 < espera:
        if vram_libre_mib() >= minimo:
            return True
        time.sleep(0.5)
    return False


class Motor:
    """Un helios_runtime hablando el protocolo tipado."""

    def __init__(self, hnf, ctx="8192", etiqueta=""):
        self.hnf, self.ctx, self.etiqueta = hnf, ctx, etiqueta
        self.p = None
        self.seq = 0

    def arrancar(self):
        # El motor que acaba de morir puede seguir soltando su contexto CUDA
        # unos segundos. Arrancar el siguiente sin esperar hace que compita por
        # una VRAM que todavía no está libre y muera al cargar. Ayer me pasó
        # exactamente lo mismo con la reflexión; aquí no lo apliqué.
        esperar_vram_libre()

        t0 = time.monotonic()
        self.p = subprocess.Popen(
            [RUNTIME, "--model", self.hnf, "--ctx", self.ctx, "--temp", "0.7"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
            env=dict(os.environ, HELIOS_EMBED_IN_RAM="1"))
        while True:
            l = self.p.stdout.readline()
            if not l:
                # Contar POR QUÉ murió, no solo que murió.
                err = (self.p.stderr.read() or "").strip().splitlines()
                cola = "\n  ".join(err[-6:]) if err else "(sin mensaje)"
                raise RuntimeError(
                    f"{self.etiqueta} murió al cargar {self.hnf}:\n  {cola}")
            d = json.loads(l)
            if d.get("type") == "ready":
                return time.monotonic() - t0

    def parar(self):
        if not self.p:
            return 0.0
        t0 = time.monotonic()
        try:
            self.p.stdin.write('{"type":"shutdown","request_id":"q"}\n')
            self.p.stdin.flush()
            self.p.wait(timeout=30)
        except Exception:
            self.p.kill()
        self.p = None
        return time.monotonic() - t0

    def turno(self, mensajes, max_vis=400, max_think=0, temp=0.7, mostrar=True):
        """Manda mensajes y devuelve (texto, segundos)."""
        self.seq += 1
        rid = f"r{self.seq}"
        self.p.stdin.write(json.dumps({
            "type": "turn", "request_id": rid, "messages": mensajes,
            "generation": {"temperature": temp,
                           "max_visible_tokens": max_vis,
                           "max_thinking_tokens": max_think}}) + "\n")
        self.p.stdin.flush()

        t0 = time.monotonic()
        salida = []
        while True:
            l = self.p.stdout.readline()
            if not l:
                break
            d = json.loads(l)
            if d.get("type") == "text_delta" and d.get("request_id") == rid:
                t = d.get("text", "")
                salida.append(t)
                if mostrar:
                    sys.stdout.write(t)
                    sys.stdout.flush()
            elif d.get("type") in ("completed", "error") and d.get("request_id") == rid:
                break
        return "".join(salida), time.monotonic() - t0


def es_codigo(texto):
    b = texto.lower()
    return any(p in b for p in PISTAS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--coder", required=True)
    ap.add_argument("--runtime", default=RUNTIME)
    args = ap.parse_args()
    globals()["RUNTIME"] = args.runtime

    # Transcripción canónica en texto plano, como hace HexOS. Es lo que
    # permite que `text` recupere el hilo tras morir: los tokenizadores de los
    # dos modelos pueden ser distintos, el texto no.
    transcripcion = []
    tiempos = []

    text = Motor(args.text, etiqueta="text")
    print("\033[90mcargando text…\033[0m", end=" ", flush=True)
    t = text.arrancar()
    print(f"\033[90m{t:.2f}s\033[0m\n")
    coder = None

    print("Escribe. Ctrl-D para salir. Pide código para ver el relevo.\n")
    try:
        while True:
            try:
                msg = input("\033[1mTÚ ›\033[0m ").strip()
            except EOFError:
                break
            if not msg:
                continue

            # --- 1. text contesta, siempre ---
            print("\033[36mTEXT ›\033[0m ", end="", flush=True)
            respuesta, dt = text.turno(
                transcripcion + [{"role": "user", "content": msg}],
                max_vis=220, max_think=600)
            print(f"\n\033[90m  [{dt:.1f}s]\033[0m")
            transcripcion.append({"role": "user", "content": msg})
            transcripcion.append({"role": "assistant", "content": respuesta})

            if not es_codigo(msg):
                continue

            # --- 2. relevo: fuera text, entra coder ---
            print("\033[33m  ⟳ pensando… creando código…\033[0m", flush=True)
            t_ida = time.monotonic()
            text.parar()
            if coder is None:
                coder = Motor(args.coder, etiqueta="coder")
            coder.arrancar()
            ida = time.monotonic() - t_ida

            # El coder NO hereda la conversación: recibe un encargo limpio.
            # Su tokenizador y su KV son suyos.
            print("\033[32mCODER ›\033[0m ", end="", flush=True)
            codigo, dt_code = coder.turno([
                {"role": "system",
                 "content": "Eres un programador. Respondes solo con código, "
                            "sin explicaciones alrededor."},
                {"role": "user", "content": msg}],
                max_vis=600, max_think=0, temp=0.2)
            print()

            # --- 3. vuelta: fuera coder, entra text con su hilo ---
            t_vuelta = time.monotonic()
            coder.parar()
            text.arrancar()
            # Aquí está el coste que la arena de KV eliminaría: re-prefillear
            # toda la conversación porque el KV murió con el proceso.
            _, dt_reprefill = text.turno(
                transcripcion + [{"role": "user",
                                  "content": "(el código ya está escrito, "
                                             "responde solo: listo)"}],
                max_vis=12, max_think=0, mostrar=False)
            vuelta = time.monotonic() - t_vuelta

            tiempos.append((ida, dt_code, vuelta, dt_reprefill))
            print(f"\033[90m  ida {ida:.2f}s · código {dt_code:.1f}s · "
                  f"vuelta {vuelta:.2f}s (de los cuales {dt_reprefill:.2f}s "
                  f"son recuperar el hilo)\033[0m\n")
    finally:
        text.parar()
        if coder:
            coder.parar()

    if tiempos:
        n = len(tiempos)
        mi = sum(t[0] for t in tiempos) / n
        mv = sum(t[2] for t in tiempos) / n
        mr = sum(t[3] for t in tiempos) / n
        print(f"\n\033[1m{n} relevos\033[0m")
        print(f"  ida (matar text + cargar coder):   {mi:.2f}s")
        print(f"  vuelta (matar coder + cargar text): {mv:.2f}s")
        print(f"    de los cuales recuperar el hilo:  {mr:.2f}s  ← "
              f"esto es lo que ahorraría evacuar el KV a RAM")
        print(f"  sobrecoste total por petición:      {mi + mv:.2f}s")


if __name__ == "__main__":
    sys.exit(main())
