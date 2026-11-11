"""Terminal local de solo lectura: el modelo ve la salida real del sistema.

No hay shell: la orden se trocea y solo corre si el programa, su subcomando y
cada opción están en la lista. Tuberías y redirecciones llegan como texto y se
rechazan. Sin cat ni grep sobre archivos: lista y estado, no contenidos. Lo que
el modelo lee de la web o del NAS puede intentar dictarle órdenes, así que esta
puerta no puede cambiar nada aunque se obedezca.
"""
from __future__ import annotations

import os
import re
import shlex
import socket
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

# El listado de lo instalado en cada gestor: lo que se lanza al buscar una aplicación.
LISTADOS = {'apt': 'apt list --installed', 'snap': 'snap list', 'flatpak': 'flatpak list'}
# Dónde dejan su lanzador las aplicaciones, vengan de donde vengan. Solo se miran los
# nombres de archivo: lista y estado, no contenidos.
LANZADORES = ('/usr/share/applications', '/usr/local/share/applications', '~/.local/share/applications',
              '/var/lib/snapd/desktop/applications', '/var/lib/flatpak/exports/share/applications',
              '~/.local/share/flatpak/exports/share/applications')
MAX_COINCIDENCIAS = 12
# Lo que apt escribe alrededor de su listado y no es ningún paquete.
RUIDO_APT = ('WARNING: apt does not have a stable CLI interface', 'Listing...')
PARA_BUSCAR = ('Esto es el listado entero. Para saber si una aplicación está instalada repite la orden '
               'con filter="parte del nombre": la búsqueda mira sola en apt, snap, flatpak y los lanzadores.')


def este_pc():
    """La máquina donde corre Helios: no está en el inventario y el modelo no lo sabe."""
    try:
        lineas = dict(l.split('=', 1) for l in open('/etc/os-release', encoding='utf-8') if '=' in l)
        sistema = lineas.get('PRETTY_NAME', 'Linux').strip().strip('"')
    except OSError:
        sistema = 'Linux'
    return dict(nombre=socket.gethostname(), sistema=sistema, se_mira_con='terminal_read')


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
    Los servicios tienen dos ámbitos: el 31/10 miró el sistema, dijo que todo iba bien y
    el servicio fallado estaba en la sesión de usuario.
    """
    ordenes = [orden.split() for orden in ordenes if orden.split()]
    if not ordenes:
        return []
    if ordenes[-1][0] in ('systemctl', 'journalctl'):
        ambitos = {'--user' in o or '--user-unit' in o for o in ordenes if o[0] == ordenes[-1][0]}
        if len(ambitos) == 2:
            return []
        # La orden entera: «sesión de usuario» como texto lo ignoraba y daba todo por bueno.
        ultima = [parte for parte in ordenes[-1] if parte != '--user']
        return [' '.join(ultima if True in ambitos else [ultima[0], '--user', *ultima[1:]])]
    mirados = [GESTORES.get(orden[0]) for orden in ordenes]
    if mirados[-1] is None:
        return []
    return [gestor for gestor in ('apt', 'flatpak', 'snap') if gestor not in mirados]


def falta_tras(ordenes, respuesta):
    """Lo pendiente tras esta orden. Un servicio caído lleva a su registro, no a otro estado.

    En el chat real miró el estado, copió de su historial que no tenía acceso a los
    registros y atribuyó el fallo a una base de datos corrupta sin haberlos leído.
    """
    # Una búsqueda ya miró en todos los gestores: no queda ninguno que señalar.
    if 'encontrado_en' in respuesta:
        return []
    partes = ordenes[-1].split()
    if (partes[0] == 'systemctl' and 'status' in partes and respuesta['exit_code'] != 0
            and not any(orden.startswith('journalctl') for orden in ordenes)):
        ambito = ['--user'] if '--user' in partes else []
        return [' '.join(['journalctl', *ambito, '-u', partes[-1], '-n', '20', '--no-pager'])]
    return sin_mirar(ordenes)


# «orden | grep texto», con -i o sin él y el texto entre comillas o no. Nada más.
GREP = re.compile(r"""^(?P<orden>[^|;&<>`$]+?)\s*\|\s*grep\s+(?:-i\s+)?(?P<c>['"]?)(?P<texto>[^\s|;&<>`$'"-][^\s|;&<>`$'"]*)(?P=c)\s*$""")


def sin_grep(command, filter):
    """`orden | grep texto` es lo que escribe quien conoce una terminal: se lee como filter.

    Sigue sin haber shell ni tubería. El 11/11, midiendo con el E4B, cuatro de cada
    cinco búsquedas empezaban así y se rechazaban una tras otra —hasta seis seguidas
    en un turno— antes de que probara filter; a veces no llegaba a probarlo. Se
    traduce solo esa forma exacta y la orden que queda pasa por la misma lista de
    siempre: cualquier otra tubería se sigue rechazando.
    """
    encontrada = GREP.match(command) if isinstance(command, str) else None
    if not encontrada or (filter and filter.casefold() != encontrada['texto'].casefold()):
        return command, filter, None
    return (encontrada['orden'].strip(), encontrada['texto'],
            'No hay tuberías: «| grep ' + encontrada['texto'] + '» se ha leído como filter="' +
            encontrada['texto'] + '». La próxima vez usa filter.')


def es_listado(partes):
    """¿La orden lista lo instalado en un gestor? Con filter, eso es buscar una aplicación."""
    programa, resto = partes[0], partes[1:]
    if programa in ('dpkg', 'dpkg-query'):
        return '-l' in resto or '-W' in resto
    if programa == 'apt':
        # Sin --installed lista lo disponible en los repositorios, que no es lo instalado.
        return 'list' in resto and '--installed' in resto
    return programa in ('snap', 'flatpak') and 'list' in resto


def lanzadores(texto, carpetas=LANZADORES):
    """Lanzadores de escritorio cuyo nombre contiene el texto, los instalara quien los instalara."""
    vistos = []
    for carpeta in carpetas:
        carpeta = os.path.expanduser(carpeta)
        try:
            nombres = sorted(os.listdir(carpeta))
        except OSError:
            continue
        vistos += [os.path.join(carpeta, nombre) for nombre in nombres
                   if nombre.endswith('.desktop') and texto.casefold() in nombre.casefold()]
    return vistos


def buscar(partes, filtro, propias, *, runner=ejecutar, escritorio=lanzadores):
    """Buscar una aplicación es mirar en todos los sitios, no en el primero que se ocurra.

    El 10/11 se le pidió encontrar ChatGPT. Dijo que no podía buscarla en dpkg, miró
    snap entero sin filtrar, propuso flatpak, y solo dio con ella en apt cuando la
    persona lo sugirió: cuatro turnos para algo que es una pregunta. `falta_por_mirar`
    ya le decía qué gestores quedaban, pero encadenarlos seguía siendo cosa suya y un
    modelo de este tamaño se pierde por el camino. Ahora la cadena la hace la
    herramienta: un listado con filter mira también en los otros gestores y en los
    lanzadores, y devuelve dónde está y dónde no.
    """
    propio = GESTORES[partes[0]]
    instaladas = propias
    if partes[0] in ('dpkg', 'dpkg-query') and '-l' in partes:
        # `rc` es un paquete desinstalado del que queda la configuración.
        instaladas = [linea for linea in propias if linea[:2] in ('ii', 'hi')]
    hallado = {propio: instaladas}
    otros = {}
    for gestor, orden in LISTADOS.items():
        if gestor == propio:
            continue
        codigo, salida = runner(trocear(orden))
        if codigo == 127:
            otros[gestor] = 'este equipo no tiene ' + gestor
            continue
        lineas = [linea for linea in salida.splitlines()
                  if filtro.casefold() in linea.casefold() and not linea.startswith(RUIDO_APT)]
        hallado[gestor] = lineas
        otros[gestor] = (lineas[:MAX_COINCIDENCIAS] if lineas else
                         'sin coincidencias' if codigo == 0 else
                         'no se pudo leer (exit_code ' + str(codigo) + ')')
    iconos = escritorio(filtro)
    otros['lanzadores'] = iconos[:MAX_COINCIDENCIAS] or 'sin coincidencias'
    encontrado = [gestor for gestor in ('apt', 'snap', 'flatpak') if hallado.get(gestor)]
    if iconos:
        encontrado.append('lanzadores')
    resultado = dict(tambien_mirado=otros, encontrado_en=encontrado)
    if propias and not instaladas:
        resultado['solo_restos'] = ('En dpkg solo queda su configuración (estado rc): '
                                    'por apt está desinstalada.')
    if not encontrado:
        resultado['sin_rastro'] = (
            '«' + filtro + '» no aparece en apt, snap ni flatpak, ni entre los lanzadores. Prueba con otra '
            'parte del nombre antes de decir que no está: un AppImage o un programa copiado a mano no '
            'deja rastro en ningún gestor.')
    return resultado


def read(command, filter=None, *, runner=ejecutar, escritorio=lanzadores):
    if filter and filter.startswith('-'):
        raise ValueError('filter es un texto que deben contener las líneas; las opciones van en command')
    command, filter, leida = sin_grep(command, filter)
    partes = trocear(command)
    codigo, salida = runner(partes)
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
    if leida:
        respuesta['nota'] = leida
    if es_listado(partes):
        if filter:
            hallazgo = buscar(partes, filter, lineas, runner=runner, escritorio=escritorio)
            # Dónde está va delante de la salida: `lines: 0` en el gestor preguntado se
            # leía como «no está», aunque estuviera en otro.
            respuesta = dict(command=command, encontrado_en=hallazgo.pop('encontrado_en'),
                             **{k: v for k, v in respuesta.items() if k != 'command'}, **hallazgo)
        else:
            respuesta['para_buscar'] = PARA_BUSCAR
    return respuesta
