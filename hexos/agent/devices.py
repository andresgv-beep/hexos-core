"""Inventario local observado e identificaciones respaldadas por citas del usuario."""
import json
import ipaddress
import re
from . import hosts
from .network import snapshot
from .work import now, string


# Cuánto vive un vecino sin nombre. Son cacharros de paso —un móvil, la tele, un
# invitado— y guardarlos convertía el inventario en un vertedero: 23 el día 12 y
# 31 el 16, con dos IPs reclamadas por dos fichas porque el DHCP las reasignó.
# Lo que la persona ha nombrado no caduca nunca; lo demás es de esta lectura.
TTL_ANONIMO = 60
# Mensajes de la persona, contando el del turno, donde puede constar la dirección.
MENSAJES_EVIDENCIA = 6


def endpoint_con_coma(value):
    """hosts.endpoint, leyendo como punto una coma que deja la dirección inválida.

    El 29/10 «https://servidorsrv1,ddns.net» se rechazó con un error genérico y la
    persona tuvo que reescribirla. Una coma nunca es válida en un nombre de equipo,
    así que leerla como punto no deduce nada; el resultado lo dice igualmente.
    """
    try:
        return hosts.endpoint(value)
    except ValueError:
        if ',' not in (value or ''):
            raise
        return hosts.endpoint(value.replace(',', '.'))


def literal_ip(text, value):
    """Una IP completa como unidad; 192.168.1.1 no casa dentro de .10."""
    return bool(re.search(r'(?<![0-9a-f:.])' + re.escape(value) + r'(?![0-9a-f:.])',
                          text or '', re.I))


def initialize(store):
    store.db.execute('CREATE TABLE IF NOT EXISTS network_devices (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
    # Una observación automática no es inventario. Las versiones anteriores
    # persistían vecinos e historiales DHCP para poder nombrarlos después. Al
    # arrancar se retira ese ruido, conservando identidad, MAC, direcciones fijas
    # dadas por la persona y solo las IP que aparezcan literalmente en su evidencia.
    for fila in list(store.db.execute('SELECT id, body FROM network_devices')):
        d = json.loads(fila['body'])
        identidad = d.get('identity') or {}
        if not identidad.get('name') and not d.get('pinned_host'):
            store.db.execute('DELETE FROM network_devices WHERE id=?', (fila['id'],))
            continue
        evidencia = identidad.get('evidence') or ''
        explicitas = list(d.get('saved_ips') or [])
        for entrada in d.get('latest_addresses') or d.get('addresses') or []:
            ip = entrada.get('ip')
            if ip and literal_ip(evidencia, ip) and ip not in explicitas:
                explicitas.append(ip)
        d.update(saved_ips=explicitas, addresses=[], latest_addresses=[],
                 in_latest_snapshot=False, last_observed_at=None)
        store.db.execute('UPDATE network_devices SET body=? WHERE id=?',
                         (json.dumps(d), fila['id']))
    store.db.commit()


def limpiar_anonimos(store, ttl=TTL_ANONIMO):
    """Quita del inventario los vecinos sin nombre que ya no son de ahora.

    Devuelve cuántos se fueron. Nunca toca un equipo identificado, ni uno con
    dirección fija o acceso guardado: eso lo puso la persona y es suyo.
    """
    from datetime import datetime, timedelta, timezone
    limite = (datetime.now(timezone.utc) - timedelta(seconds=ttl)).isoformat()
    fuera = []
    for fila in store.db.execute('SELECT id, body FROM network_devices'):
        d = json.loads(fila['body'])
        if (d.get('identity') or {}).get('name') or d.get('pinned_host'):
            continue
        visto = d.get('last_observed_at') or ''
        if visto < limite:
            fuera.append(fila['id'])
    if fuera:
        store.db.executemany('DELETE FROM network_devices WHERE id=?', [(i,) for i in fuera])
        store.db.commit()
    return len(fuera)


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
    """Compatibilidad: mirar y superponer en RAM, nunca persistir vecinos."""
    if rows is None:
        rows = {r['id']: json.loads(r['body']) for r in store.db.execute('SELECT * FROM network_devices')}
    observation = snapshot()
    return observation, ephemeral_rows(observation, rows)


def ephemeral_rows(observation, rows):
    """Superpone una instantánea en memoria sin escribir una sola IP en disco."""
    transient = json.loads(json.dumps(rows))
    for device in transient.values():
        device['in_latest_snapshot'] = False
        device['latest_addresses'] = []
    for neighbor in observation['neighbors']:
        key = neighbor['interface'] + '/' + neighbor['mac'].lower()
        device = transient.setdefault(key, dict(id=key, mac=neighbor['mac'].lower(),
            interface=neighbor['interface'], addresses=[], latest_addresses=[], identity=None))
        device['in_latest_snapshot'] = True
        device['last_observed_at'] = observation['observed_at']
        device.setdefault('latest_addresses', [])
        device['latest_addresses'].append(dict(
            ip=neighbor['ip'], state=neighbor['state'],
            observed_at=observation['observed_at']))
    return transient


def dispatch(store, name, args, turn_id=None, observation=None):
    # Antes de mirar o de listar: lo anónimo y viejo no es inventario, es ruido de
    # hace un rato. Identificar también limpia, para que nadie nombre un fantasma.
    if name in ('device.list', 'device.refresh', 'device.identify'):
        limpiar_anonimos(store, ttl=0)
    rows = {r['id']: json.loads(r['body']) for r in store.db.execute('SELECT * FROM network_devices')}
    if name == 'device.refresh':
        raise ValueError('device.refresh ya no persiste observaciones. Usa network.local; '
                         'para guardar un equipo concreto usa device.identify.')
    if name == 'device.list':
        query = args.get('query', '').casefold()
        terms = [v.strip() for v in re.split(r'\s+or\s+', query) if v.strip()]
        scope = (args.get('scope') or 'registered').casefold()
        scopes = {'registered', 'access', 'remote', 'local', 'unidentified', 'all'}
        if scope not in scopes:
            raise ValueError('scope no válido: usa registered, access, remote, local, '
                             'unidentified o all')
        # Un equipo con acceso guardado y sin ficha en el inventario se podía alcanzar
        # pero no salía al preguntar cuáles hay. Eso confunde a cualquiera: aparece
        # aquí, con su origen dicho, para que la lista sea TODO lo que se puede tocar.
        accesos = hosts.load(store.root)
        nombrados = {(d.get('identity') or {}).get('name', '').casefold() for d in rows.values()}
        for nombre, entrada in accesos.items():
            if nombre in nombrados:
                continue
            rows['acceso/' + nombre] = dict(
                id='acceso/' + nombre, mac=None, interface=None,
                pinned_host=entrada.get('host'), pinned_port=entrada.get('port'),
                pinned_original=entrada.get('original_address'),
                pinned_scheme=entrada.get('scheme'),
                addresses=[], latest_addresses=[], in_latest_snapshot=False,
                last_observed_at=None, only_access=True,
                identity=dict(name=nombre, kind=None, source='saved_access'))
        found = [d for d in rows.values()
                 if not terms or any(q in json.dumps(d, ensure_ascii=False).casefold()
                                     for q in terms)]
        found.sort(key=lambda d: (d['identity'] is None, d['id']))
        # `pinned_host` va dentro: sin él, un equipo de otra red salía en la lista
        # sin dirección ninguna —`latest_addresses` está vacío porque no se le ve
        # en la red— y la única forma de decir dónde está era recordarla de la
        # conversación, que es como empiezan las direcciones inventadas.
        # Una fila por equipo, sin claves vacías. Con 29 vecinos la versión larga
        # ocupaba 14.500 caracteres —unos 4.000 tokens— y dos consultas seguidas
        # llenaban el contexto y tumbaban el turno. Nada de lo que se sabe se
        # pierde: se quitan los nulos, la interfaz (ya va dentro de id), y las
        # direcciones se dan como IP, que es como se nombran.
        def fila(d):
            identidad = d.get('identity') or {}
            salida = dict(id=d['id'])
            for clave, valor in (('name', identidad.get('name')), ('kind', identidad.get('kind')),
                                 ('source', identidad.get('source')), ('mac', d.get('mac')),
                                 ('original_address', d.get('pinned_original')),
                                 ('scheme', d.get('pinned_scheme')),
                                 ('ssh_host', d.get('pinned_host')),
                                 ('ssh_port', d.get('pinned_port'))):
                if valor:
                    salida[clave] = valor
            ips = list(d.get('saved_ips') or [])
            if ips:
                salida['ips'] = ips
            if d.get('last_observed_at'):
                salida['seen'] = d['last_observed_at'][:19]
            if d.get('in_latest_snapshot'):
                salida['seen_now'] = True
            if identidad.get('name', '').casefold() in accesos:
                salida['has_access'] = True
            if d.get('only_access'):
                salida['only_access'] = True
            if not identidad:
                salida['unidentified'] = True
            return salida

        compact_all = [fila(d) for d in found]
        def pertenece(d):
            if scope == 'all':
                return True
            if scope == 'registered':
                return bool(d.get('name'))
            if scope == 'access':
                return bool(d.get('has_access'))
            if scope == 'remote':
                return bool(d.get('original_address') or d.get('ssh_host'))
            if scope == 'local':
                return bool(d.get('mac') or d.get('ips'))
            return not d.get('name')  # unidentified

        selected = [d for d in compact_all if pertenece(d)]
        counts = dict(
            registered=sum(bool(d.get('name')) for d in compact_all),
            with_access=sum(bool(d.get('has_access')) for d in compact_all),
            remote=sum(bool(d.get('original_address') or d.get('ssh_host')) for d in compact_all),
            local_observed=sum(bool(d.get('mac') or d.get('ips')) for d in compact_all),
            visible_in_last_observation=sum(bool(d.get('seen_now')) for d in compact_all),
            unidentified=sum(not d.get('name') for d in compact_all),
        )
        repetidos = duplicados(rows, accesos)
        # Una petición, una naturaleza y una lista. Antes se devolvían identificados
        # y anónimos juntos y el modelo confundía «guardado» con «visible ahora».
        return dict(scope=scope, items=selected[:48], counts=counts,
                    duplicates=repetidos, total=len(selected), truncated=len(selected)>48,
                    note='Inventario persistente, no una lectura actual. items contiene solo la '
                         'clase pedida por scope. registered=equipos con nombre; access=con '
                         'credencial SSH; remote=con dirección fija; local=observados alguna vez '
                         'en una red local; unidentified=sin nombre. Consulta network.local para '
                         'IPs y vecinos visibles ahora. '
                         'original_address es exactamente lo que escribió la persona; scheme '
                         'dice su protocolo. ssh_host y ssh_port son la ruta normalizada que usa '
                         'la conexión y no sustituyen a la dirección original. Los equipos sin '
                         'ruta remota se ven por ips. seen_now es que se le vio en la '
                         'última lectura de red. Las claves vacías se omiten: '
                         'unidentified significa sin identificar. Un filtro sin coincidencias no significa que el inventario esté vacío: consulta sin query. '
                         'has_access dice si hay credencial guardada para ese nombre; sin ella no se '
                         'puede leer aunque esté identificado. only_access son los que solo existen por '
                         'su acceso guardado, sin ficha en la red. '
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
        # Un equipo que solo existe por su acceso guardado también se puede quitar:
        # si sale en la lista y no se puede borrar, la lista miente.
        accesos = hosts.load(store.root)
        nombrados = {(d.get('identity') or {}).get('name', '').casefold() for d in rows.values()}
        if buscado in accesos and buscado not in nombrados:
            hosts.forget(store.root, buscado)
            return dict(forgotten=buscado, removed_record=True, forgotten_access=buscado,
                        note='Solo existía por su acceso guardado, sin ficha en la red: se ha '
                             'revocado y ya no queda nada suyo.')
        elegidos = [d for d in rows.values()
                    if buscado in (d['id'].casefold(), (d.get('mac') or '').casefold())
                    or (d.get('identity') or {}).get('name', '').casefold() == buscado
                    or (d.get('pinned_host') or '').casefold() == buscado
                    or (d.get('pinned_original') or '').casefold() == buscado
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
        # El modelo puede quitar el esquema o el puerto aunque se le ordene no
        # hacerlo. La autoridad es el mensaje de la persona: se recupera de ahí
        # el literal que resuelve al mismo host propuesto por la llamada.
        propuesto = string(args['host'], 'host', 300).strip()
        destino_propuesto, _ = endpoint_con_coma(propuesto)
        fila = store.db.execute("SELECT id,text,rowid FROM conversation WHERE id=? AND role='user'",
                                (turn_id,)).fetchone() if turn_id else None
        if not fila:
            raise ValueError('No hay mensaje de este turno del que tomar la evidencia')
        # El 29/10 la persona dio la URL y en el turno siguiente dijo «inténtalo
        # sin protocolo»: mirar solo ese turno obligaba a reescribirla. Cuentan sus
        # mensajes recientes, nunca los del asistente.
        mensajes = [fila] + list(store.db.execute(
            "SELECT id,text,rowid FROM conversation WHERE role='user' AND rowid<? "
            'ORDER BY rowid DESC LIMIT ?', (fila['rowid'], MENSAJES_EVIDENCIA - 1)))
        candidatos = []
        for orden, mensaje in enumerate(mensajes):
            for token in re.findall(r'\S+', mensaje['text']):
                literal = token.strip('"\'`()[]{}<>,;.!?¿¡')
                if not literal:
                    continue
                try:
                    host_literal, _ = endpoint_con_coma(literal)
                except (TypeError, ValueError):
                    continue
                leido = literal.replace(',', '.')
                if host_literal.casefold() == destino_propuesto.casefold():
                    candidatos.append((orden, literal, leido, mensaje))
        # Misma regla que identificar y que guardar un hecho: la dirección tiene que
        # estar en las palabras de la persona. Así no se registra un equipo deducido,
        # y menos uno al que luego se le mandaría una contraseña.
        if not candidatos:
            raise ValueError('Esa dirección no aparece en el mensaje de la persona ni en sus '
                             'mensajes recientes. Registra solo la que te haya dado, tal cual la escribió.')
        # El mensaje más reciente manda; dentro de él, una URL completa contiene
        # más evidencia que el host recortado.
        _, literal, original, mensaje = min(candidatos, key=lambda c: (
            c[0], not re.match(r'^[a-z][a-z0-9+.-]*://', c[1], re.I), -len(c[1])))
        cita = mensaje['text']
        # El diccionario es también el que acabará en la traza: debe registrar
        # el literal realmente ejecutado, no la versión recortada por el modelo.
        args['host'] = original
        destino, puerto = hosts.endpoint(original)
        esquema = re.match(r'^([a-z][a-z0-9+.-]*)://', original, re.I)
        esquema = esquema.group(1).casefold() if esquema else None
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
                        pinned_original=original, pinned_scheme=esquema,
                        mac=anterior.get('mac') if observado else None,
                        interface=anterior.get('interface') if observado else None,
                        addresses=anterior.get('addresses', []),
                        latest_addresses=anterior.get('latest_addresses', []) if observado else [],
                        in_latest_snapshot=anterior.get('in_latest_snapshot', False) if observado else False,
                        last_observed_at=anterior.get('last_observed_at') if observado else None,
                        identity=dict(name=etiqueta, kind=args.get('kind') or None,
                                      source='user_statement', source_id=mensaje['id'],
                                      evidence=cita[:1000], recorded_at=now()))
        store.db.execute('INSERT OR REPLACE INTO network_devices VALUES (?,?)',
                         (clave, json.dumps(registro)))
        store.db.commit()
        salida = dict(saved=True, device=etiqueta, original_address=original,
                      scheme=esquema, ssh_host=destino,
                      ssh_port=registro['pinned_port'], pinned=True,
                      attached_to_known=bool(mismos),
                      note='Registrado con dirección fija: no se busca en los vecinos de la red y '
                           'sigue valiendo desde cualquier sitio. Esto no comprueba que se llegue a '
                           'él ni concede acceso; las credenciales se piden aparte por la ventana.')
        if literal != original:
            salida.update(written_as=literal, correction=(
                'La persona escribió «' + literal + '» y se ha leído como «' + original +
                '»: una coma no es válida en una dirección. Díselo al confirmar el registro.'))
        return salida
    if observation:
        rows = ephemeral_rows(observation, rows)
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
    # Ese nombre puede existir ya. Si es un registro remoto —el mismo equipo visto
    # desde fuera—, se absorbe: su dirección fija pasa a esta ficha y el remoto
    # desaparece. Si es otro equipo observado, dos máquinas no pueden llamarse igual.
    homonimos = [d for d in rows.values()
                 if d['id'] != device['id']
                 and (d.get('identity') or {}).get('name', '').casefold() == label.casefold()]
    absorbido = None
    for otro in homonimos:
        if not otro['id'].startswith('remoto/'):
            raise ValueError('Ya hay otro equipo guardado como ' + repr(label) +
                             ' (' + otro['id'] + '). Dale otro nombre, o olvida ese primero.')
        device['pinned_host'] = device.get('pinned_host') or otro.get('pinned_host')
        device['pinned_port'] = device.get('pinned_port') or otro.get('pinned_port')
        device['pinned_original'] = (device.get('pinned_original')
                                     or otro.get('pinned_original'))
        device['pinned_scheme'] = device.get('pinned_scheme') or otro.get('pinned_scheme')
        store.db.execute('DELETE FROM network_devices WHERE id=?', (otro['id'],))
        absorbido = otro['id']
    identity = dict(name=label, kind=kind or None, source='user_statement', source_id=source['id'],
                    evidence=quote, recorded_at=now())
    previous = device.get('identity')
    if previous and previous['source_id'] != source['id']:
        order = store.db.execute('SELECT rowid FROM conversation WHERE id=?', (previous['source_id'],)).fetchone()
        current = store.db.execute('SELECT rowid FROM conversation WHERE id=?', (source['id'],)).fetchone()
        if order and current[0] < order[0]:
            raise ValueError('Existe una identificación más reciente; no se sustituye por una cita antigua.')
    device['identity'] = identity
    # Solo una IP completa escrita por la persona se vuelve dato persistente.
    # Un sufijo, o una IP que apareció únicamente en la observación, sirve para
    # seleccionar el equipo pero no autoriza a guardar la dirección completa.
    saved_ips = list(device.get('saved_ips') or [])
    for entrada in device.get('latest_addresses') or []:
        ip = entrada.get('ip')
        if ip and literal_ip(quote, ip) and ip not in saved_ips:
            saved_ips.append(ip)
    persisted = dict(device, saved_ips=saved_ips, addresses=[], latest_addresses=[],
                     in_latest_snapshot=False, last_observed_at=None)
    store.db.execute('INSERT OR REPLACE INTO network_devices VALUES (?,?)',
                     (persisted['id'], json.dumps(persisted)))
    store.db.commit()
    return dict(saved=True, device=persisted, absorbed=absorbido,
                note='Identificación atribuida al usuario; no verifica acceso ni concede permisos '
                     'sobre el dispositivo.' +
                     (' Se absorbió el registro remoto que tenía ese nombre: ahora es una sola '
                      'ficha con su dirección fija y su sitio en la red.' if absorbido else ''))
