"""Archivos live: config del operador, recibos host y publicación de observación."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from ..file_catalog.sqlite_repository import publish_snapshot
from .contracts import SharedFailure, UncertainEffect
from .files import movie
from .nas_encoder import NasHandBrake
from .profiles import validate


class NasFiles:
    mode = 'live'

    def __init__(self, transport, config, workspace):
        self.transport, self.workspace = transport, workspace
        self.config = json.loads(json.dumps(config))
        for field in ('storage', 'output', 'control', 'ffmpeg', 'ffprobe'):
            path = Path(self.config[field])
            if not path.is_absolute() or '..' in path.parts or path == Path('/'):
                raise ValueError('Ruta de operador inválida: '+field)
        if not self.config.get('libraries'):
            raise ValueError('Configurar bibliotecas de películas antes de ejecutar')

    def _call(self, job, key, operation, *, stop=False):
        source = movie(job['source'])
        if source != job['source'] or source['device'] != self.transport.device:
            raise SharedFailure('Ficha de origen no corresponde al recurso')
        validate(job['profile'])
        if source['library_root'] not in self.config['libraries']:
            raise SharedFailure('Biblioteca no autorizada por el operador')
        # No enviar revisión/due/progreso: la petición debe ser idéntica en cada tick.
        fields = ('id','attempt','source','profile','staging','completion','validation','publication','layout_version')
        request = dict(job={k:job[k] for k in fields if k in job}, operation=operation,
                       config=self.config, run_id=NasHandBrake.identity(job))
        return self.transport.call(dict(operation='stop' if stop else 'start', request=request,
                                        action_id=hashlib.sha256(key.encode()).hexdigest()))

    def stage(self, job, key):
        return self._call(job, key, 'stage')

    def verify(self, job, key):
        return self._call(job, key, 'verify')

    def publish(self, job, key):
        return self._call(job, key, 'publish')

    def cleanup(self, job, key):
        return self._call(job, key, 'cleanup')

    def stop(self, job, key):
        return self._call(job, key, 'stop', stop=True)

    def index(self, job, key):
        receipt = self._call(job, key, 'index')
        if receipt.get('pending'):
            return receipt
        if receipt.get('verified') is not True or receipt.get('path') != job['source']['destination']:
            raise UncertainEffect('Falta observación comprobada del destino publicado')
        observed_at = datetime.fromtimestamp(receipt['observed_at'], timezone.utc).isoformat()
        path, root = receipt['path'], job['source']['library_root']
        item = dict(path=path, root=root, name=Path(path).name, media_kind='video', **receipt['identity'])
        result = dict(device=job['source']['device'], observed_at=observed_at, items=[item],
                      complete=False, stopped_reason='single_published_file', errors=[], visited_entries=1)
        scan = publish_snapshot(self.workspace, result, [root],
                                scan_id='media-'+hashlib.sha256(key.encode()).hexdigest())
        return dict(indexed=True, scan_id=scan['scan_id'], path=path)
