"""Resolución pura de fichas. No opera sobre archivos remotos."""
from pathlib import PurePosixPath
from ..file_catalog.validation import path_argument


def movie(source):
    if source.get('kind') != 'movie':
        raise ValueError('Solo películas clasificadas explícitamente; no series ni tipos ambiguos')
    path = path_argument(source['path'])
    root = path_argument(source['library_root'])
    if root == '/' or not path.startswith(root.rstrip('/') + '/'):
        raise ValueError('Origen fuera de la biblioteca de películas')
    if not isinstance(source.get('device'), str) or not source['device'].strip():
        raise ValueError('Equipo de origen requerido')
    identity = source.get('identity', {})
    required = ('size_bytes', 'mtime_ns', 'inode', 'filesystem_id')
    if (any(type(identity.get(k)) is not int or identity[k] < 0 for k in required[:3])
            or not isinstance(identity.get('filesystem_id'), str) or not identity['filesystem_id']):
        raise ValueError('Identidad observada del catálogo incompleta')
    p = PurePosixPath(path)
    if p.suffix.lower() not in {'.mkv', '.mp4', '.avi', '.m4v', '.mov', '.ts'}:
        raise ValueError('Extensión de película no admitida')
    if p.stem.endswith('.optimizada'):
        raise ValueError('No volver a encolar una salida optimizada')
    return dict(device=source['device'], path=path, library_root=root, kind='movie',
                identity={k: identity[k] for k in required},
                destination=str(p.with_name(p.stem + '.optimizada.mkv')))
