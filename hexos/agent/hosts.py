"""Equipos por nombre del inventario y credenciales guardadas en el espacio de trabajo."""
import argparse
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3


NAME = re.compile(r'[A-Za-z0-9 ._-]{1,64}')


class AccessNeeded(ValueError):
    """Falta la credencial de un equipo. La pide la interfaz, nunca el chat."""

    def __init__(self, device, located=None):
        self.device = device
        # Dirección resuelta por el servidor: la ventana debe enseñar a qué máquina
        # se está dando el acceso, y no puede fiarse de lo que diga el cliente.
        self.located = located
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


def save(workspace, name, user, password, port=22):
    """Escribe con permisos restringidos desde la creación, sin ventana legible."""
    if not NAME.fullmatch(name or '') or not NAME.fullmatch(user or ''):
        raise ValueError('Nombre de equipo o usuario no válido')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Puerto no válido')
    data = load(workspace)
    data[name.casefold()] = dict(user=user, password=password, port=port)
    path = store_path(workspace)
    temporary = path.with_suffix('.tmp')
    handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, 'w') as out:
        json.dump(data, out, ensure_ascii=False, indent=2)
    os.replace(temporary, path)
    return dict(saved=name.casefold(), user=user, port=port)


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
    """IPv4 actual del equipo guardado con ese nombre, según el inventario pasivo."""
    if not NAME.fullmatch(name or ''):
        raise ValueError('Nombre de equipo no válido')
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
    # Direcciones de la última observación pasiva; REACHABLE antes que STALE.
    addresses = device.get('latest_addresses') or device.get('addresses') or []
    candidates = []
    for entry in addresses:
        try:
            address = ipaddress.ip_address(entry['ip'])
        except (ValueError, KeyError, TypeError):
            continue
        if address.version == 4:
            candidates.append((('REACHABLE' not in (entry.get('state') or [])), entry['observed_at'], str(address)))
    if not candidates:
        raise ValueError(repr(name) + ' está en el inventario pero sin dirección IPv4 observada; '
                         'pide una lectura de la red y reintenta')
    # Orden estable en dos pasos: primero la más reciente, luego REACHABLE por delante.
    candidates.sort(key=lambda item: item[1], reverse=True)
    candidates.sort(key=lambda item: item[0])
    unreachable, observed_at, host = candidates[0]
    return dict(name=wanted, host=host, mac=device.get('mac'),
                observed_at=observed_at, reachable=not unreachable)


def main():
    parser = argparse.ArgumentParser(description='Guardar, listar o revocar el acceso a un equipo.')
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--device', help='Nombre guardado, por ejemplo synology')
    parser.add_argument('--user', help='Requerido al guardar')
    parser.add_argument('--port', type=int, default=22)
    parser.add_argument('--forget', action='store_true', help='Borrar el acceso guardado de --device')
    parser.add_argument('--list', action='store_true', help='Listar accesos guardados, sin contraseñas')
    args = parser.parse_args()
    if args.list:
        saved = load(args.workspace)
        for name, entry in sorted(saved.items()):
            print(name, '->', entry['user'] + ':' + str(entry['port']))
        if not saved:
            print('No hay ningún acceso guardado.')
        return
    if not args.device:
        parser.error('--device es obligatorio salvo con --list')
    if args.forget:
        print('Revocado:', forget(args.workspace, args.device))
        return
    if not args.user:
        parser.error('--user es obligatorio al guardar')
    try:
        located = resolve(args.workspace, args.device)
        print('Equipo', located['name'], 'en', located['host'], '(MAC', located['mac'] + ')')
    except ValueError as exc:
        print('Aviso:', exc)
        print('Se guardará igualmente; se resolverá cuando el inventario lo tenga.')
    password = getpass.getpass('Contraseña de ' + args.user + ' (no se muestra): ')
    if not password:
        raise SystemExit('Contraseña vacía; no se ha guardado nada.')
    result = save(args.workspace, args.device, args.user, password, args.port)
    print('Guardado en', store_path(args.workspace), 'con permisos 600:', result)


if __name__ == '__main__':
    main()
