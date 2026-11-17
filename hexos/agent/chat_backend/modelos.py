"""Los modelos entre los que se puede elegir.

HexOS arrancaba con un modelo y solo sabía cargarlo y descargarlo. Con dos en el equipo
(uno que ve y charla, otro que programa) cambiar de uno a otro era editar el servicio y
reiniciarlo. Aquí se declaran en un fichero y se elige en caliente: el que estaba se
descarga y el nuevo se carga en su sitio. No conviven: los dos no caben a la vez.

El fichero es JSON:

    {"modelos": [
      {"id": "gemma4-26b", "nombre": "Gemma 4 26B", "hnf": "/ruta/modelo.hnf",
       "plantilla": "/ruta/chat_template.jinja", "ctx": 40960},
      {"id": "qwen36-35b", "nombre": "Qwen3.6 35B", "hnf": "…", "plantilla": "…", "ctx": 50176,
       "pensamiento": false, "multimodal": null}
    ]}

El primero es el de arranque mientras la persona no elija otro. `pensamiento` y
`multimodal` son opcionales.
"""
import json
import re
from pathlib import Path

CAMPOS = {'id', 'nombre', 'hnf', 'plantilla', 'ctx', 'pensamiento', 'multimodal'}


def leer(ruta):
    """Las especificaciones del fichero, validadas. No mira si los ficheros existen: un
    modelo en un disco sin montar tiene que poder figurar en la lista, marcado como no
    disponible, en vez de impedir el arranque."""
    try:
        datos = json.loads(Path(ruta).read_text())
    except (OSError, ValueError) as exc:
        raise ValueError('No pude leer la lista de modelos ' + str(ruta) + ': ' + str(exc))
    modelos = datos.get('modelos') if isinstance(datos, dict) else None
    if not isinstance(modelos, list) or not modelos:
        raise ValueError(str(ruta) + ': se espera {"modelos": [...]} con al menos uno')
    vistos = set()
    for modelo in modelos:
        if not isinstance(modelo, dict):
            raise ValueError(str(ruta) + ': cada modelo es un objeto')
        sobran = set(modelo) - CAMPOS
        if sobran:
            raise ValueError(str(ruta) + ': campos desconocidos ' + ', '.join(sorted(sobran)))
        for campo in ('id', 'nombre', 'hnf', 'plantilla'):
            if not isinstance(modelo.get(campo), str) or not modelo[campo]:
                raise ValueError(str(ruta) + ': a un modelo le falta «' + campo + '»')
        if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,63}', modelo['id']):
            raise ValueError(str(ruta) + ': id no válido: ' + modelo['id'])
        if modelo['id'] in vistos:
            raise ValueError(str(ruta) + ': id repetido: ' + modelo['id'])
        vistos.add(modelo['id'])
        if not isinstance(modelo.get('ctx'), int) or isinstance(modelo['ctx'], bool) or modelo['ctx'] < 1024:
            raise ValueError(str(ruta) + ': «ctx» de ' + modelo['id'] + ' debe ser un entero de 1024 o más')
        if not isinstance(modelo.get('pensamiento', False), bool):
            raise ValueError(str(ruta) + ': «pensamiento» de ' + modelo['id'] + ' debe ser true o false')
        if modelo.get('multimodal') is not None and not isinstance(modelo['multimodal'], str):
            raise ValueError(str(ruta) + ': «multimodal» de ' + modelo['id'] + ' debe ser una ruta')
    return modelos


class Modelos:
    """La lista y cuál está puesto. `fabrica(modelo)` devuelve la función que lo carga."""

    def __init__(self, modelos, fabrica, activo=None):
        self._modelos = {modelo['id']: modelo for modelo in modelos}
        self._orden = [modelo['id'] for modelo in modelos]
        self._fabrica = fabrica
        self.activo = activo if activo in self._modelos else self._orden[0]

    def especificacion(self, identificador=None):
        return self._modelos[identificador or self.activo]

    def fabrica(self, identificador=None):
        return self._fabrica(self.especificacion(identificador))

    def disponible(self, identificador):
        modelo = self._modelos[identificador]
        return Path(modelo['hnf']).is_file() and Path(modelo['plantilla']).is_file()

    def lista(self):
        return [dict(id=i, name=self._modelos[i]['nombre'], ctx=self._modelos[i]['ctx'],
                     active=i == self.activo, available=self.disponible(i))
                for i in self._orden]

    def elegir(self, identificador, runtime):
        """Pone otro modelo: descarga el que hubiera y deja el nuevo listo para cargarse."""
        if identificador not in self._modelos:
            raise ValueError('No hay ningún modelo «' + str(identificador) + '»: están ' + ', '.join(self._orden))
        if not self.disponible(identificador):
            modelo = self._modelos[identificador]
            raise ValueError('«' + modelo['nombre'] + '» no está disponible: falta su fichero o su plantilla ('
                             + modelo['hnf'] + '). ¿Está montado el disco?')
        if identificador == self.activo:
            return False
        runtime.switch(self.fabrica(identificador), self._modelos[identificador]['ctx'])
        self.activo = identificador
        return True
