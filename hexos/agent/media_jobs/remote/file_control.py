"""Control de acciones host: lock, intención durable y cancelación por ficha."""
import fcntl
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from .file_common import save


def snapshot(root):
    state_path = root/'state.json'
    with (root/'worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            alive = False
        except BlockingIOError:
            alive = True
    state = json.loads(state_path.read_text()) if state_path.exists() else dict(status='launching')
    if not alive and state['status'] == 'running':
        return dict(status='blocked', error='Supervisor de archivos ausente; revisar recibos y temporales')
    if state['status'] == 'launching' and (root/'launch.json').exists():
        if time.time()-json.loads((root/'launch.json').read_text())['at'] > 30:
            return dict(status='blocked', error='Intención de archivos sin confirmación de arranque')
    return state


def control(message, archive):
    request = message['request']
    job_id = request['job']['id']
    if not re.fullmatch('[a-f0-9]{32}', job_id) or not re.fullmatch('[a-f0-9]{64}', request['run_id']):
        raise ValueError('Identidad de ficha inválida')
    job_root = Path(request['config']['control'])/'file-jobs'/job_id
    job_root.mkdir(parents=True, exist_ok=True)
    with (job_root/'control.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if message['operation'] == 'stop':
            if not (job_root/'cancel.json').exists():
                save(job_root/'cancel.json', dict(at=time.time()))
            states = [snapshot(path.parent) for path in job_root.glob('actions/*/launch.json')]
            pending = any(s['status'] in ('running', 'launching') for s in states)
            if pending and time.time()-json.loads((job_root/'cancel.json').read_text())['at'] > 30:
                return dict(status='blocked', error='No se confirma parada del worker de archivos')
            if any(s['status'] == 'blocked' for s in states):
                return dict(status='blocked', error='Acción de archivos incierta; reconciliar antes de cancelar')
            return dict(status='finished', result=dict(stopped=not pending, pending=pending,
                        effects=[s['result'] for s in states if s.get('result')]))
        if (job_root/'cancel.json').exists():
            return dict(status='cancelled', error='La ficha está cancelada')
        action_id = message['action_id']
        if not re.fullmatch('[a-f0-9]{64}', action_id) or request['operation'] not in ('stage','verify','publish','index','cleanup'):
            raise ValueError('Operación inválida')
        root = job_root/'actions'/action_id
        root.mkdir(parents=True, exist_ok=True)
        path = root/'request.json'
        if path.exists() and json.loads(path.read_text()) != request:
            raise ValueError('La clave pertenece a otra acción')
        if not path.exists():
            save(path, request)
        if not (root/'launch.json').exists():
            save(root/'launch.json', dict(at=time.time()))
            code = 'import sys;sys.path.insert(0,sys.argv[1]);from remote.file_worker import run;run(sys.argv[2])'
            subprocess.Popen([sys.executable, '-c', code, archive, str(path)],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        return snapshot(root)
