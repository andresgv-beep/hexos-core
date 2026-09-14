"""Equipos por nombre del inventario y credenciales guardadas en el espacio de trabajo."""
import argparse
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
import sys


NAME = re.compile(r'[A-Za-z0-9 ._-]{1,64}')


class AccessNeeded(ValueError):
    """Falta la credencial de un equipo. La pide la interfaz, nunca el chat."""

    def __init__(self, device, located=None, reason=None):
        self.device = device
        # Dirección resuelta por el servidor: la ventana debe enseñar a qué máquina
        # se está dando el acceso, y no puede fiarse de lo que diga el cliente.
        self.located = located
        # 'rejected' cuando el acceso guardado existía pero el equipo lo rechazó:
        # la ventana tiene que decirlo, o la persona vuelve a escribir lo mismo.
        self.reason = reason
        if reason == 'rejected':
            super().__init__('El equipo ' + repr(device) + ' rechazó el acceso guardado. '
                             'La interfaz lo volverá a pedir; no pidas la contraseña por el chat. '
                             'Revisa también el usuario y el puerto: un puerto reenviado a otra '
                             'máquina da exactamente este error. Esto no dice nada sobre su salud.')
            return
        super().__init__('Helios no tiene todavía el acceso de ' + repr(device) +
                         '. La interfaz lo pedirá; no pidas la contraseña por el chat ni la escribas en él. '
                         'Esto no significa que el equipo esté sano.')


def store_path(workspace):
    return Path(workspace) / 'credentials.json'


def load(workspace):
    path = store_path(workspace)
    if not path.exists():
        return {}
    if path.stat().st_mode & 0o077:
        raise ValueError('credentials.json es legible por otros; corrige con chmod 600')
    return json.loads(path.read_text())


def save(workspace, name, user, password, port=22, host=None):
    """Escribe con permisos restringidos desde la creación, sin ventana legible.

    `host` fija la dirección del equipo. Sin ella se resuelve por los vecinos de
    la red, que solo sirve estando en la misma: en otra casa, o detrás de una VPN,
    el equipo no aparece en la tabla ARP y no habría forma de encontrarlo.
    """
    if not NAME.fullmatch(name or '') or not NAME.fullmatch(user or ''):
        raise ValueError('Nombre de equipo o usuario no válido')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Puerto no válido')
    if host is not None:
        host = address(host)
    data = load(workspace)
    entrada = dict(user=user, password=password, port=port)
    if host:
        entrada['host'] = host
    data[name.casefold()] = entrada
    path = store_path(workspace)
    temporary = path.with_suffix('.tmp')
    handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, 'w') as out:
        json.dump(data, out, ensure_ascii=False, indent=2)
    os.replace(temporary, path)
    return dict(saved=name.casefold(), user=user, port=port, host=host)


def only_device(workspace):
    """El único equipo con acceso guardado, o un error que los nombra.

    `device` tenía por defecto 'synology', y con dos equipos guardados eso mandaba
    la lectura al que no era sin avisar: se pedía el estado de uno y contestaba
    por el otro. Con uno solo el atajo se conserva; con varios hay que decir cuál.
    """
    guardados = sorted(load(workspace))
    if len(guardados) == 1:
        return guardados[0]
    if not guardados:
        # Sin ninguno, el nombre habitual mantiene el camino de pedir el acceso.
        return 'synology'
    raise ValueError('Hay varios equipos guardados y no has dicho cuál: ' +
                     ', '.join(repr(n) for n in guardados) +
                     '. Repite la lectura indicando device.')


def update(workspace, name, port=None, host=None):
    """Cambia puerto o dirección de un acceso ya guardado, sin tocar la contraseña.

    Existe porque corregir un puerto obligaba a volver a escribir la credencial
    entera, y eso no siempre se puede: quien la tiene puede no estar delante. La
    contraseña se conserva tal cual y no se lee para nada más que volver a escribirla
    en su sitio.
    """
    data = load(workspace)
    clave = (name or '').casefold()
    if clave not in data:
        raise ValueError('No hay acceso guardado de ' + repr(name) +
                         '. Guardados: ' + (', '.join(sorted(data)) or 'ninguno'))
    if port is None and host is None:
        raise ValueError('Nada que cambiar: indica puerto, dirección o ambos')
    entrada = dict(data[clave])
    if port is not None:
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Puerto no válido')
        entrada['port'] = port
    if host is not None:
        entrada['host'] = address(host)
    data[clave] = entrada
    path = store_path(workspace)
    temporary = path.with_suffix('.tmp')
    handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, 'w') as out:
        json.dump(data, out, ensure_ascii=False, indent=2)
    os.replace(temporary, path)
    return dict(updated=clave, user=entrada['user'], host=entrada.get('host'),
                port=entrada['port'], password_kept=True)


HOSTNAME = re.compile(r'[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*', re.I)


def address(value):
    """IPv4, IPv6 o nombre DNS. Se valida aquí porque esto acaba en el argv de ssh
    y un guion inicial convertiría la dirección en una opción."""
    texto = (value or '').strip()
    if not texto or len(texto) > 253:
        raise ValueError('Dirección vacía o demasiado larga')
    try:
        return str(ipaddress.ip_address(texto))
    except ValueError:
        pass
    if not HOSTNAME.fullmatch(texto):
        raise ValueError('Dirección no válida: usa una IP o un nombre de equipo')
    return texto.casefold()


def endpoint(value):
    """Lo que la gente pega de verdad → (dirección, puerto o None).

    Acepta `1.2.3.4`, `nas.ddns.net`, `https://nas.ddns.net`, `nas.ddns.net:30`,
    `ssh://nas:30` y `[::1]:30`. El esquema se descarta porque SSH no usa ninguno,
    pero la dirección que uno tiene a mano es la del panel web. El puerto sí se
    conserva: tirarlo obligaba a volver a decirlo, y era el dato que faltaba.
    """
    texto = (value or '').strip()
    texto = re.sub(r'^[a-z][a-z0-9+.-]*://', '', texto, flags=re.I)
    # Nada de usuario ni contraseña en la dirección: no es sitio para una credencial
    # y aceptarlo sería una vía silenciosa para colarla.
    if '@' in texto:
        raise ValueError('No pongas usuario ni contraseña en la dirección, solo el equipo')
    texto = texto.split('/')[0].split('?')[0]
    puerto = None
    if texto.startswith('['):
        cierre = texto.find(']')
        if cierre < 0:
            raise ValueError('Dirección IPv6 sin cerrar')
        resto = texto[cierre + 1:]
        texto = texto[1:cierre]
        if resto.startswith(':'):
            puerto = resto[1:]
    elif texto.count(':') == 1:
        texto, _, puerto = texto.partition(':')
    if puerto is not None:
        if not puerto.isdigit() or not 1 <= int(puerto) <= 65535:
            raise ValueError('Puerto no válido en la dirección')
        puerto = int(puerto)
    return address(texto), puerto


def credentials(workspace, name):
    return load(workspace).get((name or '').casefold())


def forget(workspace, name):
    """Revoca el acceso guardado de un equipo. El archivo se reescribe sin él."""
    data = load(workspace)
    if (name or '').casefold() not in data:
        raise ValueError('No hay acceso guardado de ' + repr(name) +
                         '. Guardados: ' + (', '.join(sorted(data)) or 'ninguno'))
    removed = data.pop(name.casefold())
    path = store_path(workspace)
    if data:
        temporary = path.with_suffix('.tmp')
        handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(handle, 'w') as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    else:
        path.unlink()
    return dict(forgotten=name.casefold(), user=removed['user'], remaining=sorted(data))


def resolve(workspace, name):
    """Por dónde llegar al equipo guardado con ese nombre, en orden de intento.

    Devuelve la primera dirección en `host` y el resto en `alternatives`, porque un
    equipo puede tener dos caminos —su IP en la red y una dirección fija de fuera—
    y cuál sirve depende de dónde estés. Antes se devolvía una sola y, si esa no
    llegaba, no había segunda oportunidad.

    Prioridad: la IP local si el equipo se está viendo AHORA en la red; si no, la
    dirección fija. Y en cualquier caso, la otra queda de alternativa.

    Por encima de todo eso manda la dirección de su credencial, si se guardó una:

    es la que se usa para entrar, y por eso pesa más que ninguna.
    """
    if not NAME.fullmatch(name or ''):
        raise ValueError('Nombre de equipo no válido')
    fijada = (credentials(workspace, name) or {}).get('host')
    if fijada:
        return dict(name=name.casefold(), host=fijada, mac=None,
                    observed_at=None, reachable=None, pinned=True, alternatives=[])
    database = Path(workspace) / 'work.sqlite'
    if not database.exists():
        raise ValueError('No hay inventario todavía; pide guardar los dispositivos de la red')
    connection = sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True)
    try:
        rows = [json.loads(body) for _, body in connection.execute('SELECT id, body FROM network_devices')]
    except sqlite3.Error as exc:
        raise ValueError('No se pudo leer el inventario') from exc
    finally:
        connection.close()
    wanted = name.casefold()
    matches = [row for row in rows
               if (row.get('identity') or {}).get('name', '').casefold() == wanted]
    if not matches:
        known = sorted({(row.get('identity') or {}).get('name') for row in rows if row.get('identity')})
        raise ValueError('No hay ningún equipo guardado como ' + repr(name) +
                         '. Guardados: ' + (', '.join(known) or 'ninguno'))
    if len(matches) > 1:
        raise ValueError('Hay ' + str(len(matches)) + ' equipos guardados como ' + repr(name) +
                         '; el nombre no distingue cuál')
    device = matches[0]
    # Direcciones observadas en la red, la más reciente y REACHABLE por delante.
    addresses = device.get('latest_addresses') or device.get('addresses') or []
    locales = []
    for entry in addresses:
        try:
            direccion = ipaddress.ip_address(entry['ip'])
        except (ValueError, KeyError, TypeError):
            continue
        if direccion.version == 4:
            locales.append((('REACHABLE' not in (entry.get('state') or [])),
                            entry['observed_at'], str(direccion)))
    locales.sort(key=lambda item: item[1], reverse=True)
    locales.sort(key=lambda item: item[0])
    fija = device.get('pinned_host')
    # Un equipo que se está viendo AHORA en la red se prueba primero por su IP
    # local: es más rápida y no depende de que el router de fuera esté bien. Si no
    # se le ve —otra casa, otra red—, manda la dirección fija. Y la que no se
    # eligió queda como alternativa, que es lo que faltaba: al no llegar por la
    # LAN, probar la de fuera en vez de rendirse.
    aqui = bool(device.get('in_latest_snapshot')) and bool(locales) and not locales[0][0]
    orden = []
    if locales and (aqui or not fija):
        alcanzable, visto, host = locales[0]
        orden.append(dict(host=host, port=None, pinned=False,
                          observed_at=visto, reachable=not alcanzable))
    if fija:
        orden.append(dict(host=fija, port=device.get('pinned_port'), pinned=True,
                          observed_at=None, reachable=None))
    if locales and orden and orden[0]['host'] != locales[0][2]:
        alcanzable, visto, host = locales[0]
        orden.append(dict(host=host, port=None, pinned=False,
                          observed_at=visto, reachable=not alcanzable))
    if not orden:
        raise ValueError(repr(name) + ' está en el inventario pero sin dirección IPv4 observada '
                         'ni dirección fija; pide una lectura de la red y reintenta, o dale una '
                         'dirección fija con device_remote')
    return dict(name=wanted, mac=device.get('mac'), **orden[0],
                alternatives=orden[1:])


def main():
    parser = argparse.ArgumentParser(description='Guardar, listar o revocar el acceso a un equipo.')
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--device', help='Nombre guardado, por ejemplo synology')
    parser.add_argument('--user', help='Requerido al guardar')
    parser.add_argument('--port', type=int, default=22)
    parser.add_argument('--host', help='Dirección fija (IP o nombre). Sin ella se busca '
                                       'en los vecinos de la red, que solo vale en la misma LAN.')
    parser.add_argument('--forget', action='store_true', help='Borrar el acceso guardado de --device')
    parser.add_argument('--set', action='store_true',
                        help='Cambiar solo --port y/o --host de un acceso ya guardado, sin tocar la contraseña')
    parser.add_argument('--list', action='store_true', help='Listar accesos guardados, sin contraseñas')
    args = parser.parse_args()
    if args.list:
        saved = load(args.workspace)
        for name, entry in sorted(saved.items()):
            print(name, '->', entry['user'] + '@' + entry.get('host', '(por inventario)') +
                  ':' + str(entry['port']))
        if not saved:
            print('No hay ningún acceso guardado.')
        return
    if not args.device:
        parser.error('--device es obligatorio salvo con --list')
    if args.forget:
        print('Revocado:', forget(args.workspace, args.device))
        return
    if args.set:
        print('Actualizado:', update(args.workspace, args.device,
                                     port=args.port if '--port' in sys.argv else None,
                                     host=args.host))
        return
    if not args.user:
        parser.error('--user es obligatorio al guardar')
    if args.host:
        print('Equipo', args.device, 'fijado en', address(args.host),
              '- no se buscará en los vecinos de la red.')
    else:
        try:
            located = resolve(args.workspace, args.device)
            print('Equipo', located['name'], 'en', located['host'], '(MAC', located['mac'] + ')')
        except ValueError as exc:
            print('Aviso:', exc)
            print('Se guardará igualmente; se resolverá cuando el inventario lo tenga.')
    password = getpass.getpass('Contraseña de ' + args.user + ' (no se muestra): ')
    if not password:
        raise SystemExit('Contraseña vacía; no se ha guardado nada.')
    result = save(args.workspace, args.device, args.user, password, args.port, args.host)
    print('Guardado en', store_path(args.workspace), 'con permisos 600:', result)


if __name__ == '__main__':
    main()
