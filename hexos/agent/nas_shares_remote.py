"""Lectura autónoma de recursos SMB configurados en Synology, sin sudo ni cambios."""
import base64
import configparser
import json
import os
import sys

MARKER = '__HEXOS_FILES_V1__'
CONFIG_PATH = '/etc/samba/smb.share.conf'


def collect(request):
    items, errors = [], []
    config = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        with open(CONFIG_PATH) as source:
            content = source.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            raise ValueError('configuration_size_limit')
        config.read_string(content)
    except (OSError, ValueError, configparser.Error) as exc:
        return dict(items=[], complete=False, errors=[dict(reason='share_configuration_unavailable',
                    errno=getattr(exc, 'errno', None))], source=CONFIG_PATH)
    for name in config.sections():
        if config.has_option(name, 'include'):
            errors.append(dict(name=name, reason='included_configuration_not_read'))
        if name.casefold() == 'global':
            continue
        path = config.get(name, 'path', fallback='').strip()
        if not path.startswith('/') or '%' in path:
            errors.append(dict(name=name, reason='unresolved_share_path'))
            continue
        readable, access_errno = True, None
        try:
            # Solo abrir: no enumerar el contenido de cada recurso.
            with os.scandir(path):
                pass
        except OSError as exc:
            readable, access_errno = False, exc.errno
        items.append(dict(name=name, path=path, kind='directory', size_bytes=None,
                          readable=readable, access_errno=access_errno))
    return dict(items=items, complete=not errors, errors=errors, source=CONFIG_PATH)


if __name__ == '__main__':
    result = collect(json.loads(sys.argv[1]))
    payload = json.dumps(result, ensure_ascii=True, separators=(',', ':')).encode('ascii')
    print(MARKER + base64.b64encode(payload).decode('ascii'))
