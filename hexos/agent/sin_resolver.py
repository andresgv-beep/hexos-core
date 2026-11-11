"""El turno anterior acabó en una búsqueda vacía: lo dice para que no se copie.

El modelo repite lo último que hizo, haya funcionado o no: sin esto reutilizaba
en el turno siguiente la carpeta que acababa de salir vacía. Es un dato y solo
aparece cuando hace falta; qué hacer con él lo decide el modelo.
"""
import json


def bloque(store, turno):
    previo = store.db.execute("SELECT id FROM esta_ventana WHERE role='user' AND id<>? "
                              'ORDER BY rowid DESC LIMIT 1', (turno,)).fetchone()
    if previo is None:
        return ''
    fila = store.db.execute('SELECT body FROM tool_events WHERE turn_id=? ORDER BY seq DESC LIMIT 1',
                            (previo['id'],)).fetchone()
    if fila is None:
        return ''
    evento = json.loads(fila['body'])
    resultado = evento.get('result')
    if not isinstance(resultado, dict) or not resultado.get('falta_por_mirar'):
        return ''
    if resultado.get('total_matches') != 0 and resultado.get('lines') != 0:
        return ''
    falta = resultado['falta_por_mirar']
    return ('\nSIN RESOLVER (dato, no orden): tu última búsqueda salió vacía y el turno acabó ahí: ' +
            json.dumps(evento.get('arguments'), ensure_ascii=False) + '. Falta por mirar: ' +
            (', '.join(falta) if isinstance(falta, list) else falta) + '.\n')
