"""Control remoto acotado, ejecutado dentro del contenedor; nunca recibe shell."""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path('/config/.hexos-media')


def atomic(path, data):
    fd, name = tempfile.mkstemp(prefix=path.name+'.', dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    directory = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def snapshot(root, run_id):
    path = root/'state.json'
    if not path.exists():
        launch = root/'launch.json'
        if launch.exists() and time.time()-json.loads(launch.read_text())['at'] > 30:
            return dict(run_id=run_id, status='unknown', error='Intención sin recibo de arranque')
        return dict(run_id=run_id, status='launching')
    state = json.loads(path.read_text())
    with (root/'run.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            alive = False
        except BlockingIOError:
            alive = True
    if state['status'] in ('running', 'launching') and not alive:
        state.update(status='unknown', error='Worker ausente; requiere reconciliación, no relanzar')
    return state


def control(message):
    op, run_id = message['operation'], message['run_id']
    if op not in ('start', 'observe', 'stop') or not re.fullmatch('[a-f0-9]{64}', run_id):
        raise ValueError('Operación o identidad inválida')
    root = ROOT/'runs'/run_id
    root.mkdir(parents=True, exist_ok=True)
    # Serializa preparación, lanzamiento y cancelación. No protege la inferencia.
    with (root/'control.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if op == 'stop':
            if not (root/'cancel').exists():
                atomic(root/'cancel', b'cancel')
            # Si nunca hubo intención de arrancar, el marcador impide un start tardío.
            if not (root/'launch.json').exists():
                return dict(run_id=run_id, status='finished', exit_code=130)
        if op == 'start':
            request = message['request']
            if request['run_id'] != run_id:
                raise ValueError('Recibo ajeno')
            for field, prefix in (('input', '/storage/.hexos-media/'), ('output', '/output/.hexos-media/')):
                path = Path(request[field])
                if '..' in path.parts or not str(path).startswith(prefix):
                    raise ValueError('Ruta fuera del espacio de tareas')
            encoded = json.dumps(request, sort_keys=True, allow_nan=False).encode()
            request_path = root/'request.json'
            if request_path.exists() and request_path.read_bytes() != encoded:
                raise ValueError('Clave reutilizada con otra petición')
            if (root/'cancel').exists():
                return dict(run_id=run_id, status='finished', exit_code=130)
            if not request_path.exists():
                atomic(request_path, encoded)
            if not (root/'launch.json').exists():
                source = base64.b64decode(message['worker'])
                digest = hashlib.sha256(source).hexdigest()
                worker = ROOT/('worker-'+digest+'.py')
                if not worker.exists():
                    atomic(worker, source)
                # No volver a ejecutar Popen si cae el controlador después de esta intención.
                atomic(root/'launch.json', json.dumps(dict(at=time.time(), worker=digest)).encode())
                subprocess.Popen([sys.executable, str(worker), str(request_path)],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        result = snapshot(root, run_id)
        if op == 'stop' and result['status'] in ('running', 'launching'):
            if time.time()-(root/'cancel').stat().st_mtime > 30:
                result.update(status='unknown', error='La parada no ha sido confirmada')
        return result


if __name__ == '__main__':
    try:
        result = control(json.loads(base64.b64decode(sys.argv[1])))
    except (OSError, ValueError, KeyError) as exc:
        result = dict(error=str(exc), status='control_error')
    print('__HEXOS_MEDIA__'+json.dumps(result, allow_nan=False))
