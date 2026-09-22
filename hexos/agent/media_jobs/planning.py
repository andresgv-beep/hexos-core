"""Preparación desde catálogo observado: selección explícita o top numérico global."""
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from ..file_catalog.validation import filters_argument, extensions_argument
from .selection import resolve
from .files import movie
from .store import JobStore


def ensure(db):
    db.execute('CREATE TABLE IF NOT EXISTS media_plans (id TEXT PRIMARY KEY, created REAL NOT NULL, body TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS media_service (resource TEXT PRIMARY KEY, at REAL NOT NULL, body TEXT NOT NULL)')


def health(store, config, now):
    ensure(store.db)
    row = store.db.execute('SELECT * FROM media_service WHERE resource=?', (config['resource'],)).fetchone()
    if not row or now-row['at'] > 90:
        return dict(ready=False, reason='Servicio multimedia sin heartbeat reciente')
    state = json.loads(row['body'])
    return dict(ready=state.get('ready') is True and state.get('config_digest') == config['digest'], **{'service':state})


def prepare(workspace, config, args, *, now=None):
    now = time.time() if now is None else now
    profiles = {p['id']:p for p in config['profiles']}
    if args['profile_id'] not in profiles:
        raise ValueError('Perfil no configurado; consulta media.options')
    scan_id = args['scan_id']
    database = Path(workspace)/'nas_files.sqlite'
    db = sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        scan = db.execute('SELECT * FROM scans WHERE id=?',(scan_id,)).fetchone()
        if not scan or scan['device'] != config['device']:
            raise ValueError('El catálogo no pertenece al recurso configurado')
        paths = args.get('paths')
        if paths is not None and any(k in args for k in ('count','root','query','min_bytes','max_bytes','extensions')):
            raise ValueError('Usa paths exactos o count con filtros, no ambos')
        if paths is None:
            count = args.get('count', 1)
            if type(count) is not int or not 1 <= count <= 5:
                raise ValueError('count debe estar entre 1 y 5')
            minimum, maximum = args.get('min_bytes', 0), args.get('max_bytes')
            filters_argument(minimum, maximum, args.get('query'), count)
            extensions = extensions_argument(args.get('extensions'))
            if json.loads(scan['coverage']).get('complete') is not True:
                raise ValueError('No se puede certificar el top de un recorrido parcial; acota y repite la búsqueda')
            roots = config['files']['libraries']
            root = args.get('root')
            if root is not None:
                if root not in roots:
                    raise ValueError('Raíz fuera de las bibliotecas configuradas')
                roots = [root]
            scanned = json.loads(scan['roots'])
            if any(not any(r == s or r.startswith(s.rstrip('/')+'/') for s in scanned) for r in roots):
                raise ValueError('La búsqueda no cubre todas las bibliotecas seleccionadas')
            # Las raíces de la consulta se fijan antes de LIMIT, no página a página.
            clauses = ' OR '.join('substr(path,1,?)=?' for _ in roots)
            params = []
            for r in roots:
                prefix = r.rstrip('/')+'/'
                params.extend((len(prefix),prefix))
            query = args.get('query', '').casefold()
            candidates = db.execute('SELECT path,size_bytes FROM files WHERE scan_id=? AND ('+clauses+') ORDER BY size_bytes DESC,path',
                                    [scan_id]+params)
            paths = []
            for row in candidates:
                if row['size_bytes'] < minimum or (maximum is not None and row['size_bytes'] > maximum):
                    continue
                path = Path(row['path'])
                if extensions and path.suffix.lower().lstrip('.') not in extensions:
                    continue
                if path.suffix.lower() not in {'.mkv','.mp4','.avi','.m4v','.mov','.ts'} or path.stem.endswith('.optimizada'):
                    continue
                if query and query not in path.name.casefold():
                    continue
                paths.append(str(path))
                if len(paths) == count:
                    break
            if not paths:
                raise ValueError('No hay películas coincidentes en la selección')
        libraries = [dict(device=config['device'],root=r,kind='movie') for r in config['files']['libraries']]
        sources = [movie(s) for s in resolve(workspace, scan_id, paths, libraries)]
    finally:
        db.close()
    body = dict(scan_id=scan_id, observed_at=scan['observed_at'], sources=sources, profile=profiles[args['profile_id']],
                resource=config['resource'], config_digest=config['digest'])
    plan_id = hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    store = JobStore(workspace)
    try:
        ensure(store.db)
        store.db.execute('INSERT INTO media_plans VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET created=excluded.created',
                         (plan_id,now,json.dumps(body,ensure_ascii=False)))
    finally:
        store.close()
    return dict(plan_id=plan_id, count=len(sources), profile_id=args['profile_id'],
                scope=dict(observed_at=scan['observed_at'],roots=json.loads(scan['roots']),coverage=json.loads(scan['coverage'])), files=[
        dict(path=s['path'],destination=s['destination'],size_bytes=s['identity']['size_bytes']) for s in sources],
        note='Lote preparado; todavía no se ha copiado ni convertido nada. media.start lo encola.')


def start(workspace, config, plan_id, *, now=None):
    now = time.time() if now is None else now
    store = JobStore(workspace)
    try:
        ensure(store.db)
        row = store.db.execute('SELECT * FROM media_plans WHERE id=?',(plan_id,)).fetchone()
        if not row:
            raise ValueError('Plan no preparado; usa media.prepare')
        plan = json.loads(row['body'])
        old = store.db.execute('SELECT id FROM media_batches WHERE request_key=?',('plan:'+plan_id,)).fetchone()
        if old:
            return dict(batch_id=old['id'], status='already_queued', batch=summary(store.batch(old['id'])))
        if plan['config_digest'] != config['digest'] or now-row['created'] > 1800:
            raise ValueError('Plan caducado o configuración cambiada; preparar de nuevo desde una búsqueda actual')
        if not health(store, config, now)['ready']:
            raise ValueError('El servicio y su revisor interno no están disponibles; lote no lanzado')
        batch = store.create(plan['sources'],plan['profile'],plan['resource'],'plan:'+plan_id,now,
                             mode='live',require_review=True,config_digest=config['digest'])
        return dict(batch_id=batch['id'],status='queued',batch=summary(batch),
                    note='Encolado; no equivale a copiado, convertido ni publicado. Consulta media.job o media.jobs.')
    finally:
        store.close()


def summary(batch):
    return dict(id=batch['id'],paused=batch['paused'],mode=batch['mode'],jobs=[
        dict(id=j['id'],state=j['state'],path=j['source']['path'],destination=j['source']['destination'],
             due=j['due'],error=j.get('error')) for j in batch['jobs']])
