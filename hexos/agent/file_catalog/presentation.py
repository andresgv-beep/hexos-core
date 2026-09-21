"""Vistas de resultados para el chat; el repositorio conserva los registros completos."""
import json
from copy import deepcopy

PAGE_CHARS = 6500

def bounded_page(result):
    """El límite de filas es un máximo; las rutas largas reducen la página.

    Nunca corta una ruta ni descarta filas: next_offset apunta a la primera no
    entregada. Los metadatos completos permanecen en SQLite.
    """
    result = deepcopy(result)
    result['note'] = SEARCH_NOTE
    result['items'] = [{key: item[key] for key in ('path', 'name', 'root', 'size_bytes')}
                       for item in result['items']]
    # Los totales globales y la cobertura se conservan; detalle de muchas raíces
    # no debe consumir todo el presupuesto antes de los archivos.
    result['root_count'] = len(result['roots'])
    result['roots'] = result['roots'][:16]
    result['totals'] = result['totals'][:16]
    result['coverage'].pop('filesystems', None)
    errors = result['coverage'].get('errors', [])
    result['coverage'].update(errors=errors[:5], error_count=len(errors))
    while len(json.dumps(result, ensure_ascii=False)) > PAGE_CHARS and len(result['items']) > 1:
        result['items'].pop()
    result['next_offset'] = (result['offset'] + len(result['items'])
                             if result['offset'] + len(result['items']) < result['total_matches'] else None)
    result['returned_count'] = len(result['items'])
    headline = ('Coincidencias en el catálogo filtrado: ' + str(result['total_matches']) +
                '. Archivos entregados en esta página: ' + str(result['returned_count']) + '. ' +
                ('Hay más páginas; siguiente offset=' + str(result['next_offset']) + '. '
                 if result['next_offset'] is not None else 'No quedan más páginas. ') +
                ('Cobertura parcial del NAS: estos números no incluyen las rutas no leídas.'
                 if not result['complete'] else 'Recorrido completo dentro del alcance indicado.'))
    return dict(headline=headline, **result)


SEARCH_NOTE = 'Página de un catálogo estable, no lectura actual del NAS. Rangos inclusivos en bytes; sin máximo si se omite. GB=1000000000 bytes; GiB=1073741824. total_matches cuenta TODO el catálogo filtrado, no esta página. La primera página ya contiene los más grandes de todo lo encontrado. complete=false se refiere al recorrido: paginar NO recupera carpetas sin permiso ni omitidas. Las páginas se ajustan por longitud: usa next_offset y conserva filters. video se basa en extensión; no demuestra que merezca conversión.'
LOCATIONS_NOTE = 'Directorios observados anteriormente; no inventario completo ni permisos actuales. Sin query se listan todas las rutas recordadas. Para buscar carpetas ahora o si no constan aquí usa nas.directories. Para listar recursos compartidos usa nas.shares sin patrón. Para buscar archivos dentro de una biblioteca usa sus rutas como roots de nas.find. Cero observaciones no demuestra ausencia.'
SNAPSHOT_NOTE = 'Catálogo de metadatos, sin leer vídeos. Tamaños lógicos, no ahorro recuperable; filesystem_id identifica un sistema de archivos, no un disco físico. No se siguen enlaces ni montajes anidados: indica esos montajes como raíces propias.'


def location_page(result):
    result = deepcopy(result)
    offset = result.pop('offset', 0)
    while len(json.dumps(result['items'], ensure_ascii=False)) > 5000 and len(result['items']) > 1:
        result['items'].pop()
    end = offset + len(result['items'])
    result['next_offset'] = end if end < result['total_matches'] else None
    result['note'] = LOCATIONS_NOTE
    return result


def snapshot_view(result):
    return dict(result, note=SNAPSHOT_NOTE)


def directory_page(result, limit, offset, *, query='', exact=False, shares=False):
    unique = {item['path']: item for item in result['items']} if not shares else {
        (item['name'], item['path']): item for item in result['items']}
    items = sorted(unique.values(), key=lambda item: (item['path'], item.get('name', '')))
    keys = ('name', 'path', 'readable', 'access_errno') if shares else ('name', 'path')
    page = [{key: item[key] for key in keys} for item in items[offset:offset + limit]]
    if shares:
        for item in page:
            item['access'] = ('Lectura disponible por SSH' if item.pop('readable') else
                              'Sin acceso de lectura por SSH (error ' + str(item['access_errno']) + ')')
            item.pop('access_errno')
    while len(json.dumps(page, ensure_ascii=False)) > 5000 and len(page) > 1:
        page.pop()
    errors = result.get('errors', [])
    end = offset + len(page)
    return dict(device=result['device'], observed_at=result['observed_at'],
                source=result.get('source', 'live_directory_search'), network_used=True,
                complete=result['complete'], total_is_exact=result['complete'],
                total_matches=len(items), returned_count=len(page), items=page,
                offset=offset, next_offset=end if end < len(items) else None,
                query=query, exact=exact, case_sensitive=False,
                errors=errors[:5], error_count=len(errors),
                stopped_reason=result.get('stopped_reason'),
                roots=result.get('roots', [])[:16], excludes_hidden=result.get('excludes_hidden', False),
                skipped=result.get('skipped', {}),
                note=('Recursos compartidos configurados; distingue lectura disponible y rutas sin acceso por SSH, no permisos SMB. '
                      if shares else 'Búsqueda actual de CARPETAS, incluidas vacías; no de archivos. ') +
                     'Una lectura parcial no demuestra ausencia. Muestra nombres y rutas sin explicar herramientas. '
                     'Para más páginas usa nas.directory_page con snapshot_id y next_offset; no repitas el recorrido.')


def browse_view(result, path):
    result = deepcopy(result)
    # Navegar necesita rutas y tipos, no repetir root/inode/mtime/media_kind por
    # cada directorio. El índice conserva esos datos para el trabajo con archivos.
    result['items'] = [{key: item[key] for key in ('path', 'kind', 'size_bytes')}
                       for item in result['items']]
    result['path'] = path
    result['note'] = ('Una carpeta, sin recursión. size_bytes de directorios no es su ocupación. '
                      'Rutas de usuario primero; ocultas e internas @ después, sin excluirlas. '
                      'next_offset indica otra página. Para entrar, usa una ruta de tipo directory como path. '
                      'La paginación vuelve a leer el directorio; puede cambiar entre páginas.')
    return result
