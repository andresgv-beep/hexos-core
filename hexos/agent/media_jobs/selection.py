"""Seleccionar identidades existentes en el catálogo y bibliotecas configuradas por el operador."""
from pathlib import Path
import sqlite3
from ..file_catalog.validation import path_argument


def resolve(workspace, scan_id, paths, libraries):
    """libraries: [{device, root, kind='movie'}], configuración externa al modelo."""
    if not isinstance(paths, list) or not 1 <= len(paths) <= 5 or len(set(paths)) != len(paths):
        raise ValueError('Seleccionar de una a cinco rutas distintas')
    database = Path(workspace)/'nas_files.sqlite'
    db = sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        sources = []
        for path in paths:
            path = path_argument(path)
            row = db.execute('SELECT f.*,s.device FROM files f JOIN scans s ON f.scan_id=s.id '
                             'WHERE f.scan_id=? AND f.path=?', (scan_id, path)).fetchone()
            if row is None:
                raise ValueError('Ruta no observada en el catálogo elegido')
            roots = [path_argument(lib['root']) for lib in libraries
                     if lib.get('kind') == 'movie' and lib.get('device') == row['device']]
            roots = [r for r in roots if r != '/' and path.startswith(r.rstrip('/')+'/')]
            if not roots:
                raise ValueError('Origen no pertenece a una biblioteca configurada como películas')
            sources.append(dict(path=path, device=row['device'], kind='movie', library_root=max(roots,key=len),
                                identity={k:row[k] for k in ('size_bytes','mtime_ns','inode','filesystem_id')}))
        return sources
    finally:
        db.close()
