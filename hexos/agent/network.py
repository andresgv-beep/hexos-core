"""Instantánea pasiva del kernel local; sin sondeos, DNS ni comandos del modelo."""
from datetime import datetime, timezone
import json
import shutil
import subprocess


def snapshot():
    binary = shutil.which('ip')
    if not binary:
        raise RuntimeError('No está instalado ip (iproute2); no se ha consultado la red.')
    def read(*args):
        result = subprocess.run([binary, '-j', *args], capture_output=True,
                                text=True, timeout=5, check=True)
        rows = json.loads(result.stdout)
        if not isinstance(rows, list):
            raise ValueError('Respuesta de ip no válida')
        return rows
    interfaces = read('address', 'show')
    routes = read('route', 'show') + read('-6', 'route', 'show')
    neighbors = read('neigh', 'show')
    known = []
    unresolved = 0
    for row in neighbors:
        state = row.get('state', [])
        if isinstance(state, str):
            state = state.split(',')
        if not row.get('lladdr') or set(state) & {'FAILED', 'INCOMPLETE'}:
            unresolved += 1
            continue
        known.append(dict(ip=row.get('dst'), interface=row.get('dev'),
                          mac=row['lladdr'], state=state,
                          recently_reachable='REACHABLE' in state))
    return dict(observed_at=datetime.now(timezone.utc).isoformat(),
        source='local_kernel_iproute2', passive=True, complete_inventory=False,
        note='Vecinos conocidos por este equipo, no todos los dispositivos conectados. '
             'REACHABLE indica alcanzable recientemente; STALE y otros estados no confirman '
             'conexión actual. Una IP no identifica por sí sola un NAS. '
             'Las rutas y direcciones propias tampoco prueban que otro dispositivo esté conectado.',
        interfaces=[dict(name=r.get('ifname'), state=r.get('operstate'),
                         addresses=[dict(ip=a.get('local'), prefixlen=a.get('prefixlen'),
                                         family=a.get('family')) for a in r.get('addr_info', [])])
                    for r in interfaces][:32],
        routes=[{k:r[k] for k in ('dst', 'gateway', 'dev', 'prefsrc') if k in r}
                for r in routes][:64],
        neighbors=known[:128], known_neighbors=len(known),
        unresolved_entries=unresolved,
        truncated=len(known)>128 or len(interfaces)>32 or len(routes)>64)
