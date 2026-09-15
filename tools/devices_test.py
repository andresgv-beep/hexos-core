import tempfile
import unittest
from unittest.mock import patch
from hexos.agent.chat import Agent
from hexos.agent.devices import dispatch
from hexos.agent.devices import annotate


def observation(mac='aa:bb:cc:dd:ee:ff', ip='192.168.1.10'):
    """Doble de snapshot(): mismas claves, o annotate no vería lo que ve en real."""
    return dict(observed_at='2026-09-12T12:00:00Z', truncated=False, note='passive',
                unresolved_entries=0,
                interfaces=[dict(name='lo', state='UNKNOWN',
                                 addresses=[dict(ip='127.0.0.1', prefixlen=8, family='inet')]),
                            dict(name='eth0', state='UP',
                                 addresses=[dict(ip='192.168.1.41', prefixlen=24, family='inet')])],
                neighbors=[dict(mac=mac, ip=ip, interface='eth0', state=['STALE'],
                                recently_reachable=False)])


class DevicesTest(unittest.TestCase):
    def test_suffix_ambiguity_never_labels_a_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent=Agent(tmp,None)
            with agent.store() as s:
                data=observation()
                data['neighbors'] += [dict(ip='10.0.0.10',mac='11:22:33:44:55:66',interface='eth1',state=['STALE'],recently_reachable=False)]
                with patch('hexos.agent.devices.snapshot',return_value=data):
                    agent.tool(s,'device.refresh',{})
                quote='el 10 es mi NAS'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',('u','now','user',quote,quote))
                s.db.commit()
                with self.assertRaises(ValueError):
                    agent.tool(s,'device.identify',dict(target='10',name='NAS'),turn_id='u')
                self.assertTrue(all(d.get('unidentified') for d in agent.tool(s,'device.list',{})['devices']))

    def test_two_suffixes_use_current_message_and_reject_wrong_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                data = observation()
                data['neighbors'] = [dict(ip='192.168.1.'+str(n), mac=f'aa:bb:cc:dd:ee:{n:02x}', interface='eth0',
                                          state=['STALE'], recently_reachable=False) for n in (243,131,249)]
                with patch('hexos.agent.devices.snapshot', return_value=data):
                    agent.tool(s,'device.refresh',{})
                quote='guara el que termina en 243 como synology, el 131 como nimos nas'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',quote,quote))
                s.db.commit()
                with self.assertRaises(ValueError):
                    agent.tool(s,'device.identify',dict(target='192.168.1.249',name='synology'),turn_id='u')
                for target, name in [('243','synology'),('131','nimos nas')]:
                    result=agent.tool(s,'device.identify',dict(target=target,name=name),turn_id='u')
                    self.assertEqual(result['device']['identity']['source_id'],'u')
                    self.assertEqual(result['device']['identity']['name'],name)
                before=s.db.total_changes
                self.assertEqual(agent.tool(s,'device.list',{'query':'synology OR nimos nas'})['total'],2)
                enriched=annotate(s,data)
                self.assertEqual({n['name'] for n in enriched['identified_neighbors']},{'synology','nimos nas'})
                impostor=observation(mac='00:11:22:33:44:55',ip='192.168.1.243')
                self.assertEqual(annotate(s,impostor)['identified_neighbors'],[])
                self.assertEqual(s.db.total_changes,before)
                with self.assertRaises(ValueError):
                    agent.tool(s,'device.identify',dict(target='131',name='synology'),turn_id='u')

    def test_las_dos_mitades_son_la_particion_completa_de_los_vecinos(self):
        # «Cuáles no están registradas» tiene que ser un campo, no un ejercicio
        # de resta que el modelo hace a mano sobre la lista cruda.
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                data = observation()
                data['neighbors'] += [dict(ip='192.168.1.11', mac='11:22:33:44:55:66',
                                           interface='eth0', state=['REACHABLE'],
                                           recently_reachable=True)]
                with patch('hexos.agent.devices.snapshot', return_value=data):
                    agent.tool(s, 'device.refresh', {})
                quote = 'el 10 es mi synology'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',quote,quote))
                s.db.commit()
                agent.tool(s, 'device.identify', dict(target='192.168.1.10', name='synology'), turn_id='u')
                enriquecido = annotate(s, data)
                self.assertEqual([n['ip'] for n in enriquecido['identified_neighbors']], ['192.168.1.10'])
                self.assertEqual([n['ip'] for n in enriquecido['unidentified_neighbors']], ['192.168.1.11'])
                # Cuatro campos por vecino: repetir la interfaz y un booleano
                # derivable diecisiete veces se comía el contexto del turno siguiente.
                self.assertEqual(set(enriquecido['unidentified_neighbors'][0]),
                                 {'ip', 'mac', 'state', 'via'})
                self.assertEqual(enriquecido['counts'],
                                 dict(identified=1, unidentified=1, total_neighbors=2, unresolved=0))
                # Un segundo contador del total se leía como «los que faltan»: 16 en vez de 14.
                self.assertNotIn('known_neighbors', enriquecido)
                # Mandar además la lista cruda era enviar la red dos veces, y con
                # eso el turno siguiente se quedaba sin contexto.
                self.assertNotIn('neighbors', enriquecido)
                # Sin la MAC en las dos mitades no se puede hablar de un equipo sin nombre.
                for lista in ('identified_neighbors', 'unidentified_neighbors'):
                    self.assertTrue(all(n['mac'] for n in enriquecido[lista]), lista)
                # `source: static` se leía como estado de red; el nombre lo desambigua.
                identificado = enriquecido['identified_neighbors'][0]
                self.assertIn('identity_source', identificado)
                self.assertNotIn('source', identificado)

    def test_las_direcciones_propias_no_se_cuelan_entre_los_vecinos(self):
        # El modelo llegó a listar 127.0.0.1 y la IP del portátil como si fueran
        # dispositivos de la red: vienen de `ip address`, no de `ip neigh`.
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                enriquecido = annotate(s, observation())
                self.assertEqual(enriquecido['own_addresses'], ['127.0.0.1', '192.168.1.41'])
                vecinos = enriquecido['identified_neighbors'] + enriquecido['unidentified_neighbors']
                self.assertEqual([n['ip'] for n in vecinos], ['192.168.1.10'])
                self.assertIn('no dispositivos de la red', enriquecido['lists_note'])

    def test_un_equipo_de_otra_red_se_registra_por_su_direccion(self):
        # device_identify no puede alcanzarlo: no está ni estará en la tabla ARP.
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                dicho = 'conéctate a servidorsrv1.ddns.net, llámalo synology 1'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',dicho,dicho))
                s.db.commit()
                resultado = agent.tool(s, 'device.remote',
                                       dict(name='synology 1', host='servidorsrv1.ddns.net'), turn_id='u')
                self.assertTrue(resultado['pinned'])
                from hexos.agent.hosts import resolve
                located = resolve(tmp, 'synology 1')
                self.assertEqual(located['host'], 'servidorsrv1.ddns.net')
                self.assertTrue(located['pinned'])
                # Y aparece en el inventario como cualquier otro equipo con nombre.
                nombres = [d['name'] for d in agent.tool(s, 'device.list', {})['devices']
                           if d.get('name')]
                self.assertIn('synology 1', nombres)

    def test_acepta_la_url_tal_cual_se_pega_y_se_queda_el_puerto(self):
        # Rechazar «https://…» obligaba a la persona a reescribirla a mano, y el
        # puerto que traía dentro era justo el dato que faltaba.
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                dicho = 'conéctate a https://servidorsrv1.ddns.net:30 y llámalo servidor 1'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',dicho,dicho))
                s.db.commit()
                r = agent.tool(s, 'device.remote',
                               dict(name='servidor 1', host='https://servidorsrv1.ddns.net:30'), turn_id='u')
                self.assertEqual((r['host'], r['port']), ('servidorsrv1.ddns.net', 30))
                from hexos.agent.hosts import resolve
                self.assertEqual(resolve(tmp, 'servidor 1')['port'], 30)

    def test_no_registra_una_direccion_que_la_persona_no_dijo(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                dicho = 'añade mi servidor de casa'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',dicho,dicho))
                s.db.commit()
                with self.assertRaises(ValueError) as caught:
                    agent.tool(s, 'device.remote', dict(name='casa', host='5.183.220.230'), turn_id='u')
                self.assertIn('no aparece en el mensaje', str(caught.exception))
                # Y sin turno tampoco: la evidencia no la pone el modelo.
                with self.assertRaises(ValueError):
                    agent.tool(s, 'device.remote', dict(name='casa', host='5.183.220.230'))

    def test_una_direccion_que_no_lo_es_no_entra(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                dicho = 'registra -oProxyCommand=id como servidor'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',dicho,dicho))
                s.db.commit()
                with self.assertRaises(ValueError):
                    agent.tool(s, 'device.remote',
                               dict(name='servidor', host='-oProxyCommand=id'), turn_id='u')

    def test_darle_una_url_a_un_equipo_que_ya_esta_en_la_red_no_lo_duplica(self):
        # Antes creaba una segunda ficha de la misma máquina, y luego nadie sabía
        # cuál valía. La dirección se le añade al que ya existe.
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                with patch('hexos.agent.devices.snapshot', return_value=observation()):
                    agent.tool(s, 'device.refresh', {})
                dicho = 'el 192.168.1.10 es el synology 2'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',dicho,dicho))
                s.db.commit()
                agent.tool(s, 'device.identify', dict(target='192.168.1.10', name='synology 2'), turn_id='u')
                url = 'synology 2 también está en https://casa.ddns.net:30'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u2','now','user',url,url))
                s.db.commit()
                r = agent.tool(s, 'device.remote',
                               dict(name='synology 2', host='https://casa.ddns.net:30'), turn_id='u2')
                self.assertTrue(r['attached_to_known'])
                lista = agent.tool(s, 'device.list', {})
                self.assertEqual(lista['total'], 1, 'una máquina, una ficha')
                ficha = lista['identified_devices'][0]
                self.assertEqual((ficha['host'], ficha['port']), ('casa.ddns.net', 30))
                # Y sigue siendo el equipo que se ve en la red: no se pierde su MAC.
                self.assertEqual(ficha['mac'], 'aa:bb:cc:dd:ee:ff')
                self.assertTrue(ficha['seen_now'])
                # La dirección fija manda al resolver, que es la que sirve desde fuera.
                from hexos.agent.hosts import resolve
                self.assertEqual(resolve(tmp, 'synology 2')['host'], 'casa.ddns.net')

    def test_la_lista_dice_donde_esta_un_equipo_de_otra_red(self):
        # Sin la dirección fija en la lista, un equipo remoto salía sin dirección
        # y la única forma de decir dónde estaba era recordarla de la conversación.
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                dicho = 'registra servidor 1 en https://casa.ddns.net:30'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',dicho,dicho))
                s.db.commit()
                agent.tool(s, 'device.remote',
                           dict(name='servidor 1', host='https://casa.ddns.net:30'), turn_id='u')
                fila = agent.tool(s, 'device.list', {})['identified_devices'][0]
                self.assertEqual(fila['host'], 'casa.ddns.net')
                self.assertEqual(fila['port'], 30)
                self.assertNotIn('ips', fila, 'un equipo de otra red no tiene IP en esta')

    def test_identificar_en_casa_absorbe_el_registro_remoto_del_mismo_nombre(self):
        # Al volver a su red, «el 192.168.1.10 es servidorsrv1» creaba una SEGUNDA
        # ficha y volvía el duplicado. Ahora se juntan en una con los dos caminos.
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                fuera = 'registra servidorsrv1 en https://casa.ddns.net:30'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',fuera,fuera))
                s.db.commit()
                agent.tool(s, 'device.remote', dict(name='servidorsrv1', host='https://casa.ddns.net:30'), turn_id='u')
                # En casa y a la vista: REACHABLE, que es lo que hace mandar a la IP local.
                encasa = observation()
                encasa['neighbors'][0].update(state=['REACHABLE'], recently_reachable=True)
                with patch('hexos.agent.devices.snapshot', return_value=encasa):
                    agent.tool(s, 'device.refresh', {})
                dentro = 'el 192.168.1.10 es servidorsrv1'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u2','now','user',dentro,dentro))
                s.db.commit()
                r = agent.tool(s, 'device.identify', dict(target='192.168.1.10', name='servidorsrv1'), turn_id='u2')
                self.assertEqual(r['absorbed'], 'remoto/servidorsrv1')
                lista = agent.tool(s, 'device.list', {})
                self.assertEqual(lista['duplicates'], [], 'una máquina, una ficha')
                ficha = lista['identified_devices'][0]
                self.assertEqual(ficha['mac'], 'aa:bb:cc:dd:ee:ff')
                self.assertEqual((ficha['host'], ficha['port']), ('casa.ddns.net', 30))
                # Y con los dos caminos: la IP local primero por estar a la vista.
                from hexos.agent.hosts import resolve
                ruta = resolve(tmp, 'servidorsrv1')
                self.assertEqual(ruta['host'], '192.168.1.10')
                self.assertEqual([a['host'] for a in ruta['alternatives']], ['casa.ddns.net'])

    def test_dos_equipos_de_la_red_no_pueden_llamarse_igual(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                data = observation()
                data['neighbors'] += [dict(ip='192.168.1.11', mac='11:22:33:44:55:66',
                                           interface='eth0', state=['REACHABLE'], recently_reachable=True)]
                with patch('hexos.agent.devices.snapshot', return_value=data):
                    agent.tool(s, 'device.refresh', {})
                dicho = 'el 192.168.1.10 es el nas y el 192.168.1.11 es el nas'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',dicho,dicho))
                s.db.commit()
                agent.tool(s, 'device.identify', dict(target='192.168.1.10', name='el nas'), turn_id='u')
                with self.assertRaises(ValueError) as caught:
                    agent.tool(s, 'device.identify', dict(target='192.168.1.11', name='el nas'), turn_id='u')
                self.assertIn('Ya hay otro equipo guardado', str(caught.exception))

    def test_un_equipo_con_solo_acceso_sale_en_la_lista(self):
        # Poder conectarse a algo que no aparece al preguntar qué hay es lo que
        # confunde al modelo: la lista tiene que ser TODO lo alcanzable.
        with tempfile.TemporaryDirectory() as tmp:
            from hexos.agent.hosts import save
            agent = Agent(tmp, None)
            save(tmp, 'synology 2', 'helios', 'x', 22, host='casa.ddns.net')
            with agent.store() as s:
                r = agent.tool(s, 'device.list', {})
                fila = next(d for d in r['identified_devices'] if d['name'] == 'synology 2')
                self.assertTrue(fila['only_access'])
                self.assertTrue(fila['has_access'])
                self.assertEqual(fila['host'], 'casa.ddns.net')

    def test_lo_que_sale_en_la_lista_se_puede_quitar(self):
        with tempfile.TemporaryDirectory() as tmp:
            from hexos.agent.hosts import save, load
            agent = Agent(tmp, None)
            save(tmp, 'synology 2', 'helios', 'x', 22, host='casa.ddns.net')
            with agent.store() as s:
                borra = 'olvida synology 2'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',borra,borra))
                s.db.commit()
                r = agent.tool(s, 'device.forget', dict(target='synology 2'), turn_id='u')
                self.assertEqual(r['forgotten_access'], 'synology 2')
                self.assertEqual(agent.tool(s, 'device.list', {})['identified_devices'], [])
            self.assertEqual(load(tmp), {})

    def test_un_identificado_sin_acceso_lo_dice(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                with patch('hexos.agent.devices.snapshot', return_value=observation()):
                    agent.tool(s, 'device.refresh', {})
                dicho = 'el 192.168.1.10 es la impresora'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',dicho,dicho))
                s.db.commit()
                agent.tool(s, 'device.identify', dict(target='192.168.1.10', name='impresora'), turn_id='u')
                fila = agent.tool(s, 'device.list', {})['identified_devices'][0]
                self.assertNotIn('has_access', fila, 'identificado no es lo mismo que alcanzable')
                self.assertNotIn('only_access', fila)

    def test_dos_nombres_para_un_equipo_se_señalan_sin_tocarlos(self):
        # Dar acceso a uno y pedir lecturas por el otro parece falta de credenciales.
        with tempfile.TemporaryDirectory() as tmp:
            from hexos.agent.hosts import save
            agent = Agent(tmp, None)
            with agent.store() as s:
                dicho = 'registra servidorsrv1 en casa.ddns.net y synology en casa.ddns.net'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',dicho,dicho))
                s.db.commit()
                agent.tool(s, 'device.remote', dict(name='servidorsrv1', host='casa.ddns.net'), turn_id='u')
                agent.tool(s, 'device.remote', dict(name='synology', host='casa.ddns.net'), turn_id='u')
                r = agent.tool(s, 'device.list', {})
                self.assertEqual(len(r['duplicates']), 1)
                self.assertEqual(r['duplicates'][0]['devices'], ['servidorsrv1', 'synology'])
                self.assertIn('pregunta cuál conservar', r['duplicates'][0]['note'].casefold())
                # Señalar no es borrar: los dos siguen ahí hasta que la persona decida.
                self.assertEqual(r['total'], 2)

    def test_la_credencial_manda_al_decidir_si_son_el_mismo(self):
        # Uno puede tener dirección fija y el otro llevar la suya en la credencial.
        with tempfile.TemporaryDirectory() as tmp:
            from hexos.agent.hosts import save
            agent = Agent(tmp, None)
            with agent.store() as s:
                dicho = 'registra remoto1 en casa.ddns.net'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',dicho,dicho))
                s.db.commit()
                agent.tool(s, 'device.remote', dict(name='remoto1', host='casa.ddns.net'), turn_id='u')
                with patch('hexos.agent.devices.snapshot', return_value=observation()):
                    agent.tool(s, 'device.refresh', {})
                otro = 'el 192.168.1.10 es el nas de casa'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u2','now','user',otro,otro))
                s.db.commit()
                agent.tool(s, 'device.identify', dict(target='192.168.1.10', name='nas de casa'), turn_id='u2')
                # Sin credencial no se parecen: uno es una MAC y el otro un nombre.
                self.assertEqual(agent.tool(s, 'device.list', {})['duplicates'], [])
                # Con la credencial apuntando al mismo sitio, sí.
                save(tmp, 'nas de casa', 'helios', 'x', 22, host='casa.ddns.net')
                dup = agent.tool(s, 'device.list', {})['duplicates']
                self.assertEqual([d['devices'] for d in dup], [['nas de casa', 'remoto1']])

    def test_sin_repetidos_no_señala_nada(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                with patch('hexos.agent.devices.snapshot', return_value=observation()):
                    agent.tool(s, 'device.refresh', {})
                self.assertEqual(agent.tool(s, 'device.list', {})['duplicates'], [])

    def test_olvidar_un_equipo_remoto_lo_borra_entero_y_su_acceso(self):
        with tempfile.TemporaryDirectory() as tmp:
            from hexos.agent.hosts import save, load
            agent = Agent(tmp, None)
            with agent.store() as s:
                dicho = 'registra servidor 1 en 10.9.9.9'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',dicho,dicho))
                s.db.commit()
                agent.tool(s, 'device.remote', dict(name='servidor 1', host='10.9.9.9'), turn_id='u')
                save(tmp, 'servidor 1', 'helios', 'clave', 22, host='10.9.9.9')
                borra = 'olvida servidor 1, ya no lo uso'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u2','now','user',borra,borra))
                s.db.commit()
                r = agent.tool(s, 'device.forget', dict(target='servidor 1'), turn_id='u2')
                self.assertTrue(r['removed_record'])
                self.assertEqual(r['forgotten_access'], 'servidor 1')
                # Era el único registro: no queda ninguno.
                self.assertEqual(agent.tool(s, 'device.list', {})['total'], 0)
            self.assertEqual(load(tmp), {}, 'el acceso se va con el equipo')

    def test_olvidar_uno_de_esta_red_quita_el_nombre_pero_no_el_equipo(self):
        # No se puede des-ver un vecino: volverá en la próxima lectura, sin nombre.
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                with patch('hexos.agent.devices.snapshot', return_value=observation()):
                    agent.tool(s, 'device.refresh', {})
                dicho = 'el 192.168.1.10 es mi impresora'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',dicho,dicho))
                s.db.commit()
                agent.tool(s, 'device.identify', dict(target='192.168.1.10', name='impresora'), turn_id='u')
                borra = 'olvida la impresora'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u2','now','user',borra,borra))
                s.db.commit()
                r = agent.tool(s, 'device.forget', dict(target='impresora'), turn_id='u2')
                self.assertFalse(r['removed_record'])
                self.assertIn('sigue en la red', r['note'])
                registros = agent.tool(s, 'device.list', {})['devices']
                self.assertEqual(len(registros), 1)
                self.assertTrue(registros[0]['unidentified'])

    def test_con_fichas_duplicadas_dice_cuales_y_deja_borrar_por_id(self):
        # «Ambiguo» a secas dejaba sin salida: hay que poder quitar la que sobra.
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                with patch('hexos.agent.devices.snapshot', return_value=observation()):
                    agent.tool(s, 'device.refresh', {})
                dicho = 'el 192.168.1.10 es el synology 2'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',dicho,dicho))
                s.db.commit()
                agent.tool(s, 'device.identify', dict(target='192.168.1.10', name='synology 2'), turn_id='u')
                # Un duplicado como los que dejaba la versión anterior.
                import json as _json
                s.db.execute('INSERT INTO network_devices VALUES (?,?)',
                             ('remoto/synology 2', _json.dumps(dict(
                                 id='remoto/synology 2', mac=None, interface=None,
                                 pinned_host='casa.ddns.net', addresses=[], latest_addresses=[],
                                 identity=dict(name='synology 2', kind=None, source='user_statement',
                                               source_id='u', evidence=dicho, recorded_at='now')))))
                borra = 'borra synology 2'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u2','now','user',borra,borra))
                s.db.commit()
                with self.assertRaises(ValueError) as caught:
                    agent.tool(s, 'device.forget', dict(target='synology 2'), turn_id='u2')
                mensaje = str(caught.exception)
                self.assertIn('2 fichas', mensaje)
                self.assertIn('remoto/synology 2', mensaje)
                # Y por id sí se puede quitar la que sobra.
                porid = 'borra remoto/synology 2'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u3','now','user',porid,porid))
                s.db.commit()
                agent.tool(s, 'device.forget', dict(target='remoto/synology 2'), turn_id='u3')
                self.assertEqual(agent.tool(s, 'device.list', {})['total'], 1)

    def test_no_borra_lo_que_la_persona_no_nombro(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                dicho = 'registra servidor 1 en 10.9.9.9'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',dicho,dicho))
                s.db.commit()
                agent.tool(s, 'device.remote', dict(name='servidor 1', host='10.9.9.9'), turn_id='u')
                otro = 'limpia lo que sobre'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u2','now','user',otro,otro))
                s.db.commit()
                with self.assertRaises(ValueError) as caught:
                    agent.tool(s, 'device.forget', dict(target='servidor 1'), turn_id='u2')
                self.assertIn('no aparece en el mensaje', str(caught.exception))
                # Y sin turno tampoco: borrar no se deduce.
                with self.assertRaises(ValueError):
                    agent.tool(s, 'device.forget', dict(target='servidor 1'))
                self.assertEqual(agent.tool(s, 'device.list', {})['total'], 1)

    def test_mirar_la_red_deja_registrado_lo_visto(self):
        # Enseñar vecinos sin guardarlos dejaba ver equipos que luego no se podían
        # nombrar, y los de otra red seguían figurando como recién vistos.
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                vieja = observation()
                vieja['neighbors'] = [dict(ip='192.168.1.1', mac='f8:98:ef:93:cc:11', interface='eth0',
                                           state=['REACHABLE'], recently_reachable=True)]
                with patch('hexos.agent.devices.snapshot', return_value=vieja):
                    agent.tool(s, 'device.refresh', {})
                # Otra casa: mismo 192.168.1.1, otro router.
                nueva = observation()
                nueva['neighbors'] = [dict(ip='192.168.1.1', mac='d4:86:60:f4:34:6e', interface='eth0',
                                           state=['REACHABLE'], recently_reachable=True),
                                      dict(ip='192.168.1.129', mac='fe:b1:96:7c:78:9f', interface='eth0',
                                           state=['STALE'], recently_reachable=False)]
                with patch('hexos.agent.devices.snapshot', return_value=nueva), \
                     patch('hexos.agent.chat.network_snapshot', return_value=nueva):
                    agent.tool(s, 'network.local', {})
                dicho = 'la que termina en 129 es el iphone'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',dicho,dicho))
                s.db.commit()
                # Lo que acaba de verse ya se puede nombrar, sin refrescar aparte.
                agent.tool(s, 'device.identify', dict(target='129', name='iphone'), turn_id='u')
                # Y el router de la otra red deja de figurar como recién visto, así
                # que un sufijo no puede casar con el fantasma.
                for d in agent.tool(s, 'device.list', {})['devices']:
                    if d['mac'] == 'f8:98:ef:93:cc:11':
                        self.assertNotIn('seen_now', d)
                nombres = {d['name'] for d in agent.tool(s, 'device.list', {})['devices']
                           if d.get('name')}
                self.assertEqual(nombres, {'iphone'})

    def test_se_puede_nombrar_por_los_dos_ultimos_octetos(self):
        # «la que termina en 1.129» es como se habla de una IP; con solo el último
        # octeto la frase de la persona no validaba y no se registraba nada.
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                data = observation()
                data['neighbors'] = [dict(ip='192.168.1.' + str(n), mac='aa:bb:cc:dd:ee:%02x' % n,
                                          interface='eth0', state=['REACHABLE'], recently_reachable=True)
                                     for n in (1, 129)]
                with patch('hexos.agent.devices.snapshot', return_value=data):
                    agent.tool(s, 'device.refresh', {})
                dicho = ('registra la que termina en 1.1 router, '
                         'la que termina en 1.129 es el iphone 16 pro')
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',dicho,dicho))
                s.db.commit()
                agent.tool(s, 'device.identify', dict(target='1.1', name='router'), turn_id='u')
                agent.tool(s, 'device.identify', dict(target='1.129', name='iphone 16 pro'), turn_id='u')
                nombres = {d['name'] for d in agent.tool(s, 'device.list', {})['devices']
                           if d.get('name')}
                self.assertEqual(nombres, {'router', 'iphone 16 pro'})

    def test_unos_octetos_ambiguos_no_nombran_nada(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                data = observation()
                # Mismos dos últimos octetos en redes distintas: no distingue.
                data['neighbors'] = [dict(ip=red + '.1.50', mac='aa:bb:cc:dd:ee:%02x' % n,
                                          interface='eth0', state=['REACHABLE'], recently_reachable=True)
                                     for n, red in enumerate(('192.168', '10.0'))]
                with patch('hexos.agent.devices.snapshot', return_value=data):
                    agent.tool(s, 'device.refresh', {})
                dicho = 'la que termina en 1.50 es el router'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',dicho,dicho))
                s.db.commit()
                with self.assertRaises(ValueError):
                    agent.tool(s, 'device.identify', dict(target='1.50', name='router'), turn_id='u')

    def test_identity_persists_without_following_reassigned_ip(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, None)
            with agent.store() as s:
                with patch('hexos.agent.devices.snapshot', return_value=observation()):
                    dispatch(s, 'device.refresh', {})
                quote = '192.168.1.10 es mi NAS Faro'
                s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('u','now','user',quote,quote))
                s.db.commit()
                args = dict(target='192.168.1.10', name='NAS Faro', kind='NAS', source_id='u', evidence=quote)
                dispatch(s, 'device.identify', args)
                with patch('hexos.agent.devices.snapshot', return_value=observation(ip='192.168.1.11')):
                    dispatch(s, 'device.refresh', {})
                self.assertEqual(dispatch(s,'device.list',{})['devices'][0]['name'], 'NAS Faro')
                with patch('hexos.agent.devices.snapshot', return_value=observation(mac='11:22:33:44:55:66')):
                    dispatch(s, 'device.refresh', {})
                devices = dispatch(s, 'device.list', {})['devices']
                self.assertEqual(len(devices), 2)
                self.assertTrue(next(d for d in devices if d.get('seen_now'))['unidentified'])
            with Agent(tmp, None).store() as s:
                self.assertEqual(dispatch(s, 'device.list', {'query':'NAS Faro'})['total'], 1)

    def test_rejects_invented_or_assistant_evidence_and_old_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            with Agent(tmp, None).store() as s:
                with patch('hexos.agent.devices.snapshot', return_value=observation()):
                    dispatch(s, 'device.refresh', {})
                for uid, role, quote in [('a','assistant','192.168.1.10 es router'),
                                         ('u','user','192.168.1.10 es NAS'),
                                         ('v','user','192.168.1.10 es Raspberry')]:
                    s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', (uid,'now',role,quote,quote))
                args=dict(target='192.168.1.10', name='router', evidence='192.168.1.10 es router')
                with self.assertRaises(ValueError): dispatch(s,'device.identify',args)
                args['evidence']='192.168.1.10 es NAS'; args['name']='router'
                with self.assertRaises(ValueError): dispatch(s,'device.identify',args)
                dispatch(s,'device.identify',dict(target='192.168.1.10',name='Raspberry',source_id='v',evidence='192.168.1.10 es Raspberry'))
                args['name']='NAS'
                with self.assertRaises(ValueError): dispatch(s,'device.identify',args)
