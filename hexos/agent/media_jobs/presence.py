"""Read-only current file presence, separate from durable workflow receipts."""
import base64
import json
from pathlib import PurePosixPath
import shlex
from .. import nas_session
from .remote.file_layout import layout


REMOTE = '''import json,base64,os,stat,sys,time
paths=json.loads(base64.b64decode(sys.argv[1]))
files={}
for name,path in paths.items():
    item=dict(path=path)
    try:
        s=os.stat(path,follow_symlinks=False)
        item.update(status='present' if stat.S_ISREG(s.st_mode) else 'not_regular',size_bytes=s.st_size)
    except FileNotFoundError: item['status']='missing'
    except OSError as e: item.update(status='unknown',errno=e.errno)
    files[name]=item
print('__HEXOS_PRESENCE__'+json.dumps(dict(observed_at=time.time(),files=files)))
'''


def observe(workspace, config, job):
    if not config or job.get('config_digest') != config['digest'] or job['source']['device'] != config['device']:
        raise ValueError('Configuración distinta o ausente: no comprobar otro destino')
    run = job.get('run_id') or (job.get('completion') or {}).get('run_id')
    names = layout(job, run)
    root = PurePosixPath(config['files']['output']) / '.hexos-media'
    paths = dict(source=job['source']['path'], destination=job['source']['destination'],
                 encoded=str(root / names['output']))
    if job.get('layout_version', 1) == 2:
        paths['verified'] = str(root / names['verified'])
    payload = base64.b64encode(json.dumps(paths).encode()).decode()
    result = nas_session.execute_remote(workspace, config['device'],
        'python3 -c ' + shlex.quote(REMOTE) + ' ' + shlex.quote(payload),
        'media_presence', max_output=8000, timeout_seconds=10)
    if result.get('exit_code') != 0 or result.get('timed_out') or result.get('truncated'):
        raise ValueError('No se pudo comprobar la presencia actual por SSH')
    rows = [line.split('__HEXOS_PRESENCE__',1)[1] for line in result.get('output','').splitlines()
            if line.startswith('__HEXOS_PRESENCE__')]
    if len(rows) != 1:
        raise ValueError('Respuesta de presencia incompleta')
    observed = json.loads(rows[0])
    if set(observed['files']) != set(paths):
        raise ValueError('La observación no cubre todas las rutas')
    for name, path in paths.items():
        if observed['files'][name].get('path') != path:
            raise ValueError('Ruta observada distinta de la solicitada')
    observed['source'] = 'live_ssh_stat'
    outputs = [item for name,item in observed['files'].items() if name in ('encoded','verified')]
    observed['recorded_output_missing'] = bool(job.get('completion') and outputs and
        all(item['status'] == 'missing' for item in outputs))
    observed['note'] = 'Presencia actual; no comprueba calidad, integridad ni vuelve a validar el vídeo.'
    return observed
