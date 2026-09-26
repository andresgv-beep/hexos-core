"""Configuración del operador; no se aceptan rutas ni presets nuevos desde el modelo."""
import hashlib
import json
from pathlib import Path
from .profiles import validate
from ..file_catalog.validation import path_argument


def load(workspace):
    path = Path(workspace)/'media_jobs.json'
    if not path.exists():
        return None
    config = json.loads(path.read_text())
    if config.get('enabled') is not True:
        return None
    if not isinstance(config.get('device'), str) or not config['device']:
        raise ValueError('Equipo multimedia requerido')
    if config.get('mode', 'live') != 'live':
        raise ValueError('El servicio de chat solo admite modo live')
    if not config.get('profiles') or not config['files'].get('libraries'):
        raise ValueError('Faltan perfiles o bibliotecas configuradas')
    for key in ('storage','output','control','ffmpeg','ffprobe'):
        if path_argument(config['files'][key])=='/':
            raise ValueError('Ruta específica requerida para '+key)
    config['files']['libraries']=[path_argument(p) for p in config['files']['libraries']]
    if not isinstance(config['files'].get('replace_original', False), bool):
        raise ValueError('replace_original debe ser true o false')
    if '/' in config['files']['libraries']:
        raise ValueError('No se admite / como biblioteca de películas')
    if any(type(config['preset_version'].get(k)) is not int for k in ('VersionMajor','VersionMinor','VersionMicro')):
        raise ValueError('Falta versión completa de exportación del preset')
    for profile in config['profiles']:
        validate(profile)
    if len({p['id'] for p in config['profiles']}) != len(config['profiles']):
        raise ValueError('Perfil duplicado')
    config.setdefault('container', 'HandBrake')
    config['resource'] = config['device']+'/'+config['container']
    config['digest'] = hashlib.sha256(json.dumps(config, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return config
