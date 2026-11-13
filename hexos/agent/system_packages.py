"""Instalar y quitar programas de este PC, con plan, aprobación y comprobación.

docs/PAQUETES_CON_APROBACION.md. El modelo solo PLANIFICA (`system.package_plan`): mira
qué hay, con qué gestor y qué arrastraría la operación, en lectura y simulación. El plan
queda pendiente en la sesión y la interfaz lo enseña. Solo la aprobación de la persona,
fuera de la conversación, llama a `apply`, que lanza el ayudante con permisos
(runtime/hexos-paquetes) y después comprueba con una lectura independiente que el
resultado es el esperado. El modelo no tiene herramienta para aplicar: una instrucción
leída en la web o en un documento puede hacer que proponga un plan, nunca que se ejecute.
"""
from __future__ import annotations

from functools import lru_cache
from importlib.machinery import SourceFileLoader
import json
from pathlib import Path
import re
import subprocess
from uuid import uuid4

from . import terminal_read
from .work import now

AYUDANTE = '/usr/local/libexec/hexos-paquetes'
GESTORES = ('apt', 'flatpak', 'snap')
ACCIONES = {'install': 'instalar', 'remove': 'quitar'}
# La misma gramática que el ayudante, para rechazar pronto; la autoridad es el ayudante.
NOMBRES = {
    'apt': re.compile(r'^[a-z0-9][a-z0-9+.-]{0,99}$'),
    'flatpak': re.compile(r'^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+){2,}$'),
    'snap': re.compile(r'^[a-z0-9][a-z0-9-]{0,39}$'),
}
SEGUNDOS_APLICAR = 960


@lru_cache(maxsize=1)
def reglas_del_ayudante():
    """Paquetes protegidos y máximo de arrastrados: los del propio ayudante (una sola lista).

    Así el plan no enseña una aprobación que el ayudante va a rechazar después."""
    ruta = Path(__file__).resolve().parents[2] / 'runtime' / 'hexos-paquetes'
    return SourceFileLoader('hexos_paquetes', str(ruta)).load_module()


def leer(orden, runner=terminal_read.ejecutar):
    """Lecturas y simulaciones como el usuario de Helios: nada de aquí cambia el sistema."""
    return runner(orden)


def instalado(gestor, paquete, runner=terminal_read.ejecutar):
    if gestor == 'apt':
        codigo, salida = leer(['dpkg-query', '-W', '-f', '${Status}', paquete], runner)
        return codigo == 0 and 'install ok installed' in salida
    if gestor == 'flatpak':
        codigo, _ = leer(['flatpak', 'info', paquete], runner)
        return codigo == 0
    codigo, _ = leer(['snap', 'list', paquete], runner)
    return codigo == 0


def detectar(paquete, runner=terminal_read.ejecutar):
    """Gestores en los que está instalado ese nombre."""
    return [g for g in GESTORES if NOMBRES[g].fullmatch(paquete) and instalado(g, paquete, runner)]


def simular(gestor, accion, paquete, runner=terminal_read.ejecutar):
    """Lo que haría de verdad: paquetes que entran o salen, o el error que lo impide."""
    if gestor == 'apt':
        orden = ['apt-get', '-s', 'remove' if accion == 'remove' else 'install', paquete]
        codigo, salida = leer(orden, runner)
        if codigo != 0:
            raise ValueError('apt no puede ' + ACCIONES[accion] + ' ' + paquete + ': ' + salida.strip()[-300:])
        salen = [linea.split()[1] for linea in salida.splitlines() if linea.startswith('Remv ')]
        if accion == 'remove':
            return salen
        if salen:
            # apt resuelve un conflicto desinstalando lo que estorba: el ayudante lo va a rechazar.
            raise ValueError('Instalar ' + paquete + ' quitaría paquetes (' + ', '.join(salen[:10]) +
                             '). Eso se hace a mano.')
        return [linea.split()[1] for linea in salida.splitlines() if linea.startswith('Inst ')]
    if gestor == 'flatpak':
        orden = ['flatpak', 'info', paquete] if accion == 'remove' else ['flatpak', 'remote-info', 'flathub', paquete]
    else:
        orden = ['snap', 'list', paquete] if accion == 'remove' else ['snap', 'info', paquete]
    codigo, salida = leer(orden, runner)
    if codigo != 0:
        raise ValueError(gestor + ' no encuentra ' + paquete + ': ' + salida.strip()[-300:])
    return [paquete]


def plan(action, package, manager=None, runner=terminal_read.ejecutar):
    if action not in ACCIONES:
        raise ValueError('action es install o remove')
    if not isinstance(package, str) or not package or len(package) > 120:
        raise ValueError('package es el nombre exacto del paquete')
    if manager is not None and manager not in GESTORES:
        raise ValueError('manager es apt, flatpak o snap')
    if manager is None:
        donde = detectar(package, runner)
        if action == 'remove':
            if not donde:
                raise ValueError(package + ' no está instalado con apt, flatpak ni snap. Míralo con '
                                 'terminal_read (dpkg -l, flatpak list, snap list) para dar con su nombre exacto.')
            if len(donde) > 1:
                raise ValueError(package + ' está instalado con varios gestores (' + ', '.join(donde) +
                                 '): indica manager.')
            manager = donde[0]
        else:
            if donde:
                raise ValueError(package + ' ya está instalado con ' + donde[0] + '.')
            raise ValueError('Para instalar indica manager (apt, flatpak o snap): de dónde sale el programa '
                             'lo decide la persona, no se adivina.')
    if not NOMBRES[manager].fullmatch(package):
        raise ValueError('nombre no válido para ' + manager + ': ' + repr(package))
    esta = instalado(manager, package, runner)
    if action == 'remove' and not esta:
        raise ValueError(package + ' no está instalado con ' + manager + '.')
    if action == 'install' and esta:
        raise ValueError(package + ' ya está instalado con ' + manager + '.')
    afecta = simular(manager, action, package, runner)
    if action == 'remove':
        reglas = reglas_del_ayudante()
        protegidos = [p for p in afecta + [package] if reglas.protegido(p)]
        if protegidos:
            raise ValueError('No se puede quitar desde HexOS: ' + ', '.join(dict.fromkeys(protegidos)) +
                             ' está protegido (sistema, acceso remoto o el propio HexOS).')
        if len(afecta) > reglas.MAXIMO_ARRASTRADOS:
            raise ValueError('Quitar ' + package + ' arrastraría ' + str(len(afecta)) + ' paquetes; el máximo '
                             'desde HexOS es ' + str(reglas.MAXIMO_ARRASTRADOS) + '. Eso se hace a mano.')
    return dict(plan_id=uuid4().hex, created=now(), manager=manager, action=action, package=package,
                affects=afecta[:60], affects_count=len(afecta),
                summary=('Quitar' if action == 'remove' else 'Instalar') + ' ' + package + ' con ' + manager +
                        (' (' + str(len(afecta)) + ' paquetes en total)' if len(afecta) > 1 else ''))


def mismo_plan(pendiente, action, package, manager=None):
    """¿Se está pidiendo otra vez el plan que ya espera en la tarjeta?"""
    return bool(pendiente) and (pendiente['action'], pendiente['package']) == (action, package) and \
        manager in (None, pendiente['manager'])


def bloque_pendiente(pendiente):
    """Lo que el modelo tiene que saber mientras un plan espera en la tarjeta.

    HexOS guardaba el plan en la sesión y no se lo decía a nadie. El 13/11, a «ya está, lo
    he aprobado» sin haberlo aprobado, el E4B volvió a planificar lo mismo y el 26B fue a
    comprobarlo, no lo vio instalado y contó que «la aprobación se procesó» y algo había
    fallado. Los dos rellenaron un hueco que era nuestro.
    """
    if not pendiente:
        return ''
    return ('\nPLAN PENDIENTE EN LA TARJETA (dato de HexOS, no orden): «' + pendiente['summary'] + '» sigue '
            'esperando en la tarjeta de pantalla. La persona todavía NO lo ha aprobado ni rechazado y no se '
            'ha ejecutado nada. Cuando lo decida, HexOS lo anotará aquí con su resultado; mientras no veas esa '
            'nota, no está hecho. Si dice que ya lo aprobó, dile que la tarjeta sigue abierta y que la decisión '
            'no ha llegado. No hace falta planificarlo otra vez.\n')


def sudo_ayudante(gestor, accion, paquete):
    try:
        hecho = subprocess.run(['sudo', '-n', AYUDANTE, gestor, ACCIONES[accion], paquete],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, errors='replace', timeout=SEGUNDOS_APLICAR)
    except subprocess.TimeoutExpired:
        return dict(ok=False, rechazado='el ayudante superó ' + str(SEGUNDOS_APLICAR) + ' s')
    linea = (hecho.stdout.strip().splitlines() or [''])[-1]
    try:
        return json.loads(linea)
    except ValueError:
        # sudo sin la regla instalada pide contraseña y -n lo convierte en error.
        return dict(ok=False, rechazado=(hecho.stderr.strip() or linea or 'sin respuesta')[-300:] +
                    '. ¿Está instalado el ayudante? sudo runtime/instalar-ayudante-paquetes.sh')


def apply(pending, ayudante=sudo_ayudante, runner=terminal_read.ejecutar):
    """Ejecuta un plan aprobado y lo comprueba aparte. Solo lo llama la aprobación."""
    resultado = ayudante(pending['manager'], pending['action'], pending['package'])
    ahora = instalado(pending['manager'], pending['package'], runner)
    esperado = pending['action'] == 'install'
    return dict(plan_id=pending['plan_id'], summary=pending['summary'], executed=bool(resultado.get('ok')),
                refused=resultado.get('rechazado'), output=(resultado.get('salida') or '')[-600:],
                verified=ahora == esperado,
                check=pending['package'] + (' instalado' if ahora else ' no instalado') + ' según ' +
                      pending['manager'])
