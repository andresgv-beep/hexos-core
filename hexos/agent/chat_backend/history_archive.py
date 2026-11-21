"""Paginación del archivo visible; independiente de la ventana del modelo."""
import json


def _documentos(store, mensajes):
    """Los documentos que creó cada turno, pegados a su respuesta: tras recargar, la tarjeta
    con «Ver» y «Descargar» sigue en el chat (18/11: sin ella no se sabía si estaba hecho)."""
    pendientes = None
    for mensaje in mensajes:
        if mensaje['role'] == 'user':
            filas = store.db.execute(
                "SELECT body FROM tool_events WHERE turn_id=? AND (body LIKE '%document.create%' OR body LIKE '%file.list%') ORDER BY seq",
                (mensaje['id'],)).fetchall()
            pendientes = []
            for (cuerpo,) in filas:
                paso = json.loads(cuerpo)
                hecho = paso.get('result')
                if paso.get('failed') or not isinstance(hecho, dict) or not hecho.get('id'):
                    continue
                if paso.get('tool') == 'file.list' and hecho.get('status') == 'shown':
                    pendientes.append({k: hecho.get(k) for k in
                                       ('id', 'name', 'kind', 'bytes', 'status', 'source', 'viewable', 'preview')})
                elif paso.get('tool') == 'document.create':
                    pendientes.append(dict(id=hecho['id'], name=hecho.get('name'), kind=hecho.get('kind'),
                                           bytes=hecho.get('bytes')))
        elif pendientes:
            mensaje['documents'] = pendientes
            pendientes = None
    return mensajes


def _limpieza(store):
    """Hasta qué mensaje llegaba la conversación cuando la persona pulsó «Limpiar contexto»."""
    from .context import LIMPIEZA
    from .persistence import clave
    fila = store.db.execute('SELECT value FROM agent_state WHERE key=?', (clave(store, LIMPIEZA),)).fetchone()
    try:
        return int(fila[0]) if fila else 0
    except (TypeError, ValueError):
        return 0


def history_page(store, *, before=None, limit=100):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('limit debe estar entre 1 y 100')
    if before is not None and (type(before) is not int or not 1 <= before <= 2**63-1):
        raise ValueError('before debe ser un cursor positivo')
    # La primera página empieza tras la última limpieza. Antes solo se vaciaba la pantalla
    # y al recargar, o desde el móvil, volvía la conversación entera (18/11: «limpias
    # contexto pero la conversación sigue en el chat»). Lo de antes no se borra: queda
    # detrás de «anteriores», como cualquier página vieja.
    where, values = ('WHERE rowid<?', [before]) if before is not None else ('', [])
    limpieza = _limpieza(store) if before is None else 0
    if limpieza:
        where, values = 'WHERE rowid>?', [limpieza]
    rows = store.db.execute('SELECT rowid AS cursor,id,ts,role,text FROM esta_ventana ' + where +
                            ' ORDER BY rowid DESC LIMIT ?', values + [limit+1]).fetchall()
    more = len(rows) > limit
    messages = _documentos(store, [dict(row) for row in rows[:limit]][::-1])
    if more:
        return dict(messages=messages, next_before=messages[0]['cursor'], has_more=True)
    if limpieza and store.db.execute('SELECT 1 FROM esta_ventana WHERE rowid<=? LIMIT 1', (limpieza,)).fetchone():
        return dict(messages=messages, next_before=limpieza + 1, has_more=True, cleared=True)
    return dict(messages=messages, next_before=None, has_more=False)
