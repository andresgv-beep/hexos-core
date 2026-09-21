"""Continuaciones de un listado observado: conservan alcance, filtros y procedencia.

La traza persistente es la fuente; no se infieren rutas del texto del modelo.
No resuelve peticiones nuevas ni referencias sin una consulta reciente compatible.
"""
import json
import posixpath
import re
import unicodedata


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.casefold()) if not unicodedata.combining(c))


def listing_followup(store, turn_id, text):
    message = normalized(text).strip(' .!?¿¡')
    simple = re.fullmatch(r'(?:muestrame|muestra|ensename|ensena|listame|lista)\s+(?:las\s+|los\s+)?'
                          r'(?:todas|todos)(?:\s+(?:socio|por favor))?', message)
    scoped = re.match(r'^(?:(?:muestrame|muestra|listame|lista)\s+)?(?:todas|todos)\s+(?:las|los)\s+que\s+', message)
    if not simple and not scoped:
        return None
    current = store.db.execute('SELECT rowid FROM conversation WHERE id=?', (turn_id,)).fetchone()
    if not current:
        return None
    users = store.db.execute("SELECT id,text FROM conversation WHERE role='user' AND rowid<? "
                             'ORDER BY rowid DESC LIMIT 8', (current[0],)).fetchall()
    candidates = []
    for user in users:
        # No rescatar listados a través de un cambio de tema.
        if not re.search(r'carpeta|directorio|compartid|muestra|lista|todas|todos|acceso', normalized(user['text'])):
            break
        for row in store.db.execute('SELECT body FROM tool_events WHERE turn_id=? ORDER BY seq DESC', (user['id'],)):
            try:
                event = json.loads(row['body'])
            except (TypeError, ValueError):
                continue
            result = event.get('result') or {}
            if (event.get('tool') in ('nas.directories', 'nas.shares', 'nas.directory_page')
                    and not event.get('failed') and isinstance(result, dict) and 'items' in result
                    and result.get('device') and 'error' not in result):
                candidates.append(event)
    if not candidates:
        return None
    if scoped:
        matching = []
        for event in candidates:
            roots = event.get('arguments', {}).get('roots') or event['result'].get('roots') or []
            if any(re.search(r'\b' + re.escape(normalized(posixpath.basename(root))) + r'\b', message)
                   for root in roots if posixpath.basename(root)):
                matching.append(event)
        # La referencia debe apuntar a un único equipo y conjunto de raíces.
        scopes = {(e['result']['device'], tuple(e.get('arguments', {}).get('roots') or e['result'].get('roots') or [])) for e in matching}
        if len(scopes) != 1:
            return None
        candidates = matching
    event = candidates[0]
    result = event['result']
    if result.get('snapshot_id'):
        return dict(tool='nas.directory_page', arguments=dict(snapshot_id=result['snapshot_id'], offset=0, limit=100))
    # Compatibilidad con observaciones previas a las páginas persistentes:
    # repetir la misma consulta una sola vez y guardar ahora su snapshot.
    if event['tool'] == 'nas.directory_page':
        return None
    args = dict(event.get('arguments') or {}, device=result['device'], offset=0, limit=100)
    return dict(tool=event['tool'], arguments=args)
