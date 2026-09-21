"""Validación pura de rutas, extensiones y filtros; sin E/S."""
import posixpath
import re

def integer(value, name, minimum=0, maximum=2**63 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(name + ': entero entre ' + str(minimum) + ' y ' + str(maximum))
    return value


def path_argument(value):
    if not isinstance(value, str) or not value.startswith('/') or '\x00' in value or len(value) > 4096:
        raise ValueError('La ruta debe ser absoluta, sin NUL y de hasta 4096 caracteres')
    if '..' in value.split('/'):
        raise ValueError('La ruta no puede contener ..')
    return '/' + posixpath.normpath(value).lstrip('/')


def roots_argument(roots):
    if not isinstance(roots, list) or not 1 <= len(roots) <= 16:
        raise ValueError('roots debe ser una lista de entre 1 y 16 rutas absolutas')
    return sorted(set(path_argument(root) for root in roots), key=lambda root: (len(root), root))


def extensions_argument(extensions):
    if extensions is None:
        return []
    if not isinstance(extensions, list) or not 1 <= len(extensions) <= 32:
        raise ValueError('extensions debe ser una lista de 1 a 32 extensiones: ["mkv", "mp3"]')
    normalized = []
    for value in extensions:
        if not isinstance(value, str) or not re.fullmatch(r'\.?[A-Za-z0-9]{1,16}', value):
            raise ValueError('Cada extensión debe ser literal, sin comodines: mkv, .MP4, avi, mp3')
        normalized.append(value.lower().lstrip('.'))
    return sorted(set(normalized))


def filters_argument(min_bytes, max_bytes, query, limit):
    integer(min_bytes, 'min_bytes')
    if max_bytes is not None:
        integer(max_bytes, 'max_bytes', min_bytes)
    integer(limit, 'limit', 1, 100)
    if query is not None and (not isinstance(query, str) or len(query) > 500):
        raise ValueError('query debe ser texto de hasta 500 caracteres')


def parents_within_root(path, root):
    directory = posixpath.dirname(path)
    while directory == root or directory.startswith(root.rstrip('/') + '/'):
        yield directory
        if directory == root or directory == '/':
            break
        directory = posixpath.dirname(directory)


def scan_coverage(result):
    return {key: result[key] for key in ('complete', 'errors', 'stopped_reason', 'visited_entries',
                                        'skipped', 'filesystems', 'auto_discovered', 'excludes_hidden',
                                        'indexed_extensions') if key in result}
