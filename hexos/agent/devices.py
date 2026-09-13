"""Inventario local observado e identificaciones respaldadas por citas del usuario."""
import json
import ipaddress
import re
from .network import snapshot
from .work import now, string


def initialize(store):
    store.db.execute('CREATE TABLE IF NOT EXISTS network_devices (id TEXT PRIMARY KEY, body TEXT NOT NULL)')


def annotate(store, observation):
    """Unir lectura actual con identidad persistida, sin guardar ni inferir por IP.

    Se devuelven las dos mitades, no solo la identificada: un vecino sin nombre
    guardado no es un dato que falte, es la respuesta a «cuáles no están
    registrados». Enumerarlos a mano desde la lista cruda salía mal —se colaban
    las direcciones de este mismo equipo, que vienen de `ip address` y no de
    `ip neigh`, y alguna IPv6 larga acababa recortada por el camino.
    """
    known = {r['id']: json.loads(r['body']) for r in store.db.execute('SELECT * FROM network_devices')}
    identified, unidentified = [], []
    for neighbor in observation['neighbors']:
        device = known.get(neighbor['interface'] + '/' + neighbor['mac'].lower())
        identity = device.get('identity') if device else None
        neighbor['identity'] = {k:identity[k] for k in ('name','kind','source')} if identity else None
        fila = dict(ip=neighbor['ip'], mac=neighbor['mac'], interface=neighbor['interface'],
                    state=neighbor['state'], recently_reachable=neighbor['recently_reachable'])
        if identity:
            # `identity_source` y no `source`: leído como «source: static» se
            # confundía con el estado de red del equipo, que es otra cosa.
            identified.append(dict(fila, name=identity['name'], kind=identity['kind'],
                                   identity_source=identity['source']))
        else:
            unidentified.append(fila)
    propias = sorted({address['ip'] for interface in observation['interfaces']
                      for address in interface['addresses'] if address.get('ip')})
    return dict(identified_neighbors=identified, unidentified_neighbors=unidentified,
                counts=dict(identified=len(identified), unidentified=len(unidentified),
                            unresolved=observation['unresolved_entries']),
                own_addresses=propias,
                lists_note='identified_neighbors y unidentified_neighbors ya son la partición '
                           'completa de los vecinos: no hay que deducir una de la otra ni releer '
                           '`neighbors`. own_addresses son las direcciones DE ESTE EQUIPO, no '
                           'dispositivos de la red; no las cuentes como vecinos.',
                **observation)


def dispatch(store, name, args, turn_id=None):
    rows = {r['id']: json.loads(r['body']) for r in store.db.execute('SELECT * FROM network_devices')}
    if name == 'device.refresh':
        observation = snapshot()
        for device in rows.values():
            device['in_latest_snapshot'] = False
        for neighbor in observation['neighbors']:
            key = neighbor['interface'] + '/' + neighbor['mac'].lower()
            device = rows.setdefault(key, dict(id=key, mac=neighbor['mac'].lower(),
                interface=neighbor['interface'], addresses=[], identity=None))
            if not device.get('in_latest_snapshot'):
                device['latest_addresses'] = []
            device['in_latest_snapshot'] = True
            device['last_observed_at'] = observation['observed_at']
            address = dict(ip=neighbor['ip'], state=neighbor['state'], observed_at=observation['observed_at'])
            device['addresses'] = [a for a in device['addresses'] if a['ip'] != address['ip']][-31:] + [address]
            device['latest_addresses'].append(address)
        for key, device in rows.items():
            store.db.execute('INSERT OR REPLACE INTO network_devices VALUES (?,?)', (key, json.dumps(device)))
        store.db.commit()
        return dict(saved=True, observed_at=observation['observed_at'], devices=len(rows),
                    observed_devices=sum(d['in_latest_snapshot'] for d in rows.values()),
                    truncated=observation['truncated'], note=observation['note'])
    if name == 'device.list':
        query = args.get('query', '').casefold()
        terms = [v.strip() for v in re.split(r'\s+or\s+', query) if v.strip()]
        found = [d for d in rows.values() if not terms or any(q in json.dumps(d, ensure_ascii=False).casefold() for q in terms)]
        found.sort(key=lambda d: (d['identity'] is None, d['id']))
        compact = [{k:d.get(k) for k in ('id','mac','interface','last_observed_at','in_latest_snapshot','latest_addresses')} |
                   {'identity':{k:d['identity'][k] for k in ('name','kind','source')} if d['identity'] else None} for d in found[:64]]
        return dict(identified_devices=[d for d in compact if d['identity']], devices=compact, total=len(found), truncated=len(found)>64,
                    note='Inventario histórico. Consulta network.local para el estado actual. '
                         'identity=null significa sin identificar. Un filtro sin coincidencias no significa que el inventario esté vacío: consulta sin query. '
                         'MAC e interfaz agrupan observaciones, no garantizan identidad física.')
    target = args['target'].casefold()
    candidates = [d for d in rows.values() if target in (d['id'].casefold(), d['mac'])]
    if not candidates:
        suffix = target.lstrip('.')
        short = suffix.isdigit() and 0 <= int(suffix) <= 255
        try:
            if not short:
                target = str(ipaddress.ip_address(target))
        except ValueError:
            raise ValueError('Usa una IP completa, MAC o id del inventario; consulta device.list.')
        candidates = [d for d in rows.values() if d.get('in_latest_snapshot') and
                      any(a['ip'] == target or (short and ':' not in a['ip'] and a['ip'].split('.')[-1] == suffix)
                          for a in d.get('latest_addresses', []))]
    if len(candidates) != 1:
        raise ValueError('Dispositivo ausente o ambiguo. Actualiza el inventario o usa su id exacto.')
    device = candidates[0]
    # El mensaje real llega del ejecutor, no lo reconstruye el modelo.
    source = store.db.execute("SELECT id,text FROM conversation WHERE id=? AND role='user'", (turn_id,)).fetchone() if turn_id else None
    quote = source['text'] if source else string(args.get('evidence'), 'evidence', 1000)
    label = string(args['name'], 'name', 100)
    kind = args.get('kind', '')
    if kind:
        string(kind, 'kind', 60)
    source = source or next((r for r in store.db.execute("SELECT id,text FROM conversation WHERE role='user' ORDER BY rowid DESC LIMIT 8")
                   if quote in r['text']), None)
    if not source:
        raise ValueError('La evidencia debe ser una cita literal de un mensaje reciente del usuario.')
    identifiers = [device['mac'], device['id']] + [a['ip'] for a in device.get('latest_addresses', [])]
    # Un sufijo solo sirve si identifica a un único registro en la última lectura.
    for address in device.get('latest_addresses', []):
        if ':' in address['ip']:
            continue
        suffix = address['ip'].split('.')[-1]
        matches = [d for d in rows.values() if d.get('in_latest_snapshot') and any(
            ':' not in a['ip'] and a['ip'].split('.')[-1] == suffix for a in d.get('latest_addresses', []))]
        if len(matches) == 1:
            identifiers.append(suffix)
    clauses = re.split(r'[,;\n]', quote.casefold())
    supported = any(label.casefold() in clause and any(re.search(r'(?<![\w.:])' + re.escape(value.casefold()) + r'(?![\w.:])', clause)
                       for value in identifiers) for clause in clauses)
    if not supported or (kind and kind.casefold() not in quote.casefold()):
        raise ValueError('El mensaje no atribuye ese nombre a ese dispositivo. Conserva el sufijo y nombre indicados; no cambies la dirección ni inventes el tipo.')
    identity = dict(name=label, kind=kind or None, source='user_statement', source_id=source['id'],
                    evidence=quote, recorded_at=now())
    previous = device.get('identity')
    if previous and previous['source_id'] != source['id']:
        order = store.db.execute('SELECT rowid FROM conversation WHERE id=?', (previous['source_id'],)).fetchone()
        current = store.db.execute('SELECT rowid FROM conversation WHERE id=?', (source['id'],)).fetchone()
        if order and current[0] < order[0]:
            raise ValueError('Existe una identificación más reciente; no se sustituye por una cita antigua.')
    device['identity'] = identity
    store.db.execute('UPDATE network_devices SET body=? WHERE id=?', (json.dumps(device), device['id']))
    store.db.commit()
    return dict(saved=True, device=device, note='Identificación atribuida al usuario; no verifica acceso ni concede permisos sobre el dispositivo.')
