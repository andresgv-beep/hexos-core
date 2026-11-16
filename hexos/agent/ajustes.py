"""Ajustes que la persona pone desde la interfaz: servicios externos y sus claves.

Las claves viven en `api_keys.json`, aparte de work.sqlite por lo mismo que las
contraseñas de los equipos (`hosts.secrets`): el almacén de la conversación se
vuelca, se grepea y se lee para armar el prompt. Una clave no sale de aquí hacia
la interfaz ni hacia el modelo: la interfaz solo sabe si está puesta y cómo acaba.
"""
import json
from pathlib import Path
import re

from .hosts import _write_private
from .web import SIN_REINTENTO


# Servicios que se pueden enchufar. Añadir uno es una entrada aquí y su función en
# el módulo que lo usa (para `busqueda`, `web._BUSCADORES`).
PROVEEDORES = {
    'tavily': dict(name='Tavily', kind='busqueda', site='https://app.tavily.com',
                   note='Búsqueda web para agentes. El plan gratuito da 1.000 búsquedas al mes, '
                        'sin tarjeta; al agotarse deja de contestar hasta el mes siguiente.',
                   placeholder='tvly-…', prefix='tvly-'),
}
# Sin espacios ni caracteres de control: una clave pegada con un salto de línea
# rompería la cabecera HTTP en la que viaja.
CLAVE = re.compile(r'[\x21-\x7e]{8,512}')


def keys_path(workspace):
    return Path(workspace) / 'api_keys.json'


def _claves(workspace):
    path = keys_path(workspace)
    if not path.exists():
        return {}
    if path.stat().st_mode & 0o077:
        raise ValueError('api_keys.json es legible por otros; corrige con chmod 600')
    return json.loads(path.read_text())


def _proveedor(identificador):
    if not isinstance(identificador, str) or identificador not in PROVEEDORES:
        raise ValueError('servicio desconocido: ' + repr(identificador))
    return identificador


def clave(workspace, proveedor):
    """La clave guardada de un servicio, o None. Solo para quien hace la llamada."""
    return _claves(workspace).get(_proveedor(proveedor))


def buscador(workspace):
    """El buscador con clave que usa `web.search`, o None si no hay ninguno puesto."""
    claves = _claves(workspace)
    for identificador, ficha in PROVEEDORES.items():
        if ficha['kind'] == 'busqueda' and claves.get(identificador):
            return {'id': identificador, 'key': claves[identificador]}
    return None


def listado(workspace):
    """Lo que enseña la ventana de ajustes. Nunca lleva una clave entera."""
    claves = _claves(workspace)
    proveedores = []
    for identificador, ficha in PROVEEDORES.items():
        guardada = claves.get(identificador)
        proveedores.append(dict(ficha, id=identificador, configured=bool(guardada),
                                hint='…' + guardada[-4:] if guardada else None))
    activo = buscador(workspace)
    return {'web': {'search': PROVEEDORES[activo['id']]['name'] if activo else 'DuckDuckGo',
                    'providers': proveedores}}


def guardar(workspace, proveedor, valor):
    """Guarda la clave de un servicio; con None la quita. Devuelve el listado nuevo."""
    proveedor = _proveedor(proveedor)
    claves = _claves(workspace)
    if valor is None:
        claves.pop(proveedor, None)
    else:
        if not isinstance(valor, str) or not CLAVE.fullmatch(valor.strip()):
            raise ValueError('la clave no tiene forma de clave: entre 8 y 512 caracteres, sin espacios')
        ficha = PROVEEDORES[proveedor]
        if not valor.strip().startswith(ficha['prefix']):
            # El 16/11 se guardó un texto de 44 caracteres que no era de Tavily y solo se supo
            # al probarlo, con un «no es válida» que no decía por qué.
            raise ValueError('eso no parece una clave de ' + ficha['name'] + ': las suyas empiezan por «' +
                             ficha['prefix'] + '». No se ha guardado')
        claves[proveedor] = valor.strip()
    _write_private(keys_path(workspace), claves)
    return listado(workspace)


def probar(workspace, proveedor, search):
    """Una búsqueda real con la clave guardada, para saber si vale antes de usarla."""
    proveedor = _proveedor(proveedor)
    guardada = clave(workspace, proveedor)
    if not guardada:
        raise ValueError('no hay clave guardada de ' + PROVEEDORES[proveedor]['name'])
    try:
        resultado = search('noticias de hoy', limit=1, proveedor={'id': proveedor, 'key': guardada})
    except ValueError as exc:
        # Lo que sigue a la causa va dirigido al modelo, no a quien está en Ajustes.
        raise ValueError(str(exc).split('; ' + SIN_REINTENTO)[0]) from exc
    return {'ok': True, 'provider': proveedor, 'results': resultado['count']}
