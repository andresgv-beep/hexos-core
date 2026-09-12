"""Resultado operativo separado de informe guardado. Sin ejecutar sistemas externos."""
import json
from uuid import uuid4
from .work import now


PROCEDURE = dict(id='pending_report', version=2,
    purpose='Consultar pendientes y preparar un resumen. No crea informes guardados.',
    steps=['Leer pendientes', 'Conservar instantánea como resultado del encargo',
           'Responder; report.save solo si la persona solicita guardar'],
    permissions='Lectura de fichas y registro operativo local, sin cambiar tareas.')


def initialize(store):
    store.db.executescript('''
        CREATE TABLE IF NOT EXISTS agent_results (
            id TEXT PRIMARY KEY, turn_id TEXT NOT NULL UNIQUE, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS report_sources (
            result_id TEXT PRIMARY KEY, report_id TEXT NOT NULL UNIQUE);
    ''')


def active(store, value):
    store.db.execute("INSERT INTO agent_state VALUES ('active',?) "
                     'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                     (json.dumps(value, ensure_ascii=False),))


def dispatch(store, name, args, turn_id):
    if name == 'procedure.list':
        return [PROCEDURE]
    if name == 'procedure.get':
        if args['id'] != PROCEDURE['id']:
            raise ValueError('procedimiento inexistente')
        return PROCEDURE
    if name == 'result.get':
        result_id = args.get('id')
        if result_id is None:
            state = store.db.execute("SELECT value FROM agent_state WHERE key='active'").fetchone()
            result_id = json.loads(state[0]).get('result_id') if state else None
            if result_id is None:
                raise ValueError('no hay un resultado preparado en el encargo activo')
        row = store.db.execute('SELECT body FROM agent_results WHERE id=?', (result_id,)).fetchone()
        if row is None:
            raise ValueError('resultado inexistente')
        return json.loads(row[0])
    store.db.execute('BEGIN IMMEDIATE')
    try:
        source = store.db.execute("SELECT text FROM conversation WHERE id=? AND role='user'", (turn_id,)).fetchone()
        if source is None:
            raise ValueError('falta turno fuente verificable')
        if name == 'procedure.run':
            if args['id'] != PROCEDURE['id']:
                raise ValueError('procedimiento inexistente')
            row = store.db.execute('SELECT body FROM agent_results WHERE turn_id=?', (turn_id,)).fetchone()
            if row:
                store.db.commit()
                return json.loads(row[0])
            jobs = [json.loads(r[0]) for r in store.db.execute('SELECT body FROM jobs ORDER BY rowid')]
            items = [dict(id=j['id'],revision=j['revision'],title=j['title'],next_step=j['next_step'])
                     for j in jobs if j['state']=='pendiente']
            text = ('No hay trabajos pendientes.' if not items else
                    f'Tienes {len(items)} trabajo(s) pendiente(s):\n' + '\n'.join(
                        '- ' + j['title'] + ('. Siguiente paso: ' + j['next_step'] if j['next_step'] else '')
                        for j in items))
            result = dict(id=uuid4().hex,kind='pending_summary',ts=now(),source_turn=turn_id,
                          items=items,text=text,saved_report=False)
            store.db.execute('INSERT INTO agent_results VALUES (?,?,?)',
                             (result['id'],turn_id,json.dumps(result,ensure_ascii=False)))
            active(store, dict(intent='Resumen de trabajos pendientes',status='result_ready',
                               source_turn=turn_id,result_id=result['id'],updated_at=result['ts']))
        elif name == 'report.save':
            existing = store.db.execute('SELECT report_id FROM report_sources WHERE result_id=?',
                                        (args['result_id'],)).fetchone()
            if existing:
                row = store.db.execute('SELECT body FROM agent_reports WHERE id=?', (existing[0],)).fetchone()
                store.db.commit()
                return json.loads(row[0])
            draft = store.db.execute('SELECT body FROM agent_results WHERE id=?', (args['result_id'],)).fetchone()
            if draft is None:
                raise ValueError('resultado inexistente; no se crea un informe vacío')
            original = json.loads(draft[0])
            result = dict(original, id=uuid4().hex, result_id=original['id'], saved_report=True,
                          saved_at=now(), save_turn=turn_id)
            store.db.execute('INSERT INTO agent_reports VALUES (?,?,?,?,?,?,?)',
                (result['id'],result['saved_at'],turn_id,PROCEDURE['id'],2,source[0],json.dumps(result,ensure_ascii=False)))
            store.db.execute('INSERT INTO report_sources VALUES (?,?)', (original['id'],result['id']))
            active(store, dict(intent='Guardar resumen de pendientes',status='saved',source_turn=turn_id,
                result_id=original['id'],report_id=result['id'],updated_at=result['saved_at']))
        else:
            raise ValueError('operación no soportada')
        store.db.commit()
        return result
    except Exception:
        store.db.rollback()
        raise
