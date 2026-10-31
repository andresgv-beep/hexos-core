"""Casos de uso del catálogo general: observar, publicar y consultar.

Solo depende de puertos inyectados, validación y presentación. No construye
comandos, no ejecuta SQL y no importa el agente conversacional.
"""
from .ports import CatalogStore, FileReader
from .validation import (roots_argument, path_argument, integer, scan_coverage,
                         extensions_argument, filters_argument)
from .presentation import bounded_page, location_page, snapshot_view, browse_view


class FileCatalog:
    def __init__(self, reader: FileReader, store: CatalogStore):
        self.reader = reader
        self.store = store

    def search(self, **kwargs):
        page = bounded_page(self.store.search(**kwargs))
        if kwargs.get('max_bytes') == 0:
            page['aviso'] = 'max_bytes=0 deja solo archivos vacíos; omítelo para no poner tope.'
        return page

    def locations(self, **kwargs):
        return location_page(self.store.locations(**kwargs))

    def browse(self, *, device=None, path='/', offset=0, limit=30):
        request = dict(operation='browse', roots=[path_argument(path)],
                       offset=integer(offset, 'offset'), limit=integer(limit, 'limit', 1, 100))
        result = self.reader(device, request)
        self.store.remember_browse(result, request['roots'][0])
        return browse_view(result, request['roots'][0])

    def index(self, *, roots, device=None):
        roots = roots_argument(roots)
        if '/' in roots:
            raise ValueError('nas.index no cruza montajes: / no indexa los volúmenes de datos. '
                             'Para buscar archivos en el NAS usa nas.find con device y extensions; '
                             'omite roots para descubrir los volúmenes automáticamente.')
        result = self.reader(device, dict(operation='index', roots=roots))
        coverage = scan_coverage(result)
        if not result.get('complete'):
            return dict(device=result['device'], observed_at=result['observed_at'], published=False,
                        coverage=coverage, note='Recorrido incompleto. Acota las raíces o corrige permisos '
                        'y repite. Se conservan los catálogos anteriores; esto no significa cero archivos.')
        return snapshot_view(self.store.publish(result, roots))

    def find(self, *, device=None, roots=None, extensions=None, min_bytes=0,
             max_bytes=None, query=None, limit=20, include_hidden=False):
        """Búsqueda recursiva en una llamada; las siguientes páginas son locales.

        Reutiliza lector, publicación y consulta. A diferencia del indexado estricto,
        permite consultar hallazgos parciales sin ocultar fallos de cobertura.
        """
        # «Sin roots» a veces llega como lista vacía; significa lo mismo.
        roots = roots_argument(roots) if roots else None
        # En una búsqueda, / representa todo el NAS: descubrir volúmenes evita
        # recorrer solo el sistema raíz, que no cruza los montajes de datos.
        if roots == ['/']:
            roots = None
        elif roots and '/' in roots:
            raise ValueError('Usa roots=["/"] para todos los volúmenes de datos, o solo raíces concretas')
        normalized = extensions_argument(extensions)
        filters_argument(min_bytes, max_bytes, query, limit)
        if type(include_hidden) is not bool:
            raise ValueError('include_hidden debe ser booleano')
        result = self.reader(device, dict(operation='find', roots=roots, skip_hidden=not include_hidden,
                                                extensions=normalized))
        actual_roots = result.get('roots', roots) or []
        if not actual_roots:
            return dict(published=False, complete=False, coverage=scan_coverage(result),
                        device=result['device'], note='No se descubrieron raíces de datos. '
                        'Consulta nas.browse e indica roots. No equivale a cero coincidencias.')
        snapshot = self.store.publish(result, actual_roots)
        page = self.search(scan_id=snapshot['scan_id'], extensions=normalized or None,
                      min_bytes=min_bytes, max_bytes=max_bytes, query=query, limit=limit)
        page['note'] += (' Búsqueda recursiva realizada. Para más páginas o cambiar filtros usa nas.search '
                         'con este scan_id; no vuelvas a recorrer el NAS. '
                         'Si complete=false, las coincidencias son parciales: comunica los límites o errores.')
        # Vacío aquí no es vacío en el NAS: lo dice el resultado, y qué hacer lo decide el modelo.
        if roots and not page['total_matches'] and max_bytes != 0:
            page['falta_por_mirar'] = ((self.other_folders(result['device'], query, actual_roots) if query else None)
                                 or 'el resto del NAS; nas.find sin roots recorre todos los volúmenes')
        return page

    def other_folders(self, device, query, roots):
        carpetas = self.store.locations(device=device, query=query, limit=20)['items']
        dentro = tuple(root.rstrip('/') + '/' for root in roots)
        return [c['path'] for c in carpetas if not (c['path'] + '/').startswith(dentro)][:5]
