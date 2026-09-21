"""Lecturas actuales de directorios y recursos compartidos; no consultas de archivos."""
from .validation import roots_argument, integer, filters_argument
from .presentation import directory_page


class DirectoryCatalog:
    def __init__(self, reader, store):
        self.reader, self.store = reader, store

    def directories(self, *, device=None, query='', roots=None, exact=False,
                    include_hidden=False, limit=30, offset=0):
        filters_argument(0, None, query, limit)
        if not isinstance(query, str):
            raise ValueError('query debe ser texto; omítelo para listar directorios')
        integer(offset, 'offset')
        if type(exact) is not bool or type(include_hidden) is not bool:
            raise ValueError('exact e include_hidden deben ser booleanos')
        roots = roots_argument(roots) if roots is not None else None
        if roots == ['/']:
            roots = None
        elif roots and '/' in roots:
            raise ValueError('Usa / sola para descubrir todos los volúmenes')
        result = self.reader(device, dict(operation='directories', roots=roots, query=query,
                                          exact=exact, skip_hidden=not include_hidden))
        self.store.remember_locations(result)
        result.update(query=query, exact=exact, listing_kind='directories')
        snapshot_id = self.store.publish_directories(result)
        return dict(directory_page(result, limit, offset, query=query, exact=exact),
                    snapshot_id=snapshot_id, listing_kind='directories')

    def shares(self, *, device=None, limit=100, offset=0):
        integer(limit, 'limit', 1, 100)
        integer(offset, 'offset')
        result = self.reader(device, dict(operation='shares'))
        self.store.remember_locations(result)
        result.update(listing_kind='shares')
        snapshot_id = self.store.publish_directories(result)
        return dict(directory_page(result, limit, offset, shares=True), snapshot_id=snapshot_id, listing_kind='shares')

    def page(self, *, snapshot_id, limit=100, offset=0):
        integer(limit, 'limit', 1, 100)
        integer(offset, 'offset')
        result = self.store.read_directories(snapshot_id)
        return dict(directory_page(result, limit, offset, query=result.get('query', ''),
                                   exact=result.get('exact', False), shares=result['listing_kind']=='shares'),
                    snapshot_id=snapshot_id, listing_kind=result['listing_kind'], network_used=False)
