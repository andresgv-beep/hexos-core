"""Fichas persistentes. No ejecuta comandos ni concede permisos.

CLI JSON: python3 -m hexos.agent.work --workspace DIR < peticion.json
La aplicación llama dispatch con actor='model' o actor='user' según el origen
real del mensaje. El actor nunca se toma de la petición del modelo.
"""
import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

KINDS = ('consulta', 'diagnostico', 'mantenimiento', 'documento', 'codigo')
STATES = ('pendiente', 'en_curso', 'bloqueado', 'terminado')
CLASS_FIELDS = {'kind', 'scope', 'tags'}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def string(value, name, limit=2000, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError(f'{name}: texto inválido (máximo {limit})')
    return value


def strings(value, name):
    if not isinstance(value, list) or len(value) > 32:
        raise ValueError(f'{name}: se espera lista de hasta 32 textos')
    return [string(v, name, 1000) for v in value]


class WorkStore:
    def __init__(self, workspace):
        root = Path(workspace).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(root / 'work.sqlite', timeout=10)
        # La conversación entera vive aquí: no debe quedar legible para otras cuentas.
        for name in ('work.sqlite', 'work.sqlite-wal', 'work.sqlite-shm'):
            path = root / name
            if path.exists() and path.stat().st_mode & 0o077:
                path.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY, job TEXT NOT NULL REFERENCES jobs(id),
                ts TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
                body TEXT NOT NULL);
        ''')

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def get(self, job_id):
        row = self.db.execute('SELECT body FROM jobs WHERE id=?', (job_id,)).fetchone()
        if row is None:
            raise ValueError('trabajo inexistente')
        return json.loads(row['body'])

    def save(self, job, actor, action):
        self.db.execute('INSERT INTO jobs VALUES (?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',
                        (job['id'], json.dumps(job, ensure_ascii=False)))
        self.db.execute('INSERT INTO events(job,ts,actor,action,body) VALUES (?,?,?,?,?)',
                        (job['id'], now(), actor, action, json.dumps(job, ensure_ascii=False)))

    def listing(self, query='', scope=None, state=None, since=None, until=None):
        # Fechas de calendario UTC: ambos extremos incluidos.
        for d in (since, until):
            if d is not None:
                date.fromisoformat(d)
        if since and until and since > until:
            raise ValueError('intervalo de fechas invertido')
        if state is not None and state not in STATES:
            raise ValueError('estado inválido')
        out = []
        for row in self.db.execute('SELECT body FROM jobs'):
            job = json.loads(row['body'])
            proposed = job['classification_proposal'] if job['kind'] is None else None
            if proposed:
                job = job | {k: proposed[k] for k in CLASS_FIELDS}
            if scope is not None and job['scope'] != scope:
                continue
            if state is not None and job['state'] != state:
                continue
            day = job['updated_at'][:10]
            if (since and day < since) or (until and day > until):
                continue
            searchable = ' '.join([job['title'], job['request'], job['scope'],
                                   job['summary'], job['next_step'], *job['tags']])
            if query.casefold() not in searchable.casefold():
                continue
            # Listas compactas: los detalles se obtienen con get.
            out.append({k: job[k] for k in ('id', 'title', 'kind', 'scope', 'state',
                                           'next_step', 'updated_at', 'revision')} |
                       {'classification_status': 'proposed' if proposed else 'applied'})
        return sorted(out, key=lambda x: x['updated_at'], reverse=True)[:100]

    def dispatch(self, request, *, actor):
        if actor not in ('user', 'model', 'system'):
            raise ValueError('origen inválido')
        if not isinstance(request, dict):
            raise ValueError('se espera un objeto JSON')
        op = request.get('op')
        fields = {
            'create': {'op', 'title', 'request', 'source_ref'},
            'get': {'op', 'id'},
            'list': {'op', 'query', 'scope', 'state', 'since', 'until'},
            'history': {'op', 'id'},
            'classify': {'op', 'id', 'revision', 'kind', 'scope', 'tags', 'reason'},
            'update': {'op', 'id', 'revision', 'state', 'summary', 'next_step', 'refs'},
        }
        if op not in fields or set(request) - fields[op]:
            raise ValueError('operación o campos desconocidos')
        if op == 'list':
            return self.listing(**{k: v for k, v in request.items() if k != 'op'})
        if op in ('get', 'history'):
            job = self.get(string(request.get('id'), 'id'))
            if op == 'get':
                return job
            return [dict(r) | {'body': json.loads(r['body'])} for r in self.db.execute(
                'SELECT seq,ts,actor,action,body FROM events WHERE job=? ORDER BY seq', (job['id'],))]

        # Lectura, control de versión y escritura bajo una única transacción.
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if op == 'create':
                if actor != 'user':
                    raise ValueError('la aplicación crea el trabajo desde una petición de la persona')
                stamp = now()
                job = dict(id=uuid4().hex, title=string(request.get('title'), 'title', 200),
                           request=string(request.get('request'), 'request', 16000),
                           source_ref=string(request.get('source_ref'), 'source_ref', 500),
                           kind=None, scope='', tags=[], classification_origin=None,
                           classification_locked=False, classification_proposal=None,
                           state='pendiente', summary='', next_step='', refs=[],
                           created_at=stamp, updated_at=stamp, revision=1)
            else:
                job = self.get(string(request.get('id'), 'id'))
                revision = request.get('revision')
                if type(revision) is not int or revision != job['revision']:
                    raise ValueError('revisión obsoleta: vuelve a leer el trabajo')
                if op == 'classify':
                    if request.get('kind') not in KINDS:
                        raise ValueError('tipo de trabajo inválido')
                    classification = dict(kind=request['kind'],
                        scope=string(request.get('scope'), 'scope', 200),
                        tags=strings(request.get('tags', []), 'tags'),
                        reason=string(request.get('reason'), 'reason'))
                    if actor == 'model':
                        job['classification_proposal'] = classification
                    else:
                        job.update({k: classification[k] for k in CLASS_FIELDS})
                        job['classification_origin'] = actor
                        job['classification_locked'] = actor == 'user'
                        job['classification_proposal'] = None
                else:
                    if actor == 'model':
                        raise ValueError('el modelo propone clasificación; el estado lo actualiza la aplicación')
                    if 'state' in request:
                        if request['state'] not in STATES:
                            raise ValueError('estado inválido')
                        job['state'] = request['state']
                    for field in ('summary', 'next_step'):
                        if field in request:
                            job[field] = string(request[field], field, 8000, empty=True)
                    if 'refs' in request:
                        job['refs'] = strings(request['refs'], 'refs')
                    if job['state'] == 'terminado' and not job['summary'].strip():
                        raise ValueError('un trabajo terminado necesita un resultado escrito')
                job['revision'] += 1
                job['updated_at'] = now()
            self.save(job, actor, op)
            self.db.commit()
            return job
        except Exception:
            self.db.rollback()
            raise


def strict_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError(f'clave repetida: {key}')
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=pairs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--actor', choices=('user', 'model', 'system'), default='user',
                        help='Solo el llamante de confianza elige el origen')
    args = parser.parse_args()
    store = WorkStore(args.workspace)
    try:
        result = store.dispatch(strict_json(sys.stdin.read()), actor=args.actor)
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False))
        return 0
    except (ValueError, TypeError, sqlite3.Error) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 1
    finally:
        store.close()


if __name__ == '__main__':
    sys.exit(main())
