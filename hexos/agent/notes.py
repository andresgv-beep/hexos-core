"""Notas del núcleo: texto que la persona quiere conservar, releer y retocar.

Tres decisiones que conviene saber antes de leer el código:

- Editar NO destruye. Cada versión queda en note_revisions, así que un retoque
  desafortunado del modelo se puede recuperar. Mismo criterio que el histórico
  por clave de HERA y que el registro de eventos de las fichas.
- Guardar se comprueba releyendo. La función devuelve outcome='hecho' solo
  después de volver a leer de la base lo que dice haber escrito.
- No hay borrado. El modelo puede descartar una nota, que la saca de la lista,
  pero el texto sigue ahí. Borrar de verdad es cosa de la persona.
"""
import json
from uuid import uuid4

from .work import now, string, strings

ESTADOS = ('pendiente', 'hecha', 'descartada')
TITULO, CUERPO = 200, 20000


def initialize(store):
    store.db.executescript('''
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            title TEXT NOT NULL, body TEXT NOT NULL, state TEXT NOT NULL,
            favorite INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL,
            tags TEXT NOT NULL, source_turn TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS note_revisions (
            seq INTEGER PRIMARY KEY, note TEXT NOT NULL REFERENCES notes(id),
            ts TEXT NOT NULL, revision INTEGER NOT NULL, actor TEXT NOT NULL,
            title TEXT NOT NULL, body TEXT NOT NULL);
    ''')


def _fila(row):
    nota = dict(row)
    nota['favorite'] = bool(nota['favorite'])
    nota['tags'] = json.loads(nota['tags'])
    return nota


def get(store, note_id):
    row = store.db.execute('SELECT * FROM notes WHERE id=?', (note_id,)).fetchone()
    if row is None:
        raise ValueError('nota inexistente')
    return _fila(row)


def history(store, note_id):
    get(store, note_id)
    return [dict(r) for r in store.db.execute(
        'SELECT ts, revision, actor, title, body FROM note_revisions WHERE note=? ORDER BY seq', (note_id,))]


def listing(store, query='', state=None, favorite=None, limit=50):
    if state is not None and state not in ESTADOS:
        raise ValueError('estado inválido; usa ' + ', '.join(ESTADOS))
    if not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ValueError('limit debe estar entre 1 y 200')
    filas = []
    for row in store.db.execute('SELECT * FROM notes ORDER BY updated_at DESC'):
        nota = _fila(row)
        # Una nota descartada no desaparece, pero deja de estorbar: solo sale
        # cuando se pide su estado a propósito.
        if state is None and nota['state'] == 'descartada':
            continue
        if state is not None and nota['state'] != state:
            continue
        if favorite is not None and nota['favorite'] is not bool(favorite):
            continue
        if query and query.casefold() not in (nota['title'] + ' ' + nota['body'] +
                                              ' ' + ' '.join(nota['tags'])).casefold():
            continue
        filas.append(dict(nota, body=nota['body'][:300], truncated=len(nota['body']) > 300))
        if len(filas) >= limit:
            break
    return filas


def _releer(store, note_id, title, body):
    """La prueba de que se guardó es volver a leerlo, no que no saltara un error."""
    row = store.db.execute('SELECT title, body FROM notes WHERE id=?', (note_id,)).fetchone()
    if row is None:
        return 'no_se_sostuvo', 'la nota no está en el almacén después de guardarla'
    if row['title'] != title or row['body'] != body:
        return 'no_se_sostuvo', 'lo releído no coincide con lo que se pretendía guardar'
    return 'hecho', 'releído del almacén: ' + str(len(body)) + ' caracteres bajo ' + repr(title)


def save(store, turn_id, *, id=None, title=None, body=None, tags=None, revision=None, actor='model'):
    if id is None:
        if title is None or body is None:
            raise ValueError('una nota nueva necesita title y body')
        nota = dict(id=uuid4().hex, created_at=now(), title=string(title, 'title', TITULO),
                    body=string(body, 'body', CUERPO), state='pendiente', favorite=0,
                    revision=0, tags=strings(tags or [], 'tags'), source_turn=turn_id)
        creada = True
    else:
        nota = get(store, id)
        if revision is not None and revision != nota['revision']:
            raise ValueError('la nota cambió desde que la leíste (va por la revisión ' +
                             str(nota['revision']) + '); léela otra vez antes de retocarla')
        if title is not None:
            nota['title'] = string(title, 'title', TITULO)
        if body is not None:
            nota['body'] = string(body, 'body', CUERPO)
        if tags is not None:
            nota['tags'] = strings(tags, 'tags')
        creada = False
    nota['revision'] += 1
    nota['updated_at'] = now()
    store.db.execute(
        'INSERT INTO notes VALUES (:id,:created_at,:updated_at,:title,:body,:state,:favorite,'
        ':revision,:tags,:source_turn) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,'
        'title=excluded.title, body=excluded.body, tags=excluded.tags, revision=excluded.revision',
        dict(nota, favorite=int(nota['favorite']), tags=json.dumps(nota['tags'], ensure_ascii=False)))
    store.db.execute('INSERT INTO note_revisions(note,ts,revision,actor,title,body) VALUES (?,?,?,?,?,?)',
                     (nota['id'], nota['updated_at'], nota['revision'], actor, nota['title'], nota['body']))
    store.db.commit()
    outcome, evidencia = _releer(store, nota['id'], nota['title'], nota['body'])
    return dict(nota, created=creada, outcome=outcome, checked=evidencia,
                note='La versión anterior no se pierde: queda en el histórico de la nota.')


def mark(store, note_id, *, state=None, favorite=None):
    if state is None and favorite is None:
        raise ValueError('di qué cambiar: state, favorite o ambos')
    nota = get(store, note_id)
    if state is not None:
        if state not in ESTADOS:
            raise ValueError('estado inválido; usa ' + ', '.join(ESTADOS))
        nota['state'] = state
    if favorite is not None:
        if not isinstance(favorite, bool):
            raise ValueError('favorite es sí o no')
        nota['favorite'] = favorite
    nota['updated_at'] = now()
    store.db.execute('UPDATE notes SET state=?, favorite=?, updated_at=? WHERE id=?',
                     (nota['state'], int(nota['favorite']), nota['updated_at'], note_id))
    store.db.commit()
    releida = get(store, note_id)
    coincide = releida['state'] == nota['state'] and releida['favorite'] == nota['favorite']
    return dict(releida, outcome='hecho' if coincide else 'no_se_sostuvo',
                checked='releído del almacén: estado ' + releida['state'] +
                        (', en favoritos' if releida['favorite'] else ', fuera de favoritos'))


def resolve_ref(store, args):
    """El id de la nota, venga por id o por el número que la persona tiene delante.

    `n` es la posición en la última lista, que es lo único que ella ve: pedirle al
    modelo que maneje un id de 32 caracteres que no puede ver es pedirle que lo
    invente o que lo vuelque en pantalla, y hacía las dos cosas.
    """
    if args.get('id'):
        return args['id']
    posicion = args.get('n')
    if not isinstance(posicion, int):
        raise ValueError('di qué nota: id, o n con el número de la lista')
    filas = listing(store, limit=200)
    if not 1 <= posicion <= len(filas):
        raise ValueError('no hay una nota número ' + str(posicion) + '; hay ' + str(len(filas)))
    return filas[posicion - 1]['id']


def dispatch(store, name, args, turn_id):
    if name == 'note.list':
        filas = listing(store, args.get('query', ''), args.get('state'),
                        args.get('favorite'), args.get('limit', 50))
        # Sin ids ni fechas: se le pidió por texto que no los volcara y los volcó
        # igual, con «Creada: 2026-09-14T19:51:58.563781+00:00» incluido. Lo que no
        # ve no lo puede pegar. Para abrir una basta el número que ella tiene delante.
        return dict(notes=[dict(n=i, title=f['title'], state=f['state'],
                                **({'favorite': True} if f['favorite'] else {}))
                           for i, f in enumerate(filas, 1)],
                    total=len(filas),
                    note='La lista está en su pantalla. Di cuántas hay y sus títulos. '
                         'Para abrirle una usa note_show con n, el número de esta lista.')
    if name == 'note.get':
        return dict(get(store, args['id']),
                    note='Las versiones anteriores están en el histórico de la nota.')
    if name == 'note.save':
        return save(store, turn_id, id=args.get('id'), title=args.get('title'),
                    body=args.get('body'), tags=args.get('tags'), revision=args.get('revision'))
    if name == 'note.show':
        # Devuelve la nota entera a propósito: el id viaja en la traza y la
        # interfaz la abre, y de paso el modelo ve lo que acaba de enseñar.
        return dict(get(store, resolve_ref(store, args)), shown=True,
                    note='Ya está abierta en su pantalla; no hace falta repetir el contenido.')
    if name == 'note.hide':
        # No toca el almacén: su único efecto es la pantalla. Sin id, todas.
        note_id = resolve_ref(store, args) if (args.get('id') or args.get('n')) else None
        if note_id:
            get(store, note_id)
        return dict(hidden=note_id or 'todas',
                    note='Cerrada en su pantalla.' if note_id else 'Cerradas todas en su pantalla.')
    if name == 'note.mark':
        return mark(store, args['id'], state=args.get('state'), favorite=args.get('favorite'))
    raise ValueError('operación de notas no soportada')
