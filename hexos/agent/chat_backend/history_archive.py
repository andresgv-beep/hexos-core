"""Paginación del archivo visible; independiente de la ventana del modelo."""
import json


def _documentos(store, mensajes):
    """Los documentos que creó cada turno, pegados a su respuesta: tras recargar, la tarjeta
    con «Ver» y «Descargar» sigue en el chat (18/11: sin ella no se sabía si estaba hecho)."""
    pendientes = None
    for mensaje in mensajes:
        if mensaje['role'] == 'user':
            filas = store.db.execute(
                "SELECT body FROM tool_events WHERE turn_id=? AND body LIKE '%document.create%' ORDER BY seq",
                (mensaje['id'],)).fetchall()
            pendientes = []
            for (cuerpo,) in filas:
                paso = json.loads(cuerpo)
                hecho = paso.get('result')
                if paso.get('tool') == 'document.create' and not paso.get('failed') and isinstance(hecho, dict) \
                        and hecho.get('id'):
                    pendientes.append(dict(id=hecho['id'], name=hecho.get('name'), kind=hecho.get('kind'),
                                           bytes=hecho.get('bytes')))
        elif pendientes:
            mensaje['documents'] = pendientes
            pendientes = None
    return mensajes


def history_page(store, *, before=None, limit=100):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('limit debe estar entre 1 y 100')
    if before is not None and (type(before) is not int or not 1 <= before <= 2**63-1):
        raise ValueError('before debe ser un cursor positivo')
    where, values = ('WHERE rowid<?', [before]) if before is not None else ('', [])
    rows = store.db.execute('SELECT rowid AS cursor,id,ts,role,text FROM esta_ventana ' + where +
                            ' ORDER BY rowid DESC LIMIT ?', values + [limit+1]).fetchall()
    more = len(rows) > limit
    messages = _documentos(store, [dict(row) for row in rows[:limit]][::-1])
    return dict(messages=messages, next_before=messages[0]['cursor'] if more else None,
                has_more=more)
