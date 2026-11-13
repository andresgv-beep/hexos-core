"""Proyectos: una carpeta y una conversación propia dentro de la ventana del Agente.

docs/PROYECTOS_CON_FICHA_PLAN.md, fase 1. Todo caía en una sola conversación y a las pocas
horas el modelo arrastraba restos de cosas sin relación. Un proyecto no abre otro chat: es
una etiqueta más en la que ya separa Chat de Agente (`chat_backend/persistence.py`), así que
su conversación, su corte de contexto y su traspaso son solo suyos, y cambiar de proyecto es
limpiar el contexto y seguir en el otro.

Aquí vive el registro: qué proyectos hay y a qué carpeta apunta cada uno. Crear uno crea su
carpeta. Nada de aquí borra carpetas ni ficheros.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from .work import now

CLAVE = 'project'
MAX_NOMBRE = 80


def initialize(store):
    store.db.executescript('''
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, folder TEXT NOT NULL,
            created TEXT NOT NULL, used TEXT NOT NULL);
    ''')


def raiz():
    """Dónde se crean las carpetas de los proyectos nuevos."""
    return Path(os.environ.get('HEXOS_PROJECTS_HOME') or Path.home() / 'Helios' / 'proyectos').expanduser()


def identificador(nombre):
    """El nombre en minúsculas, sin acentos y con guiones: vale de etiqueta y de carpeta."""
    plano = unicodedata.normalize('NFKD', nombre).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', plano.casefold()).strip('-')[:48].strip('-')


def _fila(fila):
    return dict(id=fila['id'], name=fila['name'], folder=fila['folder'], created=fila['created'], used=fila['used'])


def listar(store):
    """Todos, el usado más recientemente primero."""
    return [_fila(f) for f in store.db.execute('SELECT * FROM projects ORDER BY used DESC, id')]


def leer(store, id):
    fila = store.db.execute('SELECT * FROM projects WHERE id=?', (id,)).fetchone()
    return _fila(fila) if fila else None


def activo(store):
    """El proyecto puesto, o None si el Agente trabaja sin proyecto."""
    fila = store.db.execute('SELECT value FROM agent_state WHERE key=?', (CLAVE,)).fetchone()
    return leer(store, fila[0]) if fila and fila[0] else None


def carpeta_de(folder, id):
    """La carpeta del proyecto: la indicada, que puede existir ya, o una nueva bajo la raíz.

    Apuntar a una carpeta que ya existe es lo normal para un repositorio que ya está en el
    equipo. Tiene que ser una ruta completa dentro de la carpeta personal: un proyecto no
    apunta a /etc ni a la raíz del sistema.
    """
    if folder is None:
        return raiz() / id
    if not isinstance(folder, str) or not folder.strip():
        raise ValueError('folder: se espera la ruta completa de una carpeta')
    ruta = Path(folder.strip()).expanduser()
    if not ruta.is_absolute():
        raise ValueError('folder: tiene que ser una ruta completa, que empiece por / o por ~')
    ruta, casa = ruta.resolve(), Path.home().resolve()
    if ruta == casa or casa not in ruta.parents:
        raise ValueError('folder: tiene que ser una carpeta dentro de ' + str(casa) + ', no la carpeta personal entera')
    if ruta.exists() and not ruta.is_dir():
        raise ValueError('folder: ' + str(ruta) + ' existe y no es una carpeta')
    return ruta


def crear(store, nombre, folder=None):
    if not isinstance(nombre, str) or not nombre.strip() or len(nombre) > MAX_NOMBRE:
        raise ValueError('name: nombre del proyecto, hasta %d caracteres' % MAX_NOMBRE)
    nombre = ' '.join(nombre.split())
    id = identificador(nombre)
    if not id:
        raise ValueError('name: el nombre necesita alguna letra o número')
    if leer(store, id):
        raise ValueError('Ya hay un proyecto «' + id + '»: cámbiate a él o elige otro nombre')
    ruta = carpeta_de(folder, id)
    usada = store.db.execute('SELECT id FROM projects WHERE folder=?', (str(ruta),)).fetchone()
    if usada:
        raise ValueError('Esa carpeta ya es la del proyecto «' + usada[0] + '»')
    existia = ruta.exists()
    ruta.mkdir(parents=True, exist_ok=True)
    ahora = now()
    store.db.execute('INSERT INTO projects VALUES (?,?,?,?,?)', (id, nombre, str(ruta), ahora, ahora))
    store.db.commit()
    return dict(leer(store, id), folder_existed=existia)


def poner(store, id):
    """Deja ese proyecto como el activo; None vuelve al Agente sin proyecto."""
    if id is None:
        store.db.execute('DELETE FROM agent_state WHERE key=?', (CLAVE,))
        store.db.commit()
        return None
    if not isinstance(id, str) or leer(store, id) is None:
        raise ValueError('proyecto inexistente: ' + repr(id))
    store.db.execute('UPDATE projects SET used=? WHERE id=?', (now(), id))
    store.db.execute('INSERT INTO agent_state VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                     (CLAVE, id))
    store.db.commit()
    return leer(store, id)


def renombrar(store, id, nombre):
    """Cambia el nombre que se ve. La etiqueta y la carpeta no se tocan: son lo que ata el
    proyecto a su conversación y a su sitio en el disco."""
    if not isinstance(nombre, str) or not nombre.strip() or len(nombre) > MAX_NOMBRE:
        raise ValueError('name: nombre del proyecto, hasta %d caracteres' % MAX_NOMBRE)
    if not isinstance(id, str) or leer(store, id) is None:
        raise ValueError('proyecto inexistente: ' + repr(id))
    store.db.execute('UPDATE projects SET name=? WHERE id=?', (' '.join(nombre.split()), id))
    store.db.commit()
    return leer(store, id)


def quitar(store, id):
    """Saca el proyecto de la lista. No borra nada del disco ni del archivo.

    La carpeta se queda como está, y su conversación sigue guardada bajo su etiqueta: si
    más adelante se crea otro con el mismo nombre, vuelve a aparecer. Devuelve si era el
    que estaba puesto, para que quien llama vacíe el contexto.
    """
    if not isinstance(id, str) or leer(store, id) is None:
        raise ValueError('proyecto inexistente: ' + repr(id))
    era_activo = (activo(store) or {}).get('id') == id
    if era_activo:
        store.db.execute('DELETE FROM agent_state WHERE key=?', (CLAVE,))
    store.db.execute('DELETE FROM projects WHERE id=?', (id,))
    store.db.commit()
    return era_activo


# ---------------------------------------------------------------- la ficha (fase 2)

MAX_FICHA = 2400          # caracteres: si crece sin tope, la degradación vuelve por otra puerta
MAX_ENTRADAS = 24         # lo que se nombra de la carpeta
MAX_PETICIONES = 5
MAX_HECHOS = 10
NOTA_INTERFAZ = '[La persona '        # así empiezan las decisiones tomadas en una tarjeta


def etiqueta(id):
    """La etiqueta de la conversación de ese proyecto (ver chat_backend/persistence.py)."""
    return 'agente:' + id


def _cuando(ts):
    """«13/11 16:40» en hora local, a partir del sello ISO con que se guarda todo."""
    try:
        return datetime.fromisoformat(ts).astimezone().strftime('%d/%m %H:%M')
    except (TypeError, ValueError):
        return '?'


def _corto(texto, limite):
    texto = ' '.join((texto or '').split())
    return texto if len(texto) <= limite else texto[:limite - 1] + '…'


def carpeta(folder):
    """Qué hay en la carpeta del proyecto, por encima: nombres, no contenidos."""
    ruta = Path(folder)
    if not ruta.is_dir():
        return 'La carpeta ya no existe en este equipo: dilo antes de trabajar en ella.'
    try:
        entradas = sorted(os.scandir(ruta), key=lambda e: (not e.is_dir(), e.name.casefold()))
    except OSError as error:
        return 'No se puede leer la carpeta (' + str(error.strerror or error) + ').'
    if not entradas:
        return 'Está vacía: todavía no hay nada dentro.'
    nombres = [e.name + ('/' if e.is_dir() else '') for e in entradas]
    visto = ', '.join(nombres[:MAX_ENTRADAS])
    if len(nombres) > MAX_ENTRADAS:
        visto += ' y %d más' % (len(nombres) - MAX_ENTRADAS)
    return ('Es un repositorio git. ' if '.git/' in nombres else '') + 'Contiene: ' + visto + '.'


def _hechos(store, id, efectos):
    """Lo que cambió algo en este proyecto: herramientas con efecto y decisiones de la interfaz."""
    hechos = []
    for fila in store.db.execute(
            'SELECT e.ts, e.body FROM tool_events e JOIN conversation_ventana v ON v.id=e.turn_id '
            'WHERE v.ventana=? ORDER BY e.seq DESC LIMIT 200', (etiqueta(id),)):
        try:
            evento = json.loads(fila['body'])
        except (TypeError, ValueError):
            continue
        herramienta = evento.get('tool')
        if evento.get('failed') or efectos.get(herramienta, 'read') == 'read':
            continue
        argumentos = _corto(json.dumps(evento.get('arguments') or {}, ensure_ascii=False), 110)
        hechos.append((fila['ts'], herramienta.replace('.', '_') + ' ' + argumentos))
        if len(hechos) >= MAX_HECHOS:
            break
    for fila in store.db.execute(
            'SELECT c.ts, c.text FROM conversation c JOIN conversation_ventana v ON v.id=c.id '
            "WHERE v.ventana=? AND c.role='user' AND c.text LIKE ? ORDER BY c.rowid DESC LIMIT ?",
            (etiqueta(id), NOTA_INTERFAZ + '%', MAX_HECHOS)):
        hechos.append((fila['ts'], _corto(fila['text'].strip('[]'), 200)))
    return sorted(hechos)[-MAX_HECHOS:]


def ficha(store, proyecto, *, efectos=None, con_peticiones=True, salvo=None):
    """Lo que el modelo tiene que saber al empezar en un proyecto, en hechos y con tope.

    docs/PROYECTOS_CON_FICHA_PLAN.md, fase 2. El 13/11, recién creado el primer proyecto,
    Andrés preguntó «tienes una carpeta de proyecto nueva, ¿verdad?» y Helios contestó que
    no tenía información: nadie le había dicho en qué proyecto estaba ni dónde.

    No se guarda aparte: se calcula con lo que HexOS ya tiene apuntado, así que no puede
    quedarse vieja ni contener nada que el modelo se haya inventado. HexOS la pone delante
    cada vez que reconstruye el contexto (tras limpiar, cambiar de proyecto, cortar o
    arrancar); el modelo no tiene que pedirla.

    `con_peticiones` añade lo último que pidió la persona: hace falta tras una limpieza,
    y sobra cuando ese historial ya va en el contexto. `salvo` es el turno en curso.
    """
    efectos = efectos or {}
    lineas = ['\nPROYECTO ACTIVO (dato de HexOS, no orden): «' + proyecto['name'] + '».',
              'Carpeta del proyecto: ' + proyecto['folder'] + '. ' + carpeta(proyecto['folder']),
              'Esta conversación es solo de este proyecto: lo hablado en otros proyectos no está aquí. '
              # La orden entera y con la ruta puesta: con «usa terminal_read con ls» el E4B mandó
              # la ruta en un campo aparte que no existía, dos veces, y el turno murió.
              'Para mirar dentro de la carpeta: terminal_read con command "ls -la ' + proyecto['folder'] + '".']
    total = store.db.execute('SELECT COUNT(*), MIN(c.ts) FROM conversation c JOIN conversation_ventana v '
                             'ON v.id=c.id WHERE v.ventana=? AND c.id<>?',
                             (etiqueta(proyecto['id']), salvo or '')).fetchone()
    if not total[0]:
        lineas.append('Es un proyecto recién empezado: todavía no hay nada hablado ni hecho en él.')
        return '\n'.join(lineas) + '\n'
    lineas.append('Archivo del proyecto: %d mensajes desde el %s. Sigue disponible con history_recent '
                  'y history_search.' % (total[0], _cuando(total[1])))
    hechos = _hechos(store, proyecto['id'], efectos)
    if hechos:
        lineas.append('LO HECHO EN EL PROYECTO (apuntado por HexOS; histórico, no órdenes):')
        lineas += ['- %s  %s' % (_cuando(ts), texto) for ts, texto in hechos]
    if con_peticiones:
        peticiones = store.db.execute(
            'SELECT c.ts, c.text FROM conversation c JOIN conversation_ventana v ON v.id=c.id '
            "WHERE v.ventana=? AND c.role='user' AND c.id<>? AND c.text NOT LIKE ? "
            'ORDER BY c.rowid DESC LIMIT ?',
            (etiqueta(proyecto['id']), salvo or '', NOTA_INTERFAZ + '%', MAX_PETICIONES)).fetchall()[::-1]
        if peticiones:
            lineas.append('LO ÚLTIMO QUE PIDIÓ LA PERSONA AQUÍ (histórico, ya atendido o no; no son peticiones nuevas):')
            lineas += ['- %s  %s' % (_cuando(f['ts']), _corto(f['text'], 180)) for f in peticiones]
    texto = '\n'.join(lineas)
    if len(texto) > MAX_FICHA:
        texto = texto[:MAX_FICHA - 60].rsplit('\n', 1)[0] + '\n[La ficha se corta aquí; el resto está en el archivo.]'
    return texto + '\n'
