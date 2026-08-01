#!/usr/bin/env python3
"""
Mide DÓNDE se degrada una conversación con Héctor.

Sin esto, "se pone raro a partir de un rato" es una opinión y no se puede
comparar un arreglo con otro. El guion de turnos es fijo, así que dos
ejecuciones son comparables aunque el modelo no sea determinista.

Habla por el puente HTTP de HEXOS (hexos_serve), así que no toca el motor ni
necesita compilar nada.

    ./hexos/bin/hexos_serve --model <hnf> --engine <helios_chat> --no-distill
    python3 tools/medir_conversacion.py --turnos 30

Señales por turno, todas objetivas:

  chino    caracteres CJK (Qwen3 es un modelo chino: al degradarse tira de
           tokens chinos, así que esto es el canario)
  bucle    frases repetidas dentro de la respuesta, más respuestas idénticas
           a otra anterior
  mudo     el turno no produjo ni una letra visible
  fuga     la respuesta empieza con el cierre de pensamiento como texto
  ctx      posición en el contexto al terminar el turno

IMPORTANTE: usar --no-distill al arrancar el servidor. Si no, cada ejecución
de esta medida deja un recuerdo basura en el diario de Héctor.
"""

import argparse
import json
import re
import sys
import threading
import urllib.request

# Guion fijo: mezcla de trivial y sustancioso, como una conversación de
# verdad. Los turnos triviales importan porque son los que más se degradan
# (poco presupuesto de pensamiento) y los que un banco "serio" olvidaría.
GUION = [
    "hola, ¿qué tal?",
    "¿en qué estás trabajando?",
    "explícame en dos frases qué es la cuantización de un modelo",
    "¿y por qué se pierde calidad al cuantizar?",
    "vale",
    "ahora cuéntame algo de ti",
    "¿te acuerdas de lo que te pregunté al principio?",
    "¿cuál es la diferencia entre memoria RAM y VRAM?",
    "jajaja",
    "escribe una función en Python que calcule el factorial",
    "¿y de forma iterativa?",
    "gracias",
    "¿qué opinas de medir antes de optimizar?",
    "dame un ejemplo concreto",
    "ya",
    "¿cuántas capas tiene un modelo de 4 mil millones de parámetros?",
    "interesante",
    "¿me repites la primera cosa que te dije?",
    "¿qué es un kernel de CUDA?",
    "vale, y ¿qué es la memoria compartida en una GPU?",
    "hmm",
    "resume en una frase todo lo que hemos hablado",
    "¿sigues ahí?",
    "escribe un haiku sobre la ingeniería",
    "otro",
    "¿te cansas de responder?",
    "¿cuál fue la función de Python que escribiste antes?",
    "explícame qué es un cuello de botella de ancho de banda",
    "todo bien?",
    "última pregunta: ¿de qué hemos hablado hoy?",
]

CJK = re.compile(r'[一-鿿぀-ヿ]')
STATS = re.compile(r'\[([^\]]*(?:tok|ctx)[^\]]*)\]\s*$')
CTX = re.compile(r'ctx\s+(\d+)\s*/\s*(\d+)')
TPS = re.compile(r'([\d.]+)\s*tok/s')
PENSANDO = re.compile(r'\(pensando[^)]*\)')


class Puente:
    """Cliente del puente: abre el SSE en un hilo y acumula por turno."""

    def __init__(self, base):
        self.base = base
        self.buf = []
        self.fin = threading.Event()
        self.vivo = True
        self.hilo = threading.Thread(target=self._escuchar, daemon=True)
        self.hilo.start()

    def _escuchar(self):
        try:
            r = urllib.request.urlopen(self.base + '/api/events', timeout=None)
        except Exception as e:
            print(f'no pude conectar con {self.base}: {e}', file=sys.stderr)
            self.vivo = False
            self.fin.set()
            return
        for linea in r:
            linea = linea.decode('utf-8', 'replace').rstrip('\n')
            if linea.startswith('data: {"t"'):
                try:
                    self.buf.append(json.loads(linea[6:])['t'])
                except Exception:
                    pass
            elif linea.startswith('event: end'):
                self.fin.set()
            elif linea.startswith('event: dead'):
                self.vivo = False
                self.fin.set()

    def turno(self, texto, espera=180):
        self.buf.clear()
        self.fin.clear()
        req = urllib.request.Request(
            self.base + '/api/chat', data=texto.encode('utf-8'),
            headers={'Content-Type': 'text/plain; charset=utf-8'})
        with urllib.request.urlopen(req) as r:
            if r.status != 202:
                return None
        if not self.fin.wait(espera):
            return None
        return ''.join(self.buf)


def analizar(crudo, previas):
    """Separa telemetría de texto y saca las señales objetivas."""
    m = STATS.search(crudo.strip())
    stats = m.group(1) if m else ''
    texto = crudo[:m.start()] if m else crudo
    texto = PENSANDO.sub('', texto).strip()
    fuga = texto.startswith('</think>')
    texto = re.sub(r'^</think>\s*', '', texto)

    frases = [f.strip().lower() for f in re.split(r'[.!?\n]', texto)
              if len(f.strip()) > 15]
    bucle = len(frases) - len(set(frases))
    if texto and texto in previas:
        bucle += 5          # repetir un turno entero es mucho peor que una frase

    ctx = CTX.search(stats)
    tps = TPS.search(stats)
    return {
        'texto': texto,
        'chars': len(texto),
        'chino': len(CJK.findall(texto)),
        'bucle': bucle,
        'mudo': len(texto) == 0,
        'fuga': fuga,
        'ctx': int(ctx.group(1)) if ctx else 0,
        'ventana': int(ctx.group(2)) if ctx else 0,
        'tps': float(tps.group(1)) if tps else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='http://localhost:8080')
    ap.add_argument('--turnos', type=int, default=len(GUION))
    ap.add_argument('--json', help='volcar el detalle a un fichero')
    args = ap.parse_args()

    p = Puente(args.host)
    print(f'{"#":>3} {"ctx":>10}  {"chars":>5} {"chino":>5} {"bucle":>5} '
          f'{"mudo":>4} {"fuga":>4}  muestra')
    print('-' * 88)

    filas, previas = [], []
    primera_mala = None
    for i in range(args.turnos):
        pregunta = GUION[i % len(GUION)]
        crudo = p.turno(pregunta)
        if crudo is None:
            print(f'{i+1:>3}  (sin respuesta: el motor no contestó o murió)')
            break
        r = analizar(crudo, previas)
        previas.append(r['texto'])
        r['turno'] = i + 1
        r['pregunta'] = pregunta
        filas.append(r)

        malo = r['chino'] > 0 or r['bucle'] > 0 or r['mudo'] or r['fuga']
        if malo and primera_mala is None:
            primera_mala = r
        pct = (100 * r['ctx'] // r['ventana']) if r['ventana'] else 0
        print(f'{r["turno"]:>3} {r["ctx"]:>6}/{pct:>3}% {r["chars"]:>5} '
              f'{r["chino"]:>5} {r["bucle"]:>5} {"sí" if r["mudo"] else "":>4} '
              f'{"sí" if r["fuga"] else "":>4}  {r["texto"][:34]!r}')

        if not p.vivo:
            print('el motor murió')
            break

    print()
    if not filas:
        print('sin datos')
        return 1

    malos = [f for f in filas if f['chino'] or f['bucle'] or f['mudo'] or f['fuga']]
    print(f'turnos: {len(filas)}   con alguna señal: {len(malos)} '
          f'({100*len(malos)//len(filas)}%)')
    print(f'chino total: {sum(f["chino"] for f in filas)}   '
          f'mudos: {sum(1 for f in filas if f["mudo"])}   '
          f'fugas de think: {sum(1 for f in filas if f["fuga"])}   '
          f'bucles: {sum(f["bucle"] for f in filas)}')
    if primera_mala:
        print(f'PRIMERA SEÑAL en el turno {primera_mala["turno"]}, '
              f'con el contexto en {primera_mala["ctx"]} '
              f'de {primera_mala["ventana"]}')
    else:
        print('sin ninguna señal de degradación en todo el recorrido')
    print(f'contexto final: {filas[-1]["ctx"]}/{filas[-1]["ventana"]}')

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(filas, f, ensure_ascii=False, indent=1)
        print(f'detalle en {args.json}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
