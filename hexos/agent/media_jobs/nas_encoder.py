"""Encoder live opt-in. Rutas preparadas y perfil congelado, sin órdenes del LLM."""
import base64
import hashlib
import json
from pathlib import Path
import shlex

from .. import nas_session
from .contracts import SharedFailure, UncertainEffect
from .profiles import validate


class NasEncoderTransport:
    def __init__(self, workspace, device, container='HandBrake'):
        self.workspace, self.device, self.container = workspace, device, container

    def call(self, message):
        code = (Path(__file__).parent/'remote/encoder_control.py').read_text()
        payload = base64.b64encode(json.dumps(message, allow_nan=False).encode()).decode()
        command = nas_session.DOCKER + ' "$D" exec ' + shlex.quote(self.container)
        command += ' python3 -c ' + shlex.quote(code) + ' ' + shlex.quote(payload)
        result = nas_session.execute_remote(self.workspace, self.device, command, 'media_encoder',
                                            max_output=12000, payload_marker='__HEXOS_MEDIA__', timeout_seconds=20)
        if result.get('exit_code') != 0 or result.get('timed_out') or result.get('truncated'):
            raise UncertainEffect('Respuesta SSH incompleta; reconciliar la misma ejecución')
        lines = [line.split('__HEXOS_MEDIA__', 1)[1] for line in result.get('output', '').splitlines()
                 if line.startswith('__HEXOS_MEDIA__')]
        if len(lines) != 1:
            raise UncertainEffect('Falta el recibo remoto del encoder')
        response = json.loads(lines[0])
        if response.get('status') in ('control_error', 'blocked', 'unknown'):
            raise SharedFailure(response.get('error', 'Encoder bloqueado'))
        return response


class NasHandBrake:
    mode = 'live'

    def __init__(self, transport, preset_version):
        self.transport, self.preset_version = transport, dict(preset_version)

    @staticmethod
    def identity(job):
        return hashlib.sha256(f"{job['id']}:{job['attempt']}:ready".encode()).hexdigest()

    def start(self, job, key):
        if key != f"{job['id']}:{job['attempt']}:ready":
            raise ValueError('Clave de lanzamiento no corresponde a la tarea')
        profile = validate(job['profile'])
        if job['source']['device'] != self.transport.device:
            raise SharedFailure('El encoder no pertenece al dispositivo de origen')
        run_id = self.identity(job)
        source = job['staging']['container_path']
        request = dict(run_id=run_id, input=source, output=f'/output/.hexos-media/{run_id}/encoded.mkv',
                       preset_name=profile['preset']['PresetName'],
                       preset_export=dict(self.preset_version, PresetList=[profile['preset']]))
        worker = (Path(__file__).parent/'remote/encoder_worker.py').read_bytes()
        return self.transport.call(dict(operation='start', run_id=run_id, request=request,
                                        worker=base64.b64encode(worker).decode()))

    def observe(self, job):
        run_id = self.identity(job)
        if job.get('run_id') != run_id:
            raise ValueError('Identidad remota no corresponde a la tarea')
        return self.transport.call(dict(operation='observe', run_id=run_id))

    def stop(self, job, key):
        state = self.transport.call(dict(operation='stop', run_id=self.identity(job)))
        done = state.get('status') == 'finished'
        return dict(stopped=done, pending=not done and state.get('status') in ('running', 'launching'),
                    exclusive=False, run_id=self.identity(job))

    def restart(self, job, key):
        raise SharedFailure('Reinicio deshabilitado: no está demostrada la exclusividad del contenedor')
