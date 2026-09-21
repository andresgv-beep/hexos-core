"""Presentación factual de listados simples, sin reinterpretación por el modelo."""
from .file_requests import explicit_directory_read, explicit_share_read


def file_listing_reply(text, trace, *, continuation=False):
    reads = [step for step in trace if not step.get('failed')]
    if not reads or any(step.get('tool') not in ('nas.directories', 'nas.shares', 'nas.directory_page') for step in reads):
        return None
    last = reads[-1]
    result = last.get('result') or {}
    device = result.get('device')
    if not device or 'items' not in result or 'error' in result:
        return None
    shares = last['tool'] == 'nas.shares' or result.get('listing_kind') == 'shares'
    if shares and not continuation:
        if not explicit_share_read(text, [device]):
            return None
    elif not shares and not continuation and not explicit_directory_read(text, [device]):
        return None
    # No mezclar búsquedas distintas ni equipos. El modelo conserva esos turnos compuestos.
    identity = lambda step: tuple((step.get('result') or {}).get(k)
                                 for k in ('device', 'query', 'exact', 'snapshot_id'))
    # Distintas páginas vuelven a leer: la fecha puede cambiar, el alcance no.
    if any(identity(step) != identity(last) for step in reads):
        return None
    items = {}
    for step in reads:
        for item in (step.get('result') or {}).get('items', []):
            items[(item.get('name'), item['path'])] = item
    if shares:
        heading = f"Carpetas compartidas configuradas en {device}:"
    elif items:
        match = 'llamadas' if result.get('exact') else 'con el texto'
        heading = f"Carpetas {match} «{result['query']}» encontradas en {device} ({len(items)}):"
        if continuation and result.get('roots'):
            heading += '\nDentro de: ' + ', '.join(result['roots']) + '.'
    else:
        heading = f"No he encontrado una carpeta llamada «{result['query']}» en las rutas revisadas de {device}."
    lines = [heading]
    for item in items.values():
        path = item['path'].replace('`', '\\`').replace('\n', ' ')
        access = (' — ' + item['access']) if shares else ''
        name = item.get('name', '').replace('\n', ' ')
        label = (name + ': ') if shares else ''
        lines.append(f"- {label}`{path}`{access}")
    if not result.get('complete'):
        lines.append('\nLa lectura es parcial: ' + str(result.get('error_count', 0)) +
                     ' incidencias de lectura' + (' y se alcanzó un límite del recorrido' if result.get('stopped_reason') else '') +
                     '. No permite descartar otras coincidencias en las rutas no revisadas.')
    if result.get('excludes_hidden'):
        lines.append('\nSe excluyeron las carpetas ocultas e internas del sistema.')
    if result.get('next_offset') is not None:
        lines.append(f"\nMostradas {len(items)} de {result['total_matches']}; quedan más resultados por consultar.")
    if shares:
        lines.append('\nEl acceso indicado corresponde al usuario SSH; los permisos SMB pueden ser distintos.')
    return lines[0] + ('\n\n' + '\n'.join(lines[1:]).lstrip('\n') if len(lines) > 1 else '')
