"""Procedimientos de confianza y resultados persistentes; nunca ejecuta comandos."""
import json

from .work import string
from . import catalog


def initialize(store):
    store.db.executescript('''
        CREATE TABLE IF NOT EXISTS agent_reports (
            id TEXT PRIMARY KEY, ts TEXT NOT NULL, turn_id TEXT NOT NULL,
            procedure_id TEXT NOT NULL, version INTEGER NOT NULL,
            request TEXT NOT NULL, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS agent_state (
            key TEXT PRIMARY KEY, value TEXT NOT NULL);
    ''')


def state(store):
    row = store.db.execute("SELECT value FROM agent_state WHERE key='active'").fetchone()
    return json.loads(row[0]) if row else None


def dispatch(store, name, args, *, turn_id=None):
    catalog.validate(name, args)
    if name == 'task.current':
        return state(store)
    if name == 'task.focus':
        intent = string(args['intent'], 'intent', 500)
        question = string(args['question'], 'question', 500)
        source = store.db.execute("SELECT text FROM conversation WHERE id=? AND role='user'",
                                  (turn_id,)).fetchone()
        if source is None:
            raise ValueError('falta turno fuente verificable')
        active = dict(intent=intent, question=question, status='awaiting_clarification',
                      authority='model_interpretation', source_turn=turn_id,
                      source_text=source[0][:2000], source_partial=len(source[0]) > 2000)
        store.db.execute("INSERT INTO agent_state VALUES ('active',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (json.dumps(active, ensure_ascii=False),))
        store.db.commit()
        return active
    if name == 'report.list':
        return [dict(r) for r in store.db.execute(
            'SELECT id,ts,procedure_id,version FROM agent_reports ORDER BY rowid DESC LIMIT 50')]
    if name == 'report.get':
        row = store.db.execute('SELECT body FROM agent_reports WHERE id=?', (args['id'],)).fetchone()
        if row is None:
            raise ValueError('informe inexistente')
        return json.loads(row[0])
    raise ValueError('operación no soportada')
