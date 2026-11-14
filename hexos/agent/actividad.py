"""Lo que Helios ha hecho en la conversación actual, para el lateral del Agente.

La interfaz solo sabía de cada llamada el nombre y si acabó bien: bastaba para el resumen
plegado del chat («herramientas · 2 llamadas»), no para ver qué orden se lanzó. Aquí se
sirve, de la conversación que está puesta (la ventana y, en el Agente, el proyecto):

- las últimas llamadas, cada una con una línea que dice qué se pidió;
- los cambios: lo que tuvo efecto y lo que la persona decidió en una tarjeta;
- el detalle de una llamada, con sus argumentos y un extracto de la salida.

Solo lee lo ya registrado en `tool_events`. No ejecuta nada.
"""
from __future__ import annotations

import json

MAX_LLAMADAS = 40
MAX_CAMBIOS = 20
MAX_LINEA = 140
MAX_SALIDA = 4000
NOTA_INTERFAZ = '[La persona '

# Qué argumento dice de un vistazo lo que se pidió, por herramienta o por familia.
PRINCIPAL = {
    'terminal.read': ('command',), 'web.search': ('query',), 'web.read': ('url',),
    'system.package_plan': ('action', 'package', 'manager'),
    'history.search': ('query',), 'profile.recall': ('query',),
    'note.save': ('title',), 'media.prepare': ('title', 'path'),
    'project.read': ('path', 'start'), 'project.files': ('path', 'pattern'), 'project.search': ('query', 'path'),
    'project.write': ('path',),
}
FAMILIA = {'nas.': ('path', 'query', 'device'), 'device.': ('device', 'name', 'target'),
           'note.': ('title', 'id', 'n'), 'media.': ('batch_id', 'operation'), 'document.': ('query', 'id')}


def _corto(texto, limite=MAX_LINEA):
    texto = ' '.join(str(texto).split())
    return texto if len(texto) <= limite else texto[:limite - 1] + '…'


def resumen(herramienta, argumentos):
    """Una línea con lo que se pidió: la orden, la búsqueda, el paquete."""
    if not isinstance(argumentos, dict) or not argumentos:
        return ''
    claves = PRINCIPAL.get(herramienta) or next(
        (c for prefijo, c in FAMILIA.items() if herramienta.startswith(prefijo)), None)
    if claves:
        partes = [str(argumentos[c]) for c in claves if argumentos.get(c) not in (None, '')]
        if herramienta == 'terminal.read' and argumentos.get('filter'):
            partes.append('· filter ' + str(argumentos['filter']))
        if herramienta == 'terminal.read' and argumentos.get('path') and str(argumentos['path']) not in partes[0]:
            partes.insert(1, str(argumentos['path']))
        if partes:
            return _corto(' '.join(partes))
    return _corto(json.dumps(argumentos, ensure_ascii=False))


def _eventos(store, limite):
    for fila in store.db.execute(
            'SELECT e.seq, e.ts, e.body FROM tool_events e JOIN esta_ventana c ON c.id=e.turn_id '
            'ORDER BY e.seq DESC LIMIT ?', (limite,)):
        try:
            evento = json.loads(fila['body'])
        except (TypeError, ValueError):
            continue
        if isinstance(evento, dict) and isinstance(evento.get('tool'), str):
            yield fila['seq'], fila['ts'], evento


def _segundos(evento):
    valor = evento.get('seconds')
    return round(valor, 2) if isinstance(valor, (int, float)) and valor >= 0 else None


def reciente(store, efectos=None):
    """Las últimas llamadas y los cambios de la conversación actual, lo más nuevo primero."""
    efectos = efectos or {}
    llamadas, cambios = [], []
    for seq, ts, evento in _eventos(store, 400):
        herramienta = evento['tool']
        fallo = bool(evento.get('failed'))
        linea = resumen(herramienta, evento.get('arguments'))
        if len(llamadas) < MAX_LLAMADAS:
            llamadas.append(dict(seq=seq, ts=ts, tool=herramienta, summary=linea, failed=fallo,
                                 seconds=_segundos(evento)))
        efecto = evento.get('effect') or efectos.get(herramienta, 'read')
        if not fallo and efecto != 'read' and len(cambios) < MAX_CAMBIOS:
            cambios.append(dict(ts=ts, kind='tool', text=_corto(herramienta + ' ' + linea, 200)))
    for fila in store.db.execute(
            "SELECT ts, text FROM esta_ventana WHERE role='user' AND text LIKE ? ORDER BY rowid DESC LIMIT ?",
            (NOTA_INTERFAZ + '%', MAX_CAMBIOS)):
        cambios.append(dict(ts=fila['ts'], kind='decision', text=_corto(fila['text'].strip('[]'), 240)))
    cambios.sort(key=lambda c: c['ts'], reverse=True)
    return dict(tools=llamadas, changes=cambios[:MAX_CAMBIOS])


def detalle(store, seq):
    """Argumentos y salida de una llamada de la conversación actual, con tope."""
    if type(seq) is not int or seq < 1:
        raise ValueError('seq debe ser un entero positivo')
    fila = store.db.execute(
        'SELECT e.seq, e.ts, e.body FROM tool_events e JOIN esta_ventana c ON c.id=e.turn_id WHERE e.seq=?',
        (seq,)).fetchone()
    if fila is None:
        # Una llamada de otro proyecto o de la otra ventana no se enseña desde aquí.
        raise ValueError('llamada inexistente en esta conversación')
    evento = json.loads(fila['body'])
    resultado = evento.get('result')
    salida = resultado.get('output') if isinstance(resultado, dict) and isinstance(resultado.get('output'), str) else None
    if salida is None:
        salida = json.dumps(resultado, ensure_ascii=False, indent=1)
    return dict(seq=fila['seq'], ts=fila['ts'], tool=evento.get('tool'), arguments=evento.get('arguments') or {},
                failed=bool(evento.get('failed')), seconds=_segundos(evento),
                output=salida[:MAX_SALIDA], truncated=len(salida) > MAX_SALIDA)
