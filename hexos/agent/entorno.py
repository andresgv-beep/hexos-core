"""Con qué se puede programar en este equipo, en una lectura.

Antes de crear un proyecto o de proponer instalar nada hay que saber qué hay: qué
compiladores e intérpretes, de qué versión, y con qué gestor se instalaría lo que
falte. Con `terminal_read` eso son veinte órdenes `which` encadenadas, y un modelo
pequeño se pierde por el camino o da por instalado lo que no miró.

Solo lectura: busca cada programa y le pregunta su versión. No instala ni cambia nada.

Sin órdenes propias de Linux, como `pc_status`: la misma lectura vale en Windows.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor

SEGUNDOS = 5

# Cómo se le pregunta la versión a quien no entiende `--version`.
PREGUNTA = {'go': ('version',), 'java': ('-version',), 'javac': ('-version',)}

# Por lenguaje: lo imprescindible, donde cada grupo se cumple con cualquiera de sus
# programas (gcc o clang), y lo que acompaña pero no impide trabajar.
LENGUAJES = (
    ('C', (('gcc', 'clang', 'cl'),), ('make', 'cmake', 'ninja', 'gdb', 'pkg-config')),
    ('C++', (('g++', 'clang++', 'cl'),), ('make', 'cmake', 'ninja', 'gdb')),
    ('CUDA', (('nvcc',), ('g++', 'clang++', 'cl')), ('cmake', 'nvidia-smi')),
    ('Python', (('python3', 'python', 'py'),), ('pip', 'venv')),
    ('Rust', (('rustc',), ('cargo',)), ()),
    ('Go', (('go',),), ()),
    ('Java', (('javac',), ('java',)), ('mvn', 'gradle')),
    ('JavaScript', (('node',),), ('npm',)),
    ('C#', (('dotnet',),), ()),
)
GENERALES = ('git',)
GESTORES = ('apt', 'dnf', 'pacman', 'zypper', 'snap', 'flatpak', 'brew', 'winget', 'choco', 'scoop')

# Donde se instalan compiladores que no se añaden solos al PATH. El 13/11, en el portátil,
# nvcc estaba en /usr/local/cuda/bin y cargo en ~/.cargo/bin: `which` decía que no existían.
APARTE = ('~/.cargo/bin', '~/.local/bin', '~/go/bin', '/usr/local/go/bin', '/usr/local/cuda/bin',
          '/opt/cuda/bin')

NOTA = ('listo_para son los lenguajes con los que ya se puede trabajar; en ellos, sin son añadidos que no '
        'están y no impiden trabajar. no_se_puede_todavia son los lenguajes a los que les falta algo '
        'imprescindible: falta dice qué. fuera_del_path son programas que existen pero no se encuentran '
        'por su nombre: hay que llamarlos con la ruta entera. Esta lectura no instala nada.')


def carpetas_aparte(entorno=os.environ):
    vistas = [os.path.expanduser(carpeta) for carpeta in APARTE]
    for variable in ('CUDA_HOME', 'CUDA_PATH', 'CARGO_HOME', 'GOROOT'):
        if entorno.get(variable):
            vistas.append(os.path.join(entorno[variable], 'bin'))
    return vistas


def buscar(nombre, entorno=os.environ):
    """Ruta del programa y si hizo falta salirse del PATH para dar con él."""
    ruta = shutil.which(nombre, path=entorno.get('PATH', os.defpath))
    if ruta:
        return ruta, False
    ruta = shutil.which(nombre, path=os.pathsep.join(carpetas_aparte(entorno)))
    return (ruta, True) if ruta else (None, False)


def ejecutar(partes):
    """Salida de una orden corta, con los errores dentro: `java -version` escribe ahí."""
    try:
        hecho = subprocess.run(partes, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, errors='replace', timeout=SEGUNDOS)
    except (OSError, subprocess.SubprocessError):
        return 1, ''
    return hecho.returncode, hecho.stdout


def version(nombre, ruta, runner=ejecutar):
    """El número de versión, o None si el programa está pero no contesta."""
    codigo, salida = runner([ruta, *PREGUNTA.get(nombre, ('--version',))])
    if codigo != 0:
        return None
    hallada = re.search(r'\d+(?:\.\d+)+', salida)
    return hallada.group(0) if hallada else None


def modulos_python(ruta, runner=ejecutar):
    """pip y venv no son programas: son piezas de Python que una distribución puede no traer."""
    vistos = {}
    codigo, salida = runner([ruta, '-m', 'pip', '--version'])
    hallada = re.search(r'\d+(?:\.\d+)+', salida) if codigo == 0 else None
    if hallada:
        vistos['pip'] = hallada.group(0)
    # venv sin ensurepip crea entornos sin pip: en Debian y Ubuntu es el paquete python3-venv.
    codigo, _ = runner([ruta, '-c', 'import venv, ensurepip'])
    if codigo == 0:
        vistos['venv'] = 'sí'
    return vistos


def sistema():
    if platform.system() == 'Linux':
        try:
            with open('/etc/os-release', encoding='utf-8') as f:
                lineas = dict(l.split('=', 1) for l in f if '=' in l)
            return lineas.get('PRETTY_NAME', 'Linux').strip().strip('"')
        except OSError:
            return 'Linux'
    return (platform.system() + ' ' + platform.release()).strip()


def reconocer(*, localizar=buscar, runner=ejecutar):
    nombres = []
    for _, imprescindible, acompana in LENGUAJES:
        for nombre in [n for grupo in imprescindible for n in grupo] + list(acompana):
            if nombre not in nombres and nombre not in ('pip', 'venv'):
                nombres.append(nombre)
    nombres += [n for n in GENERALES if n not in nombres]

    def mirar(nombre):
        ruta, aparte = localizar(nombre)
        if not ruta:
            return nombre, None
        return nombre, dict(ruta=ruta, aparte=aparte, version=version(nombre, ruta, runner))

    with ThreadPoolExecutor(max_workers=8) as hilos:
        hallados = {nombre: dato for nombre, dato in hilos.map(mirar, nombres) if dato}

    interprete = next((hallados[n] for n in ('python3', 'python', 'py') if n in hallados), None)
    piezas = modulos_python(interprete['ruta'], runner) if interprete else {}

    def texto(nombre):
        if nombre in piezas:
            return piezas[nombre]
        return hallados[nombre]['version'] or 'instalado, no dice su versión'

    listos, incompletos = {}, {}
    for lenguaje, imprescindible, acompana in LENGUAJES:
        tiene = {n: texto(n) for grupo in imprescindible for n in grupo if n in hallados}
        tiene.update({n: texto(n) for n in acompana if n in hallados or n in piezas})
        sin = [' o '.join(grupo) for grupo in imprescindible if not any(n in hallados for n in grupo)]
        sin_extra = [n for n in acompana if n not in hallados and n not in piezas]
        if not tiene:
            incompletos[lenguaje] = dict(falta='todo: no hay nada instalado')
        elif sin:
            incompletos[lenguaje] = dict(falta=' y '.join(sin), tiene=tiene)
        else:
            listos[lenguaje] = dict(tiene=tiene, **(dict(sin=sin_extra) if sin_extra else {}))

    # Cada lenguaje sale en un solo sitio. Con una lista aparte de todo lo instalado, el
    # E4B contó Java entre los que se pueden usar y en la frase siguiente dijo que le faltaba javac.
    resultado = dict(
        equipo=dict(nombre=socket.gethostname(), sistema=sistema(), arquitectura=platform.machine()),
        listo_para=listos or 'ningún lenguaje tiene todo lo imprescindible',
        no_se_puede_todavia=incompletos or 'nada: todos los lenguajes conocidos están listos',
    )
    generales = {n: texto(n) for n in GENERALES if n in hallados}
    if generales:
        resultado['control_de_versiones'] = generales
    aparte = {n: dato['ruta'] for n, dato in hallados.items() if dato['aparte']}
    if aparte:
        resultado['fuera_del_path'] = aparte
    gestores = [g for g in GESTORES if localizar(g)[0]]
    resultado['gestores_de_paquetes'] = gestores or 'ninguno conocido'
    resultado['nota'] = NOTA
    return resultado
