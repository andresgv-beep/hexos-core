"""Inicialización del almacén existente; no introduce migraciones nuevas."""
from __future__ import annotations

from .. import catalog, procedures, workflow, notes, devices

# Cada ventana tiene su conversación. La tabla `conversation` no cambia: quien escribe
# sigue insertando igual, y un disparador apunta el mensaje a la ventana que esté puesta
# en agent_state. Quien lee «lo anterior» lee `esta_ventana`, que solo enseña lo de la
# ventana actual y conserva el rowid, así los cortes de contexto siguen valiendo. Un
# mensaje sin apunte es de antes de separar las ventanas y pertenece al chat: el
# historial que ya existía se queda allí sin migrar nada, y el agente empieza limpio.
VENTANA_ACTUAL = "COALESCE((SELECT value FROM agent_state WHERE key='window'),'%s')" % catalog.DEFAULT_WINDOW
POR_VENTANA = '''
    CREATE TABLE IF NOT EXISTS conversation_ventana (
        id TEXT PRIMARY KEY, ventana TEXT NOT NULL);
    CREATE TRIGGER IF NOT EXISTS conversation_a_su_ventana AFTER INSERT ON conversation BEGIN
        INSERT OR REPLACE INTO conversation_ventana VALUES (NEW.id, %(actual)s);
    END;
    CREATE VIEW IF NOT EXISTS esta_ventana AS
        SELECT c.rowid AS rowid, c.id, c.ts, c.role, c.text, c.model_text FROM conversation c
        WHERE COALESCE((SELECT v.ventana FROM conversation_ventana v WHERE v.id=c.id),'%(chat)s') = %(actual)s;
''' % dict(actual=VENTANA_ACTUAL, chat=catalog.DEFAULT_WINDOW)


def clave(store, base):
    """La clave de agent_state para la ventana actual: corte y traspaso son de cada una.

    El chat conserva el nombre de siempre, que es donde está lo ya guardado.
    """
    actual = store.db.execute('SELECT ' + VENTANA_ACTUAL).fetchone()[0]
    return base if actual == catalog.DEFAULT_WINDOW else base + ':' + actual


def initialize(store):
    store.db.executescript('''
        CREATE TABLE IF NOT EXISTS conversation (
            id TEXT PRIMARY KEY, ts TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL,
            model_text TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY, ts TEXT NOT NULL, content TEXT NOT NULL, sha256 TEXT NOT NULL);
        -- Escrituras cuyo efecto no se sabe: el tiempo se agotó y no consta si
        -- llegaron a ejecutarse. Sobreviven al turno a propósito. Se cierran con
        -- una LECTURA que aclare el estado, nunca repitiendo la escritura.
        CREATE TABLE IF NOT EXISTS pending_effects (
            id TEXT PRIMARY KEY, ts TEXT NOT NULL, device TEXT NOT NULL,
            target TEXT NOT NULL, action TEXT NOT NULL, turn_id TEXT NOT NULL,
            resolved_at TEXT, resolved_state TEXT);
        CREATE TABLE IF NOT EXISTS tool_events (
            seq INTEGER PRIMARY KEY, turn_id TEXT NOT NULL, ts TEXT NOT NULL,
            body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS generation_events (
            seq INTEGER PRIMARY KEY, turn_id TEXT NOT NULL, ts TEXT NOT NULL,
            body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS progress_events (
            id TEXT PRIMARY KEY, turn_id TEXT NOT NULL, ts TEXT NOT NULL, text TEXT NOT NULL);
    ''')
    procedures.initialize(store)
    workflow.initialize(store)
    notes.initialize(store)
    devices.initialize(store)
    store.db.executescript(POR_VENTANA)        # después: lee agent_state, que crea procedures
