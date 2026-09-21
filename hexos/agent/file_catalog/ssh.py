"""Adaptador de lectura SSH: identidad, acceso y protocolo remoto. Sin SQL."""
import base64
import binascii
import json
from pathlib import Path
import shlex

from .. import hosts, nas_session
from ..nas_files_remote import MARKER

def remote_command(request):
    script = 'nas_shares_remote.py' if request['operation'] == 'shares' else 'nas_files_remote.py'
    source = (Path(__file__).parent.parent / script).read_text()
    # Código fijo y un único argumento JSON citado; ninguna ruta es código shell.
    return 'python3 -c ' + shlex.quote(source) + ' ' + shlex.quote(json.dumps(request, ensure_ascii=True))


def observe(workspace, device, request):
    device = device or hosts.only_device(workspace)
    device = hosts.match(workspace, device) or device
    if not hosts.credentials(workspace, device):
        try:
            located = hosts.resolve(workspace, device)
        except ValueError:
            located = None
        raise hosts.AccessNeeded(device, located)
    raw = nas_session.execute_remote(workspace, device, remote_command(request), 'files',
                                     elevated=False, max_output=17 * 1024 * 1024,
                                     payload_marker=MARKER)
    if raw.get('timed_out') or raw.get('truncated') or raw.get('exit_code') != 0:
        raise ValueError('No se completó la lectura de archivos del NAS. Requiere python3 y permisos '
                         'de lectura del usuario SSH; no se publicó ningún catálogo. '
                         'exit_code=' + str(raw.get('exit_code')) + ', timed_out=' + str(raw.get('timed_out')))
    lines = [line[len(MARKER):] for line in raw['output'].splitlines() if line.startswith(MARKER)]
    if len(lines) != 1:
        raise ValueError('Respuesta de archivos inválida; no se publicó ningún catálogo')
    try:
        result = json.loads(base64.b64decode(lines[0], validate=True))
    except (ValueError, TypeError, binascii.Error) as exc:
        raise ValueError('Respuesta de archivos incompleta; no se publicó ningún catálogo') from exc
    result.update(device=device, observed_at=raw['observed_at'])
    return result
