"""Comprueba nombres explícitos del turno antes de ejecutar búsquedas.

No interpreta peticiones abiertas ni resuelve referencias del historial. Solo
protege formas inequívocas «carpeta llamada HNF9» o nombres entre comillas.
"""
import re

NAMED = re.compile(
    r'\b(?P<kind>carpeta|directorio|archivo)\s+(?:que\s+se\s+)?llama(?:da|do)?\s+'
    r'(?:"(?P<double>[^"\n]+)"|«(?P<angle>[^»\n]+)»|`(?P<code>[^`\n]+)`|'
    r'(?P<plain>[\w][\w.\-]*?)(?=[.!?]?\s*$|\s+(?:en|del|dentro|por)\b))', re.I)


def explicit_directory_read(text, devices):
    """Atajo solo para un mandato completo con nombre y un equipo inequívocos.

    Rechaza prosa adicional, raíces explícitas, preguntas y nombres aproximados.
    El resto sigue pasando por la decisión normal del modelo.
    """
    if len(devices) != 1:
        return None
    matches = list(NAMED.finditer(text))
    if len(matches) != 1 or matches[0].group('kind').casefold() == 'archivo':
        return None
    match = matches[0]
    device = re.escape(devices[0])
    scope = r'(?:por\s+todo\s+el\s+|en\s+(?:el\s+)?)(?:nas\s+)?' + device
    prefix = r'\s*(?:busca|búscame|buscame|encuentra)\s+(?:' + scope + r'\s+)?(?:una?\s+|la\s+|el\s+)?'
    suffix = r'\s*(?:' + scope + r')?\s*[.!]?\s*'
    if not re.fullmatch(prefix, text[:match.start()], re.I) or not re.fullmatch(suffix, text[match.end():], re.I):
        return None
    literal = next(match.group(key) for key in ('double', 'angle', 'code', 'plain') if match.group(key))
    return dict(tool='nas.directories', arguments=dict(device=devices[0], query=literal, exact=True))


def validate_file_request(text, tool, arguments):
    if tool not in ('nas.find', 'nas.search', 'nas.directories'):
        return
    matches = list(NAMED.finditer(text))
    if len(matches) != 1:
        return
    match = matches[0]
    # Una petición expresamente aproximada puede ampliar la consulta.
    if re.search(r'\b(?:similar|parecid\w*|aproximad\w*)\b', text, re.I):
        return
    literal = next(match.group(key) for key in ('double', 'angle', 'code', 'plain') if match.group(key))
    directory = match.group('kind').casefold() in ('carpeta', 'directorio')
    expected_tool = 'nas.directories' if directory else 'nas.find'
    if (directory and tool != 'nas.directories') or (not directory and tool == 'nas.directories'):
        raise ValueError('La petición actual nombra ' + match.group('kind') + ' ' + repr(literal) +
                         '. Usa ' + expected_tool + ' con query=' + repr(literal) + '; no cambies el tipo de objeto.')
    query = arguments.get('query')
    if not isinstance(query, str) or query.casefold() != literal.casefold():
        raise ValueError('El nombre literal del mensaje ACTUAL es ' + repr(literal) +
                         '. Repite la búsqueda con query=' + repr(literal) +
                         ', sin sustituirlo por nombres del historial. No hace falta confirmación.')


def explicit_share_read(text, devices):
    """Listado simple de recursos compartidos de un solo equipo explícito."""
    if len(devices) != 1:
        return None
    device = devices[0]
    target = r'(?:\s+(?:en|del)\s+(?:el\s+)?' + re.escape(device) + r')?'
    listing = (r'\s*(?:(?:qué|que)\s+carpetas\s+compartidas\s+puedes\s+ver' + target +
               r'\??\s*(?:l[ií]stame\s+todas)?|(?:lista|l[ií]stame|listar)\s+(?:todas\s+)?'
               r'(?:las\s+)?carpetas\s+compartidas(?:\s+disponibles)?' + target + r')\s*[.!?]?\s*')
    if re.fullmatch(listing, text, re.I):
        return dict(tool='nas.shares', arguments=dict(device=device))
    return None
