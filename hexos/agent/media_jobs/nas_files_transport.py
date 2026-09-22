"""Despliegue versionado y transporte corto para workers de archivos del host."""
import base64
import io
import json
from pathlib import Path
import shlex
import zipfile

from .. import nas_session
from .contracts import FileFailure, SharedFailure, UncertainEffect


BOOTSTRAP = '''import base64,hashlib,json,os,pathlib,sys,tempfile
m=json.loads(base64.b64decode(sys.argv[1]))
b=base64.b64decode(m.pop('bundle'))
root=pathlib.Path(m['request']['config']['control'])/'file-runtime'
root.mkdir(parents=True,exist_ok=True)
archive=root/(hashlib.sha256(b).hexdigest()+'.zip')
if not archive.exists():
 fd,temp=tempfile.mkstemp(dir=str(root))
 with os.fdopen(fd,'wb') as f:
  f.write(b);f.flush();os.fsync(f.fileno())
 os.replace(temp,str(archive))
sys.path.insert(0,str(archive))
from remote.file_control import control
try: result=control(m,str(archive))
except Exception as e: result={'status':'blocked','error':str(e)}
print('__HEXOS_MEDIA_FILES__'+json.dumps(result))
'''


def bundle():
    buffer = io.BytesIO()
    root = Path(__file__).parent/'remote'
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ('__init__.py','file_common.py','file_control.py','file_worker.py','file_operations.py','file_media.py'):
            info = zipfile.ZipInfo('remote/'+name)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (root/name).read_bytes())
    return base64.b64encode(buffer.getvalue()).decode()


class NasFilesTransport:
    def __init__(self, workspace, device):
        self.workspace, self.device = workspace, device
        self.bundle = bundle()

    def call(self, message):
        envelope = dict(message, bundle=self.bundle)
        payload = base64.b64encode(json.dumps(envelope, allow_nan=False).encode()).decode()
        command = 'python3 -c '+shlex.quote(BOOTSTRAP)+' '+shlex.quote(payload)
        result = nas_session.execute_remote(self.workspace, self.device, command, 'media_files',
                                           max_output=16000, payload_marker='__HEXOS_MEDIA_FILES__', timeout_seconds=20)
        if result.get('exit_code') != 0 or result.get('timed_out') or result.get('truncated'):
            raise UncertainEffect('Respuesta SSH de archivos incompleta; conservar clave')
        lines = [line[len('__HEXOS_MEDIA_FILES__'):] for line in result['output'].splitlines()
                 if line.startswith('__HEXOS_MEDIA_FILES__')]
        if len(lines) != 1:
            raise UncertainEffect('Falta recibo de archivos')
        state = json.loads(lines[0])
        if state['status'] == 'rejected':
            raise FileFailure(state['error'])
        if state['status'] in ('blocked', 'cancelled'):
            raise SharedFailure(state['error'])
        if state['status'] == 'finished':
            return dict(state['result'], observed_at=state.get('observed_at'))
        return dict(pending=True, **state)
