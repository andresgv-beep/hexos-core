#!/usr/bin/env python3
"""
Conmutación entre chats contra `helios_runtime` de verdad.

Lo que hay que demostrar:
  · varias sesiones sobre UNOS MISMOS pesos (un solo proceso, una sola carga),
  · pausar conserva KV, muestreador y posición — no reinicia ni reconstruye,
  · cambiar de chat cancela lo que hubiera en vuelo, sin romper nada,
  · una sesión pausada no ejecuta nada,
  · el protocolo viejo, sin campo `session`, sigue valiendo palabra por palabra.

uso: sesiones_runtime_test.py --model <hnf> --runtime <bin>
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time

fallos = pruebas = 0


def ok(cond, nombre, detalle=""):
    global fallos, pruebas
    pruebas += 1
    if cond:
        print(f"  \033[32m✓\033[0m {nombre}")
    else:
        fallos += 1
        print(f"  \033[31m✗ {nombre}\033[0m — {detalle}")


class Runtime:
    """Habla el protocolo tipado por tuberías, como HexOS."""

    def __init__(self, binario, modelo, ctx="4096"):
        self.p = subprocess.Popen(
            [binario, "--model", modelo, "--ctx", ctx, "--temp", "0.0"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
            env=dict(os.environ, HELIOS_EMBED_IN_RAM="1"))
        self.eventos = []
        self._lock = threading.Lock()
        threading.Thread(target=self._leer, daemon=True).start()

    def _leer(self):
        for linea in self.p.stdout:
            linea = linea.strip()
            if not linea:
                continue
            try:
                ev = json.loads(linea)
            except json.JSONDecodeError:
                continue
            with self._lock:
                self.eventos.append(ev)

    def esperar(self, tipo, desde=0, timeout=180):
        t0 = time.time()
        while time.time() - t0 < timeout:
            with self._lock:
                for i, ev in enumerate(self.eventos[desde:], start=desde):
                    if ev.get("type") == tipo:
                        return i, ev
            time.sleep(0.05)
        return None, None

    def n(self):
        with self._lock:
            return len(self.eventos)

    def mandar(self, obj):
        self.p.stdin.write(json.dumps(obj) + "\n")
        self.p.stdin.flush()

    def turno(self, texto, session=None, rid=None, max_vis=64, esperar=True):
        rid = rid or f"r{int(time.time()*1000) % 100000}{len(self.eventos)}"
        msg = {"type": "turn", "request_id": rid,
               "messages": [{"role": "user", "content": texto}],
               "generation": {"max_visible_tokens": max_vis,
                              "max_thinking_tokens": 0, "temperature": 0.0}}
        if session is not None:
            msg["session"] = session
        desde = self.n()
        self.mandar(msg)
        if not esperar:
            return rid, desde
        self._fin(rid)
        return rid, desde

    def _fin(self, rid, timeout=180):
        t0 = time.time()
        while time.time() - t0 < timeout:
            with self._lock:
                for ev in self.eventos:
                    if (ev.get("request_id") == rid and
                            ev.get("type") in ("completed", "error")):
                        return ev
            time.sleep(0.05)
        return None

    def texto(self, rid):
        with self._lock:
            return "".join(e.get("text", "") for e in self.eventos
                           if e.get("type") == "text_delta"
                           and e.get("request_id") == rid)

    def posicion(self, rid):
        with self._lock:
            for e in reversed(self.eventos):
                if e.get("request_id") == rid and e.get("type") == "completed":
                    return e.get("model_state", {}).get("cache_position")
        return None

    def cerrar(self):
        try:
            self.mandar({"type": "shutdown", "request_id": "q"})
            self.p.wait(timeout=30)
        except Exception:
            self.p.kill()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--runtime", required=True)
    args = ap.parse_args()

    rt = Runtime(args.runtime, args.model)
    _, listo = rt.esperar("ready")
    if not listo:
        print("el runtime no arrancó")
        return 1

    try:
        print("\n[1] varias sesiones, una sola carga de pesos")
        rid_a, _ = rt.turno("Recuerda: mi perro se llama Byteazul. Di solo: vale.",
                            session="chatA")
        rid_b, _ = rt.turno("Recuerda: mi gato se llama Nube. Di solo: vale.",
                            session="chatB")
        ok(rt.esperar("session_opened")[1] is not None,
           "el runtime abre sesiones bajo demanda", "no anunció ninguna")
        ok(rt.posicion(rid_a) is not None and rt.posicion(rid_b) is not None,
           "las dos han generado", "alguna no terminó")

        print("\n[2] cada chat recuerda lo suyo y solo lo suyo")
        ra, _ = rt.turno("¿Cómo se llama mi perro? Solo el nombre.", session="chatA")
        ta = rt.texto(ra)
        ok("byteazul" in ta.lower(), "A recuerda lo de A", repr(ta[:80]))
        ok("nube" not in ta.lower(), "y no se le ha pegado nada de B", repr(ta[:80]))

        rb, _ = rt.turno("¿Cómo se llama mi gato? Solo el nombre.", session="chatB")
        tb = rt.texto(rb)
        ok("nube" in tb.lower(), "B recuerda lo de B", repr(tb[:80]))
        ok("byteazul" not in tb.lower(), "y tampoco al revés", repr(tb[:80]))

        print("\n[3] pausar conserva el KV: no reinicia ni reconstruye")
        pos_a = rt.posicion(ra)
        # Se usa B a fondo, que es lo que pasa al cambiar de chat y volver.
        rt.turno("Escribe un párrafo largo sobre volcanes.", session="chatB",
                 max_vis=150)
        ra2, _ = rt.turno("¿Y cómo se llamaba? Solo el nombre.", session="chatA")
        ok(rt.posicion(ra2) > pos_a,
           "al volver a A su caché SIGUE donde estaba y avanza desde ahí",
           f"{rt.posicion(ra2)} <= {pos_a}")
        ok("byteazul" in rt.texto(ra2).lower(),
           "y sigue la conversación, no la empieza de cero",
           repr(rt.texto(ra2)[:80]))

        print("\n[4] cambiar de chat cancela lo que hubiera en vuelo")
        desde = rt.n()
        # Un turno largo en A, y sin esperar, otro en B: eso es abrir otro chat.
        rid_largo, _ = rt.turno("Escribe un ensayo muy largo sobre la Luna.",
                                session="chatA", max_vis=400, esperar=False)
        time.sleep(1.5)
        rid_corto, _ = rt.turno("Di solo: hola.", session="chatB")
        rt._fin(rid_largo)

        _, pausa = rt.esperar("session_paused", desde=desde, timeout=30)
        ok(pausa is not None and pausa.get("session") == "chatA",
           "el runtime anuncia que pausó el chat que generaba",
           str(pausa))
        # Que lo anuncie no basta: el turno largo tiene que haber PARADO por la
        # conmutación. Sin esto, la prueba pasaría igual si simplemente se
        # hubiera terminado solo antes de que llegara el otro.
        fin = rt._fin(rid_largo)
        razon = (fin or {}).get("finish_reason")
        ok(razon == "cancelled",
           "y el turno largo termina CANCELADO, no por haber acabado solo",
           f"finish_reason={razon}")
        ok("hola" in rt.texto(rid_corto).lower(),
           "y el chat nuevo contesta igual", repr(rt.texto(rid_corto)[:80]))

        print("\n[5] lo cancelado se conserva: pausar no destruye")
        parcial = rt.texto(rid_largo)
        ok(len(parcial) > 0,
           "lo que A alcanzó a decir no se tira", "se perdió lo emitido")
        ra3, _ = rt.turno("Di solo: sigo.", session="chatA")
        ok("sigo" in rt.texto(ra3).lower(),
           "y A sigue viva y usable tras la pausa", repr(rt.texto(ra3)[:80]))
        ok(rt.posicion(ra3) is not None and rt.posicion(ra3) > 0,
           "con su caché intacto", "el caché se fue a cero")

        print("\n[6] una sesión pausada no ejecuta nada")
        desde = rt.n()
        rid_b6, _ = rt.turno("Di solo: uno.", session="chatB")
        with rt._lock:
            ajenos = [e for e in rt.eventos[desde:]
                      if e.get("type") in ("text_delta", "prefill", "thinking")
                      and e.get("request_id") != rid_b6]
        # Se compara contra el id REAL del turno de B. La versión anterior
        # filtraba por un prefijo que ningún id tenía, así que la lista salía
        # vacía siempre y la prueba pasaba sin mirar nada.
        ok(not ajenos,
           "mientras habla B, ninguna otra sesión emite un solo evento",
           str(ajenos[:2]))

        print("\n[7] el protocolo viejo sigue valiendo")
        rv, _ = rt.turno("Di solo: compatible.")     # sin campo `session`
        ok("compatible" in rt.texto(rv).lower(),
           "un turno sin `session` va a la sesión por defecto",
           repr(rt.texto(rv)[:80]))
        ok(rt.posicion(rv) is not None, "y termina normal", "no terminó")

        print("\n[8] cerrar un chat libera su sesión")
        rt.mandar({"type": "session_close", "request_id": "x1", "session": "chatB"})
        _, cerrado = rt.esperar("session_closed", timeout=30)
        ok(cerrado is not None and cerrado.get("session") == "chatB",
           "el runtime confirma el cierre", str(cerrado))
        rn, _ = rt.turno("¿Cómo se llama mi gato? Solo el nombre.", session="chatB")
        ok("nube" not in rt.texto(rn).lower(),
           "y reabrirlo empieza en blanco: no resucita el KV viejo",
           repr(rt.texto(rn)[:80]))
    finally:
        rt.cerrar()

    print(f"\n{pruebas} pruebas · {fallos} fallos")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
