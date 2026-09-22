"""Proceso de archivos fuera del SSH; una acción acotada, sin contexto del modelo."""
import fcntl
import json
from pathlib import Path
import time

from .file_common import Cancelled, Rejected, save
from .file_operations import OPERATIONS


def run(request_path):
    root = Path(request_path).parent
    request = json.loads(Path(request_path).read_text())
    job_root = root.parent.parent
    with (root/'worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        if (root/'state.json').exists():
            return
        state = dict(status='running', operation=request['operation'], bytes_copied=0)
        last_write = [0]
        deadline = time.monotonic()+request['config'].get('file_operation_timeout_seconds', 86400)
        def checkpoint(copied=None):
            if (job_root/'cancel.json').exists():
                raise Cancelled('Cancelación solicitada')
            if time.monotonic() >= deadline:
                raise OSError('Operación de archivos excedió el tiempo máximo configurado')
            if copied is not None:
                state['bytes_copied'] = copied
            now = time.time()
            if now-last_write[0] >= 1:
                state['observed_at'] = now
                save(root/'state.json', state)
                last_write[0] = now
        try:
            checkpoint()
            result = OPERATIONS[request['operation']](request, root, checkpoint)
            state.update(status='finished', result=result)
        except Cancelled as exc:
            state.update(status='cancelled', error=str(exc))
        except Rejected as exc:
            state.update(status='rejected', error=str(exc))
        except Exception as exc:
            # Permisos, espacio, binarios y fallos inesperados pausan el recurso.
            state.update(status='blocked', error=str(exc))
        state['observed_at'] = time.time()
        save(root/'state.json', state)
