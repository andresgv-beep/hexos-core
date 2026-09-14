import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from hexos.agent.hosts import credentials, forget, load, resolve, save, store_path


def inventory(workspace, devices):
    db = sqlite3.connect(str(Path(workspace) / 'work.sqlite'))
    db.execute('CREATE TABLE network_devices (id TEXT PRIMARY KEY, body TEXT)')
    for device in devices:
        db.execute('INSERT INTO network_devices VALUES (?,?)', (device['id'], json.dumps(device)))
    db.commit()
    db.close()


def device(id, name, ip, state=('REACHABLE',), at='2026-09-12T14:27:13+00:00', mac='aa:bb:cc:dd:ee:ff'):
    address = dict(ip=ip, state=list(state), observed_at=at)
    return dict(id=id, mac=mac, interface='wlp0', addresses=[address], latest_addresses=[address],
                identity=dict(name=name, kind=None, source='user_statement') if name else None)


class HostsTest(unittest.TestCase):
    def test_credentials_round_trip_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            save(tmp, 'Synology', 'helios', 'secreta', 22)
            self.assertEqual(os.stat(store_path(tmp)).st_mode & 0o777, 0o600)
            # El nombre se normaliza para que synology y Synology sean el mismo equipo.
            self.assertEqual(credentials(tmp, 'synology')['user'], 'helios')
            self.assertEqual(credentials(tmp, 'SYNOLOGY')['password'], 'secreta')
            self.assertIsNone(credentials(tmp, 'otro'))

    def test_revoking_one_access_leaves_the_others_and_keeps_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            save(tmp, 'synology', 'helios', 'a')
            save(tmp, 'nimos nas', 'root', 'b')
            self.assertEqual(forget(tmp, 'Synology')['remaining'], ['nimos nas'])
            self.assertIsNone(credentials(tmp, 'synology'))
            self.assertEqual(credentials(tmp, 'nimos nas')['user'], 'root')
            self.assertEqual(os.stat(store_path(tmp)).st_mode & 0o777, 0o600)

    def test_revoking_the_last_access_removes_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            save(tmp, 'synology', 'helios', 'a')
            forget(tmp, 'synology')
            self.assertFalse(store_path(tmp).exists())
            with self.assertRaises(ValueError) as caught:
                forget(tmp, 'synology')
            self.assertIn('ninguno', str(caught.exception))

    def test_readable_by_others_is_refused_instead_of_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            save(tmp, 'nas', 'u', 'p')
            os.chmod(store_path(tmp), 0o644)
            with self.assertRaises(ValueError) as caught:
                load(tmp)
            self.assertIn('chmod 600', str(caught.exception))

    def test_rejects_names_that_could_reach_the_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, user, port in [('nas; rm -rf /', 'u', 22), ('nas', 'u$(id)', 22),
                                     ('nas', 'u', 0), ('nas', 'u', 70000), ('', 'u', 22)]:
                with self.assertRaises(ValueError):
                    save(tmp, name, user, 'p', port)

    def test_resolves_saved_name_to_its_current_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory(tmp, [device('a', 'synology', '192.168.1.243', mac='b4:2e:99:47:6d:15'),
                            device('b', 'nimos nas', '192.168.1.131'),
                            device('c', None, '192.168.1.249')])
            located = resolve(tmp, 'Synology')
            self.assertEqual(located['host'], '192.168.1.243')
            self.assertEqual(located['mac'], 'b4:2e:99:47:6d:15')
            self.assertTrue(located['reachable'])

    def test_unknown_name_lists_what_is_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory(tmp, [device('a', 'synology', '192.168.1.243')])
            with self.assertRaises(ValueError) as caught:
                resolve(tmp, 'faro')
            self.assertIn('synology', str(caught.exception))

    def test_prefers_a_reachable_address_over_a_stale_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            stale = dict(ip='192.168.1.9', state=['STALE'], observed_at='2026-09-12T15:00:00+00:00')
            live = dict(ip='192.168.1.243', state=['REACHABLE'], observed_at='2026-09-12T14:00:00+00:00')
            entry = device('a', 'synology', '0.0.0.0')
            entry['latest_addresses'] = [stale, live]
            inventory(tmp, [entry])
            self.assertEqual(resolve(tmp, 'synology')['host'], '192.168.1.243')

    def test_ipv6_only_device_says_so_instead_of_guessing(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = device('a', 'synology', '0.0.0.0')
            entry['latest_addresses'] = [dict(ip='fe80::1', state=['REACHABLE'], observed_at='2026-09-12T14:00:00+00:00')]
            inventory(tmp, [entry])
            with self.assertRaises(ValueError) as caught:
                resolve(tmp, 'synology')
            self.assertIn('IPv4', str(caught.exception))

    def test_duplicate_names_refuse_to_pick_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory(tmp, [device('a', 'nas', '192.168.1.2'), device('b', 'nas', '192.168.1.3')])
            with self.assertRaises(ValueError) as caught:
                resolve(tmp, 'nas')
            self.assertIn('no distingue', str(caught.exception))


class ActualizarSinContrasenaTest(unittest.TestCase):
    """Corregir un puerto no puede exigir volver a escribir la credencial entera."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-hosts-set-')
        save(self.tmp.name, 'synology 1', 'helios', 'secreta', 22, host='casa.ddns.net')

    def tearDown(self):
        self.tmp.cleanup()

    def test_cambia_el_puerto_y_conserva_la_contrasena(self):
        from hexos.agent.hosts import update, credentials
        resultado = update(self.tmp.name, 'synology 1', port=30)
        self.assertEqual((resultado['port'], resultado['host']), (30, 'casa.ddns.net'))
        guardado = credentials(self.tmp.name, 'synology 1')
        self.assertEqual(guardado['password'], 'secreta')
        self.assertEqual(guardado['user'], 'helios')

    def test_cambia_la_direccion_y_la_valida(self):
        from hexos.agent.hosts import update, credentials
        update(self.tmp.name, 'synology 1', host='100.83.4.11')
        self.assertEqual(credentials(self.tmp.name, 'synology 1')['host'], '100.83.4.11')
        with self.assertRaises(ValueError):
            update(self.tmp.name, 'synology 1', host='-oProxyCommand=id')
        with self.assertRaises(ValueError):
            update(self.tmp.name, 'synology 1', port=0)

    def test_no_inventa_accesos_ni_cambia_nada_sin_pedirlo(self):
        from hexos.agent.hosts import update, load
        with self.assertRaises(ValueError):
            update(self.tmp.name, 'no existe', port=30)
        with self.assertRaises(ValueError):
            update(self.tmp.name, 'synology 1')
        self.assertEqual(load(self.tmp.name)['synology 1']['port'], 22)

    def test_el_archivo_sigue_siendo_privado(self):
        from hexos.agent.hosts import update, store_path
        update(self.tmp.name, 'synology 1', port=30)
        self.assertEqual(store_path(self.tmp.name).stat().st_mode & 0o777, 0o600)


class ElegirEquipoTest(unittest.TestCase):
    """Con dos NAS guardados, adivinar cuál es mandar la lectura al que no es."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-elegir-')

    def tearDown(self):
        self.tmp.cleanup()

    def test_con_uno_solo_no_hace_falta_nombrarlo(self):
        from hexos.agent.hosts import only_device
        save(self.tmp.name, 'synology', 'helios', 'x', 22)
        self.assertEqual(only_device(self.tmp.name), 'synology')

    def test_con_varios_se_niega_y_los_nombra(self):
        from hexos.agent.hosts import only_device
        save(self.tmp.name, 'synology', 'helios', 'x', 22)
        save(self.tmp.name, 'synology 1', 'helios', 'x', 30, host='casa.ddns.net')
        with self.assertRaises(ValueError) as caught:
            only_device(self.tmp.name)
        self.assertIn('synology 1', str(caught.exception))
        self.assertIn('varios equipos', str(caught.exception))

    def test_sin_ninguno_conserva_el_camino_de_pedir_acceso(self):
        from hexos.agent.hosts import only_device
        self.assertEqual(only_device(self.tmp.name), 'synology')


class DireccionFijaTest(unittest.TestCase):
    """Un equipo fuera de su red no aparece en la tabla ARP: hace falta fijarlo."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-hosts-fija-')

    def tearDown(self):
        self.tmp.cleanup()

    def test_la_direccion_fijada_manda_sobre_el_inventario(self):
        save(self.tmp.name, 'synology', 'helios', 'x', 22, host='100.83.4.11')
        located = resolve(self.tmp.name, 'synology')
        self.assertEqual(located['host'], '100.83.4.11')
        self.assertTrue(located['pinned'])
        # Y no necesita inventario ninguno: sin work.sqlite seguiría resolviendo.
        self.assertFalse((Path(self.tmp.name) / 'work.sqlite').exists())

    def test_admite_nombre_dns_ademas_de_ip(self):
        # La dirección DDNS del NAS es un nombre, no una IP.
        save(self.tmp.name, 'synology', 'helios', 'x', 22, host='micasa.synology.me')
        self.assertEqual(resolve(self.tmp.name, 'synology')['host'], 'micasa.synology.me')

    def test_rechaza_lo_que_no_es_una_direccion(self):
        from hexos.agent.hosts import address
        # Un guion inicial convertiría la dirección en una opción de ssh.
        for malo in ('-oProxyCommand=id', 'a b', '', ' ', 'x' * 254, 'uno;dos', '10.0.0.1 -v'):
            with self.assertRaises(ValueError, msg=malo):
                address(malo)
        # Y lo que sí lo es, pasa y queda normalizado.
        self.assertEqual(address(' 192.168.1.243 '), '192.168.1.243')
        self.assertEqual(address('MiCasa.Synology.ME'), 'micasa.synology.me')

    def test_sin_direccion_fijada_se_sigue_usando_el_inventario(self):
        save(self.tmp.name, 'synology', 'helios', 'x', 22)
        with self.assertRaises(ValueError) as caught:
            resolve(self.tmp.name, 'synology')
        self.assertIn('inventario', str(caught.exception))


class RutasAlternativasTest(unittest.TestCase):
    """Un equipo puede tener dos caminos; hay que devolver los dos y en orden."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-rutas-')

    def tearDown(self):
        self.tmp.cleanup()

    def inventario(self, **campos):
        import sqlite3
        base = dict(id='eth0/aa:bb', mac='aa:bb', interface='eth0', identity=dict(name='synology'),
                    latest_addresses=[], addresses=[], in_latest_snapshot=False)
        base.update(campos)
        db = sqlite3.connect(Path(self.tmp.name) / 'work.sqlite')
        db.execute('CREATE TABLE IF NOT EXISTS network_devices (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
        db.execute('INSERT OR REPLACE INTO network_devices VALUES (?,?)', (base['id'], json.dumps(base)))
        db.commit(); db.close()

    def test_si_se_le_ve_en_la_red_manda_su_ip_y_la_fija_queda_de_reserva(self):
        self.inventario(in_latest_snapshot=True, pinned_host='casa.ddns.net', pinned_port=30,
                        latest_addresses=[dict(ip='192.168.1.243', state=['REACHABLE'], observed_at='2026-09-14')])
        r = resolve(self.tmp.name, 'synology')
        self.assertEqual(r['host'], '192.168.1.243')
        self.assertEqual([a['host'] for a in r['alternatives']], ['casa.ddns.net'])
        self.assertEqual(r['alternatives'][0]['port'], 30)

    def test_si_no_se_le_ve_manda_la_fija_y_la_ip_queda_de_reserva(self):
        # Otra casa: la IP local de la última vez ya no vale, pero se intenta después.
        self.inventario(in_latest_snapshot=False, pinned_host='casa.ddns.net', pinned_port=30,
                        latest_addresses=[dict(ip='192.168.1.243', state=['STALE'], observed_at='2026-09-13')])
        r = resolve(self.tmp.name, 'synology')
        self.assertEqual((r['host'], r['port']), ('casa.ddns.net', 30))
        self.assertEqual([a['host'] for a in r['alternatives']], ['192.168.1.243'])

    def test_sin_direccion_fija_solo_hay_un_camino(self):
        self.inventario(in_latest_snapshot=True,
                        latest_addresses=[dict(ip='192.168.1.243', state=['REACHABLE'], observed_at='2026-09-14')])
        r = resolve(self.tmp.name, 'synology')
        self.assertEqual(r['host'], '192.168.1.243')
        self.assertEqual(r['alternatives'], [])

    def test_sin_ninguna_direccion_lo_dice_en_vez_de_inventarse_una(self):
        self.inventario(latest_addresses=[dict(ip='fe80::1', state=['STALE'], observed_at='2026-09-14')])
        with self.assertRaises(ValueError) as caught:
            resolve(self.tmp.name, 'synology')
        self.assertIn('IPv4', str(caught.exception))
        self.assertIn('device_remote', str(caught.exception))


class EquipoNombradoTest(unittest.TestCase):
    """Si la persona nombró el equipo, no hay que preguntárselo otra vez."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-nombrado-')
        class Runtime:
            def call(self, request): pass
            def generate(self, messages): return {'reply': '', 'work': None}
        from hexos.agent.chat import Agent
        self.agent = Agent(self.tmp.name, Runtime())
        for nombre in ('synology', 'synology 2', 'servidorsrv1'):
            save(self.tmp.name, nombre, 'helios', 'x', 22)

    def tearDown(self):
        self.tmp.cleanup()

    def nombrado(self, texto):
        from uuid import uuid4
        from hexos.agent.work import now
        # Un id por llamada: el mismo test puede probar varias frases.
        uid = uuid4().hex
        with self.agent.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             (uid, now(), 'user', texto, texto))
            store.db.commit()
            return self.agent.device_in_message(store, uid)

    def test_lo_toma_de_sus_palabras(self):
        self.assertEqual(self.nombrado('revisa la salud de los contenedores del synology'), 'synology')

    def test_el_nombre_mas_largo_gana_sobre_el_que_lo_contiene(self):
        # 'synology' está dentro de 'synology 2'; elegir el corto sería otro equipo.
        self.assertEqual(self.nombrado('mira el synology 2'), 'synology 2')

    def test_con_dos_nombrados_no_elige(self):
        self.assertIsNone(self.nombrado('compara synology y servidorsrv1'))

    def test_nombrar_los_dos_synology_no_elige_uno_callado(self):
        # El caso peligroso: 'synology' está dentro de 'synology 2', y descartarlo
        # por el nombre en vez de por la posición hacía que eligiera uno solo.
        self.assertIsNone(self.nombrado('compara synology y synology 2'))
        self.assertIsNone(self.nombrado('el synology 2 y luego el synology'))

    def test_el_mismo_nombre_repetido_sigue_siendo_uno(self):
        self.assertEqual(self.nombrado('synology, sí, el synology'), 'synology')

    def test_sin_ninguno_no_inventa(self):
        self.assertIsNone(self.nombrado('mira los contenedores'))

    def test_sin_turno_no_hay_de_dónde_leerlo(self):
        with self.agent.store() as store:
            self.assertIsNone(self.agent.device_in_message(store, None))


if __name__ == '__main__':
    unittest.main()
