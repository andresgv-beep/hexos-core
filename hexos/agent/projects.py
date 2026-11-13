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

import os
import re
import unicodedata
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
