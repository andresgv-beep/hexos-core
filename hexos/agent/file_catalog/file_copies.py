"""Almacén local de copias inmutables; ninguna ruta HTTP permite leer el filesystem."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4


def database(workspace):
    Path(workspace).mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(Path(workspace) / 'file_copies.sqlite')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS copies (id TEXT PRIMARY KEY, metadata TEXT NOT NULL, content BLOB NOT NULL)')
    return db


def save(workspace, metadata, content):
    identifier = uuid4().hex
    metadata = dict(metadata, file_id=identifier, sha256=hashlib.sha256(content).hexdigest())
    db = database(workspace)
    try:
        with db:
            db.execute('INSERT INTO copies VALUES (?,?,?)', (identifier, json.dumps(metadata), content))
    finally:
        db.close()
    return metadata


def get(workspace, identifier):
    if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{32}', identifier):
        raise ValueError('Identificador de archivo no válido')
    db = database(workspace)
    try:
        row = db.execute('SELECT metadata,content FROM copies WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise ValueError('Copia de archivo inexistente')
        return json.loads(row['metadata']), row['content']
    finally:
        db.close()


def listing(workspace):
    db = database(workspace)
    try:
        return [json.loads(row[0]) for row in db.execute('SELECT metadata FROM copies ORDER BY rowid DESC LIMIT 50')]
    finally:
        db.close()
