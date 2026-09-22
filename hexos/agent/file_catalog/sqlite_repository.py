"""Único propietario del esquema SQLite y de las transacciones del catálogo.

No conoce SSH, herramientas, chat, GPU ni interfaz. Mantiene la base existente.
"""
import json
from pathlib import Path
import posixpath
import sqlite3
from uuid import uuid4

from ..work import now
from .validation import (integer, filters_argument, extensions_argument,
                         path_argument, parents_within_root, scan_coverage)

def database(workspace):
    directory = Path(workspace)
    directory.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(directory / 'nas_files.sqlite')
    db.row_factory = sqlite3.Row
    db.executescript('''
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS scans (
            id TEXT PRIMARY KEY, device TEXT NOT NULL, observed_at TEXT NOT NULL,
            roots TEXT NOT NULL, coverage TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS files (
            scan_id TEXT NOT NULL REFERENCES scans(id), path TEXT NOT NULL,
            root TEXT NOT NULL, name TEXT NOT NULL, size_bytes INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL, filesystem_id TEXT NOT NULL, inode INTEGER NOT NULL,
            media_kind TEXT NOT NULL, PRIMARY KEY(scan_id, path));
        CREATE INDEX IF NOT EXISTS files_size ON files(scan_id, size_bytes DESC, path);
        CREATE TABLE IF NOT EXISTS directories (
            device TEXT NOT NULL, path TEXT NOT NULL, observed_at TEXT NOT NULL,
            PRIMARY KEY(device, path));
        CREATE TABLE IF NOT EXISTS directory_imports (scan_id TEXT PRIMARY KEY);
    ''')
    return db


def remember_directories(db, device, paths, observed_at):
    db.executemany('INSERT INTO directories VALUES (?,?,?) ON CONFLICT(device,path) '
                   'DO UPDATE SET observed_at=MAX(observed_at,excluded.observed_at)',
                   ((device.casefold(), path, observed_at) for path in set(paths)))


def locations(workspace, *, device=None, query=None, limit=20, offset=0):
    """Memoria local de directorios observados, sin SSH ni nuevo recorrido.

    Recupera también los catálogos creados antes de introducir esta memoria.
    La fecha acredita observación anterior, no existencia o permisos actuales.
    """
    integer(limit, 'limit', 1, 100)
    integer(offset, 'offset')
    if query is not None and (not isinstance(query, str) or len(query) > 500):
        raise ValueError('query debe ser texto de hasta 500 caracteres')
    db = database(workspace)
    try:
        with db:
            for scan in db.execute('SELECT * FROM scans WHERE id NOT IN (SELECT scan_id FROM directory_imports)').fetchall():
                paths = set(json.loads(scan['coverage']).get('filesystems', {}))
                for item in db.execute('SELECT path,root FROM files WHERE scan_id=?', (scan['id'],)):
                    paths.update(parents_within_root(item['path'], item['root']))
                remember_directories(db, scan['device'], paths, scan['observed_at'])
                db.execute('INSERT INTO directory_imports VALUES (?)', (scan['id'],))
        db.create_function('casefold', 1, str.casefold)
        db.create_function('basename', 1, posixpath.basename)
        clauses, values = [], []
        if device:
            clauses.append('device=?')
            values.append(device.casefold())
        if query:
            # Buscar el nombre del directorio evita devolver todas las películas
            # descendientes cuando se pide dónde está la carpeta multimedia.
            clauses.append('instr(casefold(basename(path)),?)>0')
            values.append(query.casefold())
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        total = db.execute('SELECT COUNT(*) FROM directories' + where, values).fetchone()[0]
        items = [dict(row) for row in db.execute('SELECT * FROM directories' + where +
                 " ORDER BY length(path)-length(replace(path,'/','')),path,device LIMIT ? OFFSET ?",
                 values + [limit, offset])]
        return dict(items=items, total_matches=total, offset=offset,
                    next_offset=offset + len(items) if offset + len(items) < total else None,
                    source='saved_directory_observations', network_used=False)
    finally:
        db.close()

def publish_snapshot(workspace, result, roots, *, scan_id=None):
    """Publica metadatos inmutables; conserva cobertura completa o parcial."""
    coverage = scan_coverage(result)
    scan_id = scan_id or uuid4().hex
    db = database(workspace)
    try:
        with db:
            existing = db.execute('SELECT * FROM scans WHERE id=?', (scan_id,)).fetchone()
            expected = (scan_id, result['device'], result['observed_at'], json.dumps(roots), json.dumps(coverage))
            if existing:
                actual_items = {r['path']: dict(r) for r in db.execute('SELECT * FROM files WHERE scan_id=?', (scan_id,))}
                expected_items = {i['path']: dict(scan_id=scan_id, **{k:i[k] for k in
                    ('path','root','name','size_bytes','mtime_ns','filesystem_id','inode','media_kind')}) for i in result['items']}
                if tuple(existing) != expected or actual_items != expected_items:
                    raise ValueError('El identificador de observación pertenece a otros metadatos')
            db.execute('INSERT OR IGNORE INTO scans VALUES (?,?,?,?,?)',
                       (scan_id, result['device'], result['observed_at'], json.dumps(roots), json.dumps(coverage)))
            directories = set(result.get('filesystems', {}))
            for item in result['items']:
                directories.update(parents_within_root(item['path'], item['root']))
                # Una raíz anidada puede observar el mismo path; la ruta más
                # específica conserva la atribución. No colapsar hardlinks por nombre.
                db.execute('INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?,?,?)',
                           (scan_id, item['path'], item['root'], item['name'], item['size_bytes'],
                            item['mtime_ns'], item['filesystem_id'], item['inode'], item['media_kind']))
            remember_directories(db, result['device'], directories, result['observed_at'])
            db.execute('INSERT OR IGNORE INTO directory_imports VALUES (?)', (scan_id,))
        totals = [dict(row) for row in db.execute(
            'SELECT root, filesystem_id, COUNT(*) AS files, SUM(size_bytes) AS logical_bytes '
            'FROM files WHERE scan_id=? GROUP BY root, filesystem_id ORDER BY root', (scan_id,))]
    finally:
        db.close()
    return dict(scan_id=scan_id, device=result['device'], observed_at=result['observed_at'],
                published=True, roots=roots, totals=totals, coverage=coverage)

def search(workspace, *, scan_id, min_bytes=0, max_bytes=None, query=None,
           root=None, kind='all', offset=0, limit=30, extensions=None):
    filters_argument(min_bytes, max_bytes, query, limit)
    extensions = extensions_argument(extensions)
    integer(offset, 'offset')
    if kind not in ('all', 'video'):
        raise ValueError('kind debe ser all o video; video identifica extensiones, no códecs')
    if not isinstance(scan_id, str) or not scan_id:
        raise ValueError('scan_id debe ser el identificador devuelto por nas.index')
    clauses, values = ['scan_id=?', 'size_bytes>=?'], [scan_id, min_bytes]
    if max_bytes is not None:
        clauses.append('size_bytes<=?')
        values.append(max_bytes)
    if root is not None:
        root = path_argument(root)
        clauses.append('root=?')
        values.append(root)
    if kind == 'video':
        clauses.append("media_kind='video'")
    if extensions:
        clauses.append('extension(name) IN (' + ','.join('?' for _ in extensions) + ')')
        values.extend(extensions)
    if query:
        clauses.append('instr(casefold(name), ?) > 0')
        values.append(query.casefold())
    db = database(workspace)
    try:
        db.create_function('casefold', 1, str.casefold)
        db.create_function('extension', 1, lambda name: posixpath.splitext(name)[1].lower().lstrip('.'))
        scan = db.execute('SELECT * FROM scans WHERE id=?', (scan_id,)).fetchone()
        if scan is None:
            raise ValueError('Catálogo inexistente; primero usa nas.index con las rutas observadas')
        coverage = json.loads(scan['coverage'])
        indexed_extensions = coverage.get('indexed_extensions', [])
        if indexed_extensions:
            if extensions and not set(extensions).issubset(indexed_extensions):
                raise ValueError('Este catálogo solo incluye extensiones ' + ', '.join(indexed_extensions) +
                                 '. Para ampliarlas usa nas.find de nuevo.')
            if not extensions:
                extensions = indexed_extensions
        if root is not None and root not in json.loads(scan['roots']):
            raise ValueError('root debe ser una de las raíces de este catálogo')
        where = ' AND '.join(clauses)
        count = db.execute('SELECT COUNT(*), COALESCE(SUM(size_bytes),0) FROM files WHERE ' + where,
                           values).fetchone()
        items = [dict(row) for row in db.execute(
            'SELECT path, root, name, size_bytes, mtime_ns, filesystem_id, inode, media_kind '
            'FROM files WHERE ' + where + ' ORDER BY size_bytes DESC, path ASC LIMIT ? OFFSET ?',
            values + [limit, offset])]
        totals = [dict(row) for row in db.execute(
            'SELECT root, filesystem_id, COUNT(*) AS files, SUM(size_bytes) AS logical_bytes '
            'FROM files WHERE ' + where + ' GROUP BY root, filesystem_id ORDER BY root', values)]
        complete = coverage.get('complete', False)
        return dict(scan_id=scan_id, device=scan['device'], observed_at=scan['observed_at'],
                    complete=complete, total_is_exact=complete, coverage=coverage,
                    roots=json.loads(scan['roots']),
                    queried_at=now(), total_matches=count[0], logical_bytes=count[1], totals=totals,
                    items=items, offset=offset, next_offset=offset + len(items) if offset + len(items) < count[0] else None,
                    filters=dict(min_bytes=min_bytes, max_bytes=max_bytes, root=root, kind=kind, query=query,
                                 extensions=extensions))
    finally:
        db.close()


class SQLiteCatalog:
    """Adaptador del puerto CatalogStore; todas las conexiones se cierran por operación."""
    def __init__(self, workspace):
        self.workspace = workspace

    def publish(self, result, roots):
        return publish_snapshot(self.workspace, result, roots)

    def search(self, **kwargs):
        return search(self.workspace, **kwargs)

    def locations(self, **kwargs):
        return locations(self.workspace, **kwargs)

    def publish_directories(self, result):
        from .directory_snapshots import publish
        db = database(self.workspace)
        try:
            return publish(db, result)
        finally:
            db.close()

    def read_directories(self, snapshot_id):
        from .directory_snapshots import read
        db = database(self.workspace)
        try:
            return read(db, snapshot_id)
        finally:
            db.close()

    def remember_browse(self, result, path):
        db = database(self.workspace)
        try:
            with db:
                paths = [item['path'] for item in result['items'] if item['kind'] == 'directory']
                if result.get('complete'):
                    paths.append(path)
                remember_directories(db, result['device'], paths, result['observed_at'])
        finally:
            db.close()

    def remember_locations(self, result):
        db = database(self.workspace)
        try:
            with db:
                remember_directories(db, result['device'],
                                     [item['path'] for item in result['items']], result['observed_at'])
        finally:
            db.close()
