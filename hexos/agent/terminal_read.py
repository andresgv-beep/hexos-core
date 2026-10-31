"""Terminal local de solo lectura: el modelo ve la salida real del sistema.

No hay shell: la orden se trocea y solo corre si el programa, su subcomando y
cada opción están en la lista. Tuberías y redirecciones llegan como texto y se
rechazan. Sin cat ni grep sobre archivos: lista y estado, no contenidos. Lo que
el modelo lee de la web o del NAS puede intentar dictarle órdenes, así que esta
puerta no puede cambiar nada aunque se obedezca.
"""
from __future__ import annotations

import os
import shlex
import subprocess

MAX_SALIDA = 6000
SEGUNDOS = 15
ENTORNO = dict(PATH='/usr/bin:/bin', HOME=os.path.expanduser('~'), LC_ALL='C.UTF-8',
               PAGER='cat', SYSTEMD_PAGER='', XDG_RUNTIME_DIR=os.environ.get('XDG_RUNTIME_DIR', ''),
               DBUS_SESSION_BUS_ADDRESS=os.environ.get('DBUS_SESSION_BUS_ADDRESS', ''))

# programa: (subcomandos, o None si no lleva; opciones admitidas)
ORDENES = {
    'dpkg': (None, {'-l', '-s', '-L', '-S'}),
    'dpkg-query': (None, {'-l', '-s', '-L', '-S', '-W'}),
    'apt-cache': ({'search', 'policy', 'show', 'depends', 'rdepends'}, {'--names-only', '--installed'}),
    'apt': ({'list', 'show'}, {'--installed', '--manual-installed', '--upgradable', '-a'}),
    'apt-mark': ({'showhold', 'showmanual', 'showauto'}, set()),
    'flatpak': ({'list', 'info'}, {'--app', '--runtime', '--user', '--system', '--columns'}),
    'snap': ({'list', 'info'}, {'--all'}),
    'which': (None, {'-a'}),
    'whereis': (None, set()),
    'pidof': (None, set()),
    'ls': (None, {'-l', '-a', '-la', '-al', '-lh', '-lah', '-1', '-d', '-ld'}),
    'du': (None, {'-s', '-h', '-sh'}),
    'df': (None, {'-h', '-T', '-hT'}),
    'free': (None, {'-h', '-m'}),
    'uname': (None, {'-a', '-r', '-m'}),
    'lsblk': (None, {'-f', '-o'}),
    'file': (None, set()),
    'systemctl': ({'status', 'is-active', 'is-enabled', 'list-units', 'list-unit-files'},
                  {'--user', '--no-pager', '--type', '--state', '--failed', '--all', '-n'}),
    'journalctl': (None, {'-u', '--user-unit', '-n', '-b', '-p', '--no-pager', '--since', '--user', '-k'}),
}


GESTORES = {'dpkg': 'apt', 'dpkg-query': 'apt', 'apt-cache': 'apt', 'apt': 'apt', 'apt-mark': 'apt',
            'flatpak': 'flatpak', 'snap': 'snap'}


def trocear(orden):
    if not isinstance(orden, str) or not orden.strip() or len(orden) > 300:
        raise ValueError('command debe ser una orden de hasta 300 caracteres')
    try:
        partes = shlex.split(orden)
    except ValueError as exc:
        raise ValueError('command mal formado: ' + str(exc))
    programa = partes[0]
    if programa not in ORDENES:
        raise ValueError(programa + ' no está disponible. Programas de lectura: ' + ', '.join(sorted(ORDENES)))
    subcomandos, opciones = ORDENES[programa]
    resto = partes[1:]
    subcomando = next((parte for parte in resto if not parte.startswith('-')), None)
    if subcomandos is not None and subcomando not in subcomandos:
        raise ValueError(programa + ' solo admite: ' + ', '.join(sorted(subcomandos)))
    for parte in resto:
        if parte in ('|', '||', '&', '&&', ';', '>', '>>', '<') or parte.startswith(('`', '$(')):
            raise ValueError('Sin tuberías ni redirecciones: cada orden va sola. '
                             'Para acotar la salida usa filter.')
        if parte.startswith('-') and parte.split('=')[0] not in opciones:
            raise ValueError(programa + ': la opción ' + parte + ' no está permitida. Admitidas: ' +
                             (', '.join(sorted(opciones)) or 'ninguna'))
    return partes


def ejecutar(partes):
    try:
        hecho = subprocess.run(partes, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, errors='replace', timeout=SEGUNDOS, env=ENTORNO, cwd=ENTORNO['HOME'])
    except subprocess.TimeoutExpired:
        return 124, 'La orden superó ' + str(SEGUNDOS) + ' s y se cortó.'
    except OSError as exc:
        return 127, str(exc)
    return hecho.returncode, hecho.stdout


def sin_mirar(ordenes):
    """Gestores que faltan: lo mirado en uno no dice nada de los otros.

    Sin gestores en la última orden no hay nada que señalar: `df` no busca aplicaciones.
    """
    mirados = [GESTORES.get(orden.split()[0]) for orden in ordenes if orden.split()]
    if not mirados or mirados[-1] is None:
        return []
    return [gestor for gestor in ('apt', 'flatpak', 'snap') if gestor not in mirados]


def read(command, filter=None, *, runner=ejecutar):
    codigo, salida = runner(trocear(command))
    lineas = salida.splitlines()
    total = len(lineas)
    if filter:
        lineas = [l for l in lineas if filter.casefold() in l.casefold()]
    texto = '\n'.join(lineas)
    respuesta = dict(command=command, exit_code=codigo, lines=len(lineas), output=texto[:MAX_SALIDA])
    if filter:
        respuesta.update(filter=filter, lines_before_filter=total)
    if len(texto) > MAX_SALIDA:
        respuesta['truncated'] = True
    return respuesta
