"""Registro SQLite de lotes, fichas, intenciones y leases con fencing tokens."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .files import movie
from .profiles import validate
from .policy import STATES, TERMINAL
from ..internal_tasks.queue import ensure as ensure_reviews, enqueue


def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class Conflict(ValueError):
    pass


class JobStore:
    def __init__(self, workspace):
        root = Path(workspace)
        root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(root / 'media_jobs.sqlite', timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS media_batches (
                id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL,
                paused INTEGER NOT NULL DEFAULT 0, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS media_jobs (
                id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES media_batches(id),
                resource TEXT NOT NULL, position INTEGER NOT NULL, state TEXT NOT NULL,
                revision INTEGER NOT NULL, due REAL NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS media_events (
                seq INTEGER PRIMARY KEY, job_id TEXT NOT NULL, ts REAL NOT NULL,
                kind TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS media_leases (
                resource TEXT PRIMARY KEY, token TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS media_actions (
                key TEXT PRIMARY KEY, job_id TEXT NOT NULL, ts REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS media_resource ON media_jobs(resource, state);
        ''')
        ensure_reviews(self.db)

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def create(self, sources, profile, resource, request_key, now, mode='simulation', require_review=False, config_digest=None):
        if mode not in ('simulation', 'live'):
            raise ValueError('Modo inválido')
        if not isinstance(sources, list) or not 1 <= len(sources) <= 5:
            raise ValueError('Seleccionar entre una y cinco películas')
        if not all(isinstance(s, str) and s.strip() for s in (resource, request_key)):
            raise ValueError('Recurso y clave de petición requeridos')
        sources = [movie(s) for s in sources]
        keys = {(s['device'], s['path']) for s in sources}
        if len({s['device'] for s in sources}) != 1:
            raise ValueError('Un lote pertenece a un solo equipo')
        destinations = {(s['device'], s['destination']) for s in sources}
        if len(destinations) != len(sources):
            raise Conflict('Dos películas producirían el mismo destino')
        if len(keys) != len(sources):
            raise ValueError('Película duplicada en el lote')
        profile = validate(profile)
        fingerprint = dump(dict(sources=sources, profile=profile, resource=resource, mode=mode,
                                require_review=require_review, config_digest=config_digest))
        with self.transaction():
            existing = self.db.execute('SELECT * FROM media_batches WHERE request_key=?', (request_key,)).fetchone()
            if existing:
                if existing['fingerprint'] != fingerprint:
                    raise Conflict('La clave ya identifica otro lote')
                return self.batch(existing['id'])
            for row in self.db.execute('SELECT body FROM media_jobs'):
                old = json.loads(row[0])
                if old['state'] not in TERMINAL and ((old['source']['device'], old['source']['path']) in keys
                        or (old['source']['device'], old['source']['destination']) in destinations):
                    raise Conflict('Película ya en una tarea activa')
            batch = uuid4().hex
            self.db.execute('INSERT INTO media_batches VALUES (?,?,?,0,?)',
                            (batch, request_key, fingerprint, dump(dict(created_at=now, mode=mode))))
            for position, source in enumerate(sources):
                job = dict(id=uuid4().hex, batch_id=batch, resource=resource, position=position,
                           state='queued', revision=0, due=now, source=source, profile=profile,
                           mode=mode, require_review=require_review, config_digest=config_digest,
                           attempt=0, observation=None, error=None, created_at=now)
                self.db.execute('INSERT INTO media_jobs VALUES (?,?,?,?,?,?,?,?)',
                    (job['id'], batch, resource, position, 'queued', 0, now, dump(job)))
                self.event(job['id'], now, 'created', dict(source=source, profile_hash=profile['sha256']))
        return self.batch(batch)

    def event(self, job_id, now, kind, body):
        self.db.execute('INSERT INTO media_events(job_id,ts,kind,body) VALUES (?,?,?,?)',
                        (job_id, now, kind, dump(body)))

    def get(self, job_id):
        row = self.db.execute('SELECT body FROM media_jobs WHERE id=?', (job_id,)).fetchone()
        if not row:
            raise ValueError('Tarea inexistente')
        return json.loads(row[0])

    def batch(self, batch_id):
        row = self.db.execute('SELECT * FROM media_batches WHERE id=?', (batch_id,)).fetchone()
        if not row:
            raise ValueError('Lote inexistente')
        return dict(id=batch_id, paused=bool(row['paused']), **json.loads(row['body']),
                    jobs=[json.loads(r[0]) for r in self.db.execute(
                        'SELECT body FROM media_jobs WHERE batch_id=? ORDER BY position', (batch_id,))])

    def listing(self):
        return [self.batch(r[0]) for r in self.db.execute('SELECT id FROM media_batches ORDER BY rowid DESC LIMIT 50')]

    def _save(self, job):
        if job['state'] not in STATES:
            raise ValueError('Estado inválido')
        job['revision'] += 1
        self.db.execute('UPDATE media_jobs SET state=?,revision=?,due=?,body=? WHERE id=?',
                        (job['state'], job['revision'], job['due'], dump(job), job['id']))

    def claim(self, resource, now, lease_seconds=30):
        with self.transaction():
            lease = self.db.execute('SELECT * FROM media_leases WHERE resource=?', (resource,)).fetchone()
            if lease and lease['expires'] > now:
                return None
            # Primera ficha no terminal por recurso. Pausa/bloqueo no permiten
            # saltar a otro lote mientras podría quedar un efecto remoto activo.
            for row in self.db.execute('SELECT j.*, b.paused FROM media_jobs j JOIN media_batches b '
                                       'ON j.batch_id=b.id WHERE resource=? ORDER BY j.rowid', (resource,)):
                if row['state'] in TERMINAL:
                    continue
                if row['state'] in ('blocked','awaiting_review') or (row['paused'] and row['state'] == 'queued') or row['due'] > now:
                    return None
                token = uuid4().hex
                self.db.execute('INSERT OR REPLACE INTO media_leases VALUES (?,?,?)',
                                (resource, token, now+lease_seconds))
                return json.loads(row['body']), token
        return None

    def _lease(self, resource, token, now):
        row = self.db.execute('SELECT token,expires FROM media_leases WHERE resource=?', (resource,)).fetchone()
        if not row or row['token'] != token or row['expires'] <= now:
            raise Conflict('Lease expirado o reemplazado: descartar respuesta antigua')

    def intention(self, job, token, key, now):
        with self.transaction():
            self._lease(job['resource'], token, now)
            if self.get(job['id'])['revision'] != job['revision']:
                raise Conflict('La ficha cambió')
            cursor = self.db.execute('INSERT OR IGNORE INTO media_actions VALUES (?,?,?)', (key, job['id'], now))
            if cursor.rowcount:
                self.event(job['id'], now, 'intention', dict(key=key, state=job['state']))

    def finish(self, job, token, changes, now, pause=False):
        with self.transaction():
            self._lease(job['resource'], token, now)
            current = self.get(job['id'])
            if current['revision'] != job['revision']:
                raise Conflict('La ficha cambió durante la operación')
            current.update(changes)
            self._save(current)
            enqueue(self,current,now)
            if pause:
                self.db.execute('UPDATE media_batches SET paused=1 WHERE id=?', (job['batch_id'],))
            self.event(job['id'], now, 'transition', changes)
            self.db.execute('DELETE FROM media_leases WHERE resource=? AND token=?', (job['resource'], token))
        return current

    def control(self, batch_id, operation, now):
        if operation not in ('pause', 'resume', 'cancel'):
            raise ValueError('Control desconocido')
        with self.transaction():
            batch = self.batch(batch_id)
            self.db.execute('UPDATE media_batches SET paused=? WHERE id=?', (operation != 'resume', batch_id))
            for job in batch['jobs']:
                if operation == 'resume' and job['state'] == 'blocked':
                    job['state'] = job.pop('resume_state')
                elif operation == 'cancel' and job['state'] not in TERMINAL:
                    job['state'] = 'cancelled' if job['state'] == 'queued' else 'cancel_requested'
                else:
                    self.event(job['id'], now, operation, {})
                    continue
                job['due'] = now
                self._save(job)
                enqueue(self,job,now)
                self.event(job['id'], now, operation, {})
        return self.batch(batch_id)
