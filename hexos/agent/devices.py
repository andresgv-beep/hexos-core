"""Inventario local observado e identificaciones respaldadas por citas del usuario."""
import json
import ipaddress
import re
from . import hosts
from .network import snapshot
from .work import now, string


def initialize(store):
    store.db.execute('CREATE TABLE IF NOT EXISTS network_devices (id TEXT PRIMARY KEY, body TEXT NOT NULL)')


def duplicados(rows, credenciales):
    """Equipos registrados que acaban en la misma máquina.

    Dos nombres para un NAS no es un detalle estético: se le puede dar acceso a uno
    y pedirle lecturas al otro, y parecerá que no tiene credenciales cuando sí las
    tiene. Aquí solo se SEÑALA; juntarlos o borrar uno lo decide la persona.
    """
    porDestino = {}
    for d in rows.values():
        nombre = (d.get('identity') or {}).get('name')
        if not nombre:
            continue
        # A dónde va de verdad: manda la dirección de su credencial, luego la fija,
        # y si no tiene ninguna, su MAC — que es lo que identifica al equipo en la red.
        destino = ((credenciales.get(nombre.casefold()) or {}).get('host')
                   or d.get('pinned_host') or d.get('mac'))
        if destino:
            porDestino.setdefault(destino.casefold(), []).append(nombre)
    return [dict(destination=destino, devices=sorted(nombres),
                 note='Estos nombres llevan al mismo equipo. Pregunta cuál conservar antes de '
                      'tocar nada; device_forget borra el que sobre. Mientras haya dos, una '
                      'credencial guardada en uno no sirve al pedir algo por el otro.')
            for destino, nombres in sorted(porDestino.items()) if len(nombres) > 1]


def cola(ip, suffix):
    """Los últimos octetos de `ip`, tantos como traiga `suffix`."""
    return '.'.join(ip.split('.')[-len(suffix.split('.')):])


def annotate(store, observation):
    """Unir lectura actual con identidad persistida, sin guardar ni inferir por IP.

    Se devuelven las dos mitades, no solo la identificada: un vecino sin nombre
    guardado no es un dato que falte, es la respuesta a «cuáles no están
    registrados». Enumerarlos a mano desde la lista cruda salía mal —se colaban
    las direcciones de este mismo equipo, que vienen de `ip address` y no de
    `ip neigh`, y alguna IPv6 larga acababa recortada por el camino.
    """
    known = {r['id']: json.loads(r['body']) for r in store.db.execute('SELECT * FROM network_devices')}
    unresolved = observation['unresolved_entries']
    identified, unidentified = [], []
    for neighbor in observation['neighbors']:
        device = known.get(neighbor['interface'] + '/' + neighbor['mac'].lower())
        identity = device.get('identity') if device else None
        neighbor['identity'] = {k:identity[k] for k in ('name','kind','source')} if identity else None
        # Un vecino son cuatro datos, no siete: `interface` es la misma para todos
        # y `recently_reachable` repetía lo que ya dice `state`. Multiplicado por
        # diecisiete entradas, esa repetición se comía el contexto del turno
        # siguiente y la tercera pregunta moría sin sitio para responder.
        fila = dict(ip=neighbor['ip'], mac=neighbor['mac'],
                    state=','.join(neighbor['state']), via=neighbor['interface'])
        if identity:
            # `identity_source` y no `source`: leído como «source: static» se
            # confundía con el estado de red del equipo, que es otra cosa.
            identified.append(dict(fila, name=identity['name'], kind=identity['kind'],
                                   identity_source=identity['source']))
        else:
            unidentified.append(fila)
    propias = sorted({address['ip'] for interface in observation['interfaces']
                      for address in interface['addresses'] if address.get('ip')})
    # `known_neighbors` es el total y se estaba leyendo como «los que faltan por
    # identificar»: 16 en vez de 14. Dos contadores para lo mismo es uno de más,
    # así que el total solo vive en `counts`, con sus dos sumandos al lado.
    # Fuera `neighbors`: las dos mitades son exactamente esos mismos vecinos con
    # los mismos campos, así que mandarlo era enviar la red dos veces —2.956 de
    # 7.813 caracteres— y con eso el segundo turno ya no cabía en el contexto.
    # `interfaces` se resume en own_addresses y su detalle no lo usa nadie.
    observation = {k: v for k, v in observation.items()
                   if k not in ('known_neighbors', 'unresolved_entries',
                                'neighbors', 'interfaces')}
    return dict(identified_neighbors=identified, unidentified_neighbors=unidentified,
                counts=dict(identified=len(identified), unidentified=len(unidentified),
                            total_neighbors=len(identified) + len(unidentified),
                            unresolved=unresolved),
                own_addresses=propias,
                lists_note='identified_neighbors y unidentified_neighbors son la partición '
                           'completa de los vecinos y counts ya trae sus tamaños: no hay que '
                           'contarlos ni deducir una lista de la otra. Al decir cuántos hay sin '
                           'identificar, usa counts.unidentified, nunca el total. own_addresses '
                           'son las direcciones DE ESTE EQUIPO, no dispositivos de la red.',
                **observation)


def observe(store, rows=None):
    """Mirar la red y dejar constancia de lo visto. Devuelve (lectura, registros).

    Lo hace también `network.local`: enseñar vecinos sin guardarlos dejaba ver
    equipos que luego no se podían nombrar —«la que termina en 129» no existía en
    el inventario— y dejaba en pie los de otra red marcados como recién vistos, así
    que un sufijo casaba con el fantasma. Mostrar y registrar tienen que ser el
    mismo acto o lo que se ve y lo que se puede tocar se separan.
    """
    if rows is None:
        rows = {r['id']: json.loads(r['body']) for r in store.db.execute('SELECT * FROM network_devices')}
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
    return observation, rows


def dispatch(store, name, args, turn_id=None):
    rows = {r['id']: json.loads(r['body']) for r in store.db.execute('SELECT * FROM network_devices')}
    if name == 'device.refresh':
        observation, rows = observe(store, rows)
        return dict(saved=True, observed_at=observation['observed_at'], devices=len(rows),
                    observed_devices=sum(d['in_latest_snapshot'] for d in rows.values()),
                    truncated=observation['truncated'], note=observation['note'])
    if name == 'device.list':
        query = args.get('query', '').casefold()
        terms = [v.strip() for v in re.split(r'\s+or\s+', query) if v.strip()]
        found = [d for d in rows.values() if not terms or any(q in json.dumps(d, ensure_ascii=False).casefold() for q in terms)]
        found.sort(key=lambda d: (d['identity'] is None, d['id']))
        # `pinned_host` va dentro: sin él, un equipo de otra red salía en la lista
        # sin dirección ninguna —`latest_addresses` está vacío porque no se le ve
        # en la red— y la única forma de decir dónde está era recordarla de la
        # conversación, que es como empiezan las direcciones inventadas.
        compact = [{k:d.get(k) for k in ('id','mac','interface','last_observed_at',
                                         'in_latest_snapshot','latest_addresses',
                                         'pinned_host','pinned_port')} |
                   {'identity':{k:d['identity'][k] for k in ('name','kind','source')} if d['identity'] else None} for d in found[:64]]
        repetidos = duplicados(rows, hosts.load(store.root))
        return dict(identified_devices=[d for d in compact if d['identity']], devices=compact,
                    duplicates=repetidos, total=len(found), truncated=len(found)>64,
                    note='Inventario histórico. Consulta network.local para el estado actual. '
                         'pinned_host es la dirección fija de un equipo de otra red; los de esta '
                         'red no la tienen y se ven por latest_addresses. '
                         'identity=null significa sin identificar. Un filtro sin coincidencias no significa que el inventario esté vacío: consulta sin query. '
                         'MAC e interfaz agrupan observaciones, no garantizan identidad física.')
    if name == 'device.forget':
        objetivo = string(args['target'], 'target', 100).strip()
        fila = store.db.execute("SELECT id,text FROM conversation WHERE id=? AND role='user'",
                                (turn_id,)).fetchone() if turn_id else None
        if not fila:
            raise ValueError('No hay mensaje de este turno del que tomar la evidencia')
        # Borrar es la única operación que no se puede deshacer leyendo otra vez, así
        # que tiene que estar en las palabras de la persona: ni el nombre ni la
        # dirección pueden salir de una deducción del modelo.
        if objetivo.casefold() not in fila['text'].casefold():
            raise ValueError('Ese equipo no aparece en el mensaje de la persona. Borra solo lo que '
                             'te hayan nombrado, tal cual lo escribieron.')
        buscado = objetivo.casefold()
        elegidos = [d for d in rows.values()
                    if buscado in (d['id'].casefold(), (d.get('mac') or '').casefold())
                    or (d.get('identity') or {}).get('name', '').casefold() == buscado
                    or (d.get('pinned_host') or '').casefold() == buscado
                    or any(a['ip'] == buscado for a in d.get('latest_addresses', []))]
        if len(elegidos) > 1:
            # Decir «ambiguo» y callar deja a la persona sin salida. Se nombran las
            # fichas para que pueda borrar la que quiera por su id.
            raise ValueError('Hay ' + str(len(elegidos)) + ' fichas llamadas ' + repr(objetivo) +
                             ': ' + ', '.join(repr(d['id']) for d in elegidos) +
                             '. Repite el borrado con el id de la que sobre.')
        if not elegidos:
            conocidos = sorted((d.get('identity') or {}).get('name') for d in rows.values()
                               if d.get('identity'))
            raise ValueError('No hay ningún equipo guardado como ' + repr(objetivo) +
                             '. Guardados: ' + (', '.join(conocidos) or 'ninguno') + '.')
        device = elegidos[0]
        etiqueta = (device.get('identity') or {}).get('name')
        # Un registro remoto desaparece entero; uno observado en la red volvería a
        # aparecer en la lectura siguiente, así que lo que se olvida es su nombre.
        remoto = device['id'].startswith('remoto/')
        if remoto:
            store.db.execute('DELETE FROM network_devices WHERE id=?', (device['id'],))
        else:
            device['identity'] = None
            store.db.execute('UPDATE network_devices SET body=? WHERE id=?',
                             (json.dumps(device), device['id']))
        store.db.commit()
        acceso = None
        if etiqueta:
            try:
                acceso = hosts.forget(store.root, etiqueta)['forgotten']
            except (ValueError, OSError):
                acceso = None
        return dict(forgotten=etiqueta or device['id'], removed_record=remoto,
                    forgotten_access=acceso,
                    note=('Registro borrado entero.' if remoto else
                          'Nombre olvidado. El equipo sigue en la red y volverá a salir en la '
                          'próxima lectura, ya sin nombre.') +
                         (' También se revocó su acceso guardado.' if acceso else
                          ' No tenía acceso guardado.'))
    if name == 'device.remote':
        # Un equipo de otra red no aparece nunca en la tabla ARP, así que
        # device.identify no puede alcanzarlo: no hay nada que nombrar. Este
        # registra el nombre CON su dirección, y se resuelve por ella.
        etiqueta = string(args['name'], 'name', 100)
        # Acepta la URL tal cual se pega, con su puerto si lo trae.
        destino, puerto = hosts.endpoint(args['host'])
        fila = store.db.execute("SELECT id,text FROM conversation WHERE id=? AND role='user'",
                                (turn_id,)).fetchone() if turn_id else None
        if not fila:
            raise ValueError('No hay mensaje de este turno del que tomar la evidencia')
        cita = fila['text']
        # Misma regla que identificar y que guardar un hecho: la dirección tiene que
        # estar en las palabras de la persona. Así no se registra un equipo deducido,
        # y menos uno al que luego se le mandaría una contraseña.
        if destino not in cita.casefold():
            raise ValueError('Esa dirección no aparece en el mensaje de la persona. Registra solo '
                             'la que te haya dado, tal cual la escribió.')
        # Si ya hay un equipo con ese nombre —visto en la red o registrado antes—,
        # la dirección se le añade a ÉL. Crear otro registro dejaría dos fichas de
        # la misma máquina, que es como acabaron 'synology 1' y 'servidor 1'
        # apuntando al mismo sitio sin que nadie supiera cuál valía.
        mismos = [d for d in rows.values()
                  if (d.get('identity') or {}).get('name', '').casefold() == etiqueta.casefold()]
        if len(mismos) > 1:
            raise ValueError('Hay varios equipos guardados como ' + repr(etiqueta) +
                             '; renombra o borra uno antes de darle dirección.')
        clave = mismos[0]['id'] if mismos else 'remoto/' + etiqueta.casefold()
        anterior = rows.get(clave, {})
        # A uno que está en la red se le añade la dirección sin tocar lo observado:
        # sigue siendo el mismo equipo y se le sigue viendo.
        observado = bool(anterior.get('mac'))
        registro = dict(anterior, id=clave, pinned_host=destino,
                        pinned_port=puerto or anterior.get('pinned_port'),
                        mac=anterior.get('mac') if observado else None,
                        interface=anterior.get('interface') if observado else None,
                        addresses=anterior.get('addresses', []),
                        latest_addresses=anterior.get('latest_addresses', []) if observado else [],
                        in_latest_snapshot=anterior.get('in_latest_snapshot', False) if observado else False,
                        last_observed_at=anterior.get('last_observed_at') if observado else None,
                        identity=dict(name=etiqueta, kind=args.get('kind') or None,
                                      source='user_statement', source_id=fila['id'],
                                      evidence=cita[:1000], recorded_at=now()))
        store.db.execute('INSERT OR REPLACE INTO network_devices VALUES (?,?)',
                         (clave, json.dumps(registro)))
        store.db.commit()
        return dict(saved=True, device=etiqueta, host=destino,
                    port=registro['pinned_port'], pinned=True,
                    attached_to_known=bool(mismos),
                    note='Registrado con dirección fija: no se busca en los vecinos de la red y '
                         'sigue valiendo desde cualquier sitio. Esto no comprueba que se llegue a '
                         'él ni concede acceso; las credenciales se piden aparte por la ventana.')
    target = args['target'].casefold()
    candidates = [d for d in rows.values() if target in (d['id'].casefold(), d['mac'])]
    if not candidates:
        suffix = target.lstrip('.')
        # «la que termina en 1.129» es como se habla de una IP, no solo «129».
        short = bool(re.fullmatch(r'\d{1,3}(\.\d{1,3})?', suffix)) and \
            all(0 <= int(parte) <= 255 for parte in suffix.split('.'))
        try:
            if not short:
                target = str(ipaddress.ip_address(target))
        except ValueError:
            raise ValueError('Usa una IP completa, sus últimos octetos, MAC o id del inventario; '
                             'consulta device.list.')
        candidates = [d for d in rows.values() if d.get('in_latest_snapshot') and
                      any(a['ip'] == target or (short and cola(a['ip'], suffix) == suffix)
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
    # Se admiten uno y dos octetos: la gente dice «la que termina en 1.129».
    for address in device.get('latest_addresses', []):
        if ':' in address['ip']:
            continue
        for trozos in (1, 2):
            suffix = '.'.join(address['ip'].split('.')[-trozos:])
            matches = [d for d in rows.values() if d.get('in_latest_snapshot') and any(
                ':' not in a['ip'] and cola(a['ip'], suffix) == suffix
                for a in d.get('latest_addresses', []))]
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
