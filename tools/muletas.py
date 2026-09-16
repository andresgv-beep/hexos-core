"""Cuánto trabajo hace el modelo y cuánto hace HexOS por él.

La pregunta que contesta: si mañana cambias de modelo, ¿mejoró de verdad? Las
muletas se disparan SOLO cuando el modelo no actúa, así que su frecuencia es una
medida directa de lo que le falta. Con un modelo mejor debería bajar sola.

    python3 tools/muletas.py --workspace runtime/workspace [--desde 2026-09-15]

No toca nada: lee el registro que el agente ya guarda.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Lo que HexOS hace SIEMPRE, por diseño: no son muletas y no deben inflar la cifra.
# Buscar en el archivo o guardar un hecho del perfil no suple una incapacidad del
# modelo, igual que resolver «srv1» no lo suple: es el sistema sabiendo lo suyo.
POR_DISENO = ('history.recall', 'profile.remember')


def medir(db_path, desde=None):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    turnos = {r['id']: r['ts'] for r in db.execute("SELECT id, ts FROM conversation WHERE role='user'")
              if not desde or r['ts'][:10] >= desde}
    if not turnos:
        return dict(turnos=0, suplencias=0, avisos=0, acciones_modelo=0,
                    por_diseno=0, detalle=Counter(), avisos_detalle=Counter())
    suplidos, avisados = set(), set()
    detalle, acciones_modelo, por_diseno = Counter(), 0, 0
    for fila in db.execute('SELECT turn_id, body FROM tool_events'):
        if fila['turn_id'] not in turnos:
            continue
        paso = json.loads(fila['body'])
        herramienta = paso.get('tool')
        resultado = paso.get('result') if isinstance(paso.get('result'), dict) else {}
        if herramienta in POR_DISENO:
            por_diseno += 1
        elif resultado.get('requested_by') == 'hexos':
            suplidos.add(fila['turn_id'])
            detalle[herramienta] += 1
        else:
            acciones_modelo += 1
    avisos_detalle = Counter()
    for fila in db.execute('SELECT turn_id, body FROM generation_events'):
        if fila['turn_id'] not in turnos:
            continue
        prompt = json.loads(fila['body']).get('prompt') or ''
        if 'AVISO DE HEXOS' not in prompt:
            continue
        avisados.add(fila['turn_id'])
        # Qué le tuvimos que recordar, por el verbo del aviso.
        for clave, etiqueta in (('no se ha ejecutado note_', 'no abrió/cerró lo que dijo'),
                                ('falta por leer', 'se dejó equipos o secciones'),
                                ('sin haberlo hecho', 'prometió y no hizo'),
                                ('ninguna operación de escritura', 'dijo haber guardado')):
            if clave in prompt:
                avisos_detalle[etiqueta] += 1
                break
    db.close()
    return dict(turnos=len(turnos), suplencias=len(suplidos), avisos=len(avisados),
                acciones_modelo=acciones_modelo, por_diseno=por_diseno,
                detalle=detalle, avisos_detalle=avisos_detalle)


def informe(m):
    if not m['turnos']:
        return 'Sin turnos en ese rango.'
    pct = lambda n: f'{100 * n / m["turnos"]:5.1f}%'
    lineas = [f'Turnos medidos: {m["turnos"]}', '',
              f'  Acciones que hizo el modelo:        {m["acciones_modelo"]:4}',
              f'  Turnos donde HexOS actuó por él:    {m["suplencias"]:4}   {pct(m["suplencias"])}',
              f'  Turnos donde hubo que avisarle:     {m["avisos"]:4}   {pct(m["avisos"])}',
              f'  (Aparte, por diseño y no muleta:    {m["por_diseno"]:4})']
    if m['detalle']:
        lineas += ['', '  Lo que tuvo que hacer HexOS:']
        lineas += [f'    {h:14} {n}' for h, n in m['detalle'].most_common()]
    if m['avisos_detalle']:
        lineas += ['', '  Lo que hubo que recordarle:']
        lineas += [f'    {e:32} {n}' for e, n in m['avisos_detalle'].most_common()]
    lineas += ['', 'Las muletas saltan solo cuando el modelo no actúa: con uno mejor, estas',
               'cifras bajan solas. Un cero no significa que sobren —siguen puestas por si',
               'el día malo—, significa que ese día no hicieron falta.']
    return '\n'.join(lineas)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', default='runtime/workspace')
    p.add_argument('--desde', help='solo turnos desde esa fecha, AAAA-MM-DD')
    a = p.parse_args()
    print(informe(medir(str(Path(a.workspace) / 'work.sqlite'), a.desde)))


if __name__ == '__main__':
    main()
