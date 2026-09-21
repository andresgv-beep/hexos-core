"""Persistencia de observaciones de directorios para paginar sin repetir SSH."""
import json
from uuid import uuid4


def publish(db, result):
    identifier = uuid4().hex
    with db:
        db.execute('CREATE TABLE IF NOT EXISTS directory_snapshots (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
        db.execute('INSERT INTO directory_snapshots VALUES (?,?)',
                   (identifier, json.dumps(result, ensure_ascii=False)))
    return identifier


def read(db, identifier):
    if not isinstance(identifier, str) or not identifier:
        raise ValueError('snapshot_id debe identificar una observación de directorios')
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='directory_snapshots'").fetchone()
    row = db.execute('SELECT body FROM directory_snapshots WHERE id=?', (identifier,)).fetchone() if exists else None
    if row is None:
        raise ValueError('Observación de directorios inexistente; realiza una nueva lectura')
    return json.loads(row[0])
