"""Paginación del archivo visible; independiente de la ventana del modelo."""

def history_page(store, *, before=None, limit=100):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('limit debe estar entre 1 y 100')
    if before is not None and (type(before) is not int or not 1 <= before <= 2**63-1):
        raise ValueError('before debe ser un cursor positivo')
    where, values = ('WHERE rowid<?', [before]) if before is not None else ('', [])
    rows = store.db.execute('SELECT rowid AS cursor,id,ts,role,text FROM conversation ' + where +
                            ' ORDER BY rowid DESC LIMIT ?', values + [limit+1]).fetchall()
    more = len(rows) > limit
    messages = [dict(row) for row in rows[:limit]][::-1]
    return dict(messages=messages, next_before=messages[0]['cursor'] if more else None,
                has_more=more)
