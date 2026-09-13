import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from hexos.agent import hosts
from hexos.agent.work import now
from hexos.agent.nas_session import read


def inventory(workspace, name='synology', ip='192.168.1.243'):
    db = sqlite3.connect(str(Path(workspace) / 'work.sqlite'))
    db.execute('CREATE TABLE IF NOT EXISTS network_devices (id TEXT PRIMARY KEY, body TEXT)')
    address = dict(ip=ip, state=['REACHABLE'], observed_at='2026-09-12T14:00:00+00:00')
    body = dict(id='a', mac='b4:2e:99:47:6d:15', interface='wlp0', addresses=[address],
                latest_addresses=[address],
                identity=dict(name=name, kind=None, source='user_statement'))
    db.execute('INSERT OR REPLACE INTO network_devices VALUES (?,?)', ('a', json.dumps(body)))
    db.commit()
    db.close()


class CredentialRequestTest(unittest.TestCase):
    def test_missing_access_asks_through_the_interface_with_the_resolved_machine(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory(tmp)
            with self.assertRaises(hosts.AccessNeeded) as caught:
                read(tmp, 'diagnosis')
            needed = caught.exception
            self.assertEqual(needed.device, 'synology')
            # La ventana debe poder enseñar a qué máquina se da el acceso.
            self.assertEqual(needed.located['host'], '192.168.1.243')
            self.assertEqual(needed.located['mac'], 'b4:2e:99:47:6d:15')
            self.assertIn('no pidas la contraseña por el chat', str(needed).lower())
            self.assertIn('no significa que el equipo esté sano', str(needed))

    def test_unknown_device_still_asks_instead_of_failing_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory(tmp)
            with self.assertRaises(hosts.AccessNeeded) as caught:
                read(tmp, 'diagnosis', device='otro')
            self.assertIsNone(caught.exception.located)

    def test_saving_access_never_returns_or_stores_the_password_in_the_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory(tmp)
            hosts.save(tmp, 'synology', 'helios', 'secreta')
            self.assertEqual(os.stat(hosts.store_path(tmp)).st_mode & 0o777, 0o600)
            # Tras guardarla, la lectura ya no pide acceso.
            with patch('hexos.agent.nas_session.execute', return_value=dict(output='', exit_code=0)) as run:
                read(tmp, 'system')
            run.assert_called_once()

    def test_container_action_also_asks_for_access_before_touching_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory(tmp)
            with patch('hexos.agent.nas_session.execute') as run:
                with self.assertRaises(hosts.AccessNeeded):
                    read(tmp, 'container', container='plex', action='restart')
            run.assert_not_called()

    def test_saving_tells_the_model_to_retry_instead_of_leaving_it_stuck(self):
        from hexos.agent.chat import Agent

        class FakeRuntime:
            def call(self, request): pass
            def generate(self, messages): return {'reply': '', 'work': None}

        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, FakeRuntime())
            inventory(tmp)
            agent.credential_request = dict(device='synology', host='192.168.1.243')
            result = agent.save_access(dict(device='synology', user='helios', password='secreta'))
            self.assertTrue(result['saved'])
            self.assertIsNone(agent.credential_request)
            # La respuesta al navegador no devuelve la contraseña.
            self.assertNotIn('secreta', json.dumps(result, ensure_ascii=False))
            with agent.store() as store:
                rows = [dict(r) for r in store.db.execute('SELECT role, text FROM conversation')]
            note = [r for r in rows if 'acceso a synology' in r['text']]
            self.assertEqual(len(note), 1, 'el modelo debe ver que el acceso ya está guardado')
            self.assertIn('vuelve a llamar a la herramienta', note[0]['text'])
            self.assertNotIn('secreta', note[0]['text'])

    def test_interface_and_origin_rules_are_declared_in_the_server(self):
        source = Path('hexos/agent/chat.py').read_text()
        # Sin comprobación de origen, una página abierta en otra pestaña podría
        # provocar la ventana que pide la credencial.
        self.assertIn("origin not in allowed_origins", source)
        self.assertIn("'/api/credentials'", source)
        self.assertIn('allowed_origins = ', source)
        page = Path('hexos/agent/chat.html').read_text()
        self.assertIn('/api/credentials', page)
        self.assertIn('accesstarget', page)
        # Tras dar el acceso, la interfaz retoma la petición sin que haya que repetirla.
        self.assertIn('lastRequest', page)
        self.assertIn('if(lastRequest)await send(lastRequest)', page)

    def test_saved_conversation_is_not_readable_by_other_accounts(self):
        from hexos.agent.work import WorkStore
        with tempfile.TemporaryDirectory() as tmp:
            store = WorkStore(tmp)
            store.db.close()
            self.assertEqual(os.stat(Path(tmp) / 'work.sqlite').st_mode & 0o077, 0)


class AccesoRechazadoTest(unittest.TestCase):
    """Una credencial rechazada no es una lectura fallida: falta el acceso."""

    def test_el_mensaje_distingue_rechazo_de_ausencia(self):
        from hexos.agent.hosts import AccessNeeded
        falta = AccessNeeded('synology 1')
        rechazo = AccessNeeded('synology 1', dict(host='x'), reason='rejected')
        self.assertIsNone(falta.reason)
        self.assertEqual(rechazo.reason, 'rejected')
        self.assertIn('no tiene todavía el acceso', str(falta))
        self.assertIn('rechazó el acceso guardado', str(rechazo))
        # El puerto es la causa más fácil de pasar por alto y la más fácil de arreglar.
        self.assertIn('puerto', str(rechazo))

    def test_permission_denied_pide_el_acceso_otra_vez(self):
        import pexpect
        from unittest.mock import patch
        from hexos.agent import hosts, nas_session

        class SshFalso:
            """Contesta el rechazo de OpenSSH y cierra, como el de verdad."""
            exitstatus = 255
            def __init__(self, salida): self.before = salida
            def expect(self, patrones, timeout=None): return 2   # EOF
            def waitnoecho(self, timeout=None): return True
            def sendline(self, texto): pass
            def close(self, force=False): pass

        acceso = dict(user='helios', password='x', port=22)
        ubicado = dict(name='synology 1', host='servidorsrv1.ddns.net', mac=None,
                       observed_at=None, reachable=None, pinned=True)
        rechazos = ['helios@host: Permission denied (publickey,password).',
                    'Authentication failed.',
                    'Received disconnect: Too many authentication failures']
        for salida in rechazos:
            with patch.object(nas_session.hosts, 'resolve', return_value=ubicado), \
                 patch.object(nas_session.hosts, 'credentials', return_value=acceso), \
                 patch.object(pexpect, 'spawn', return_value=SshFalso(salida)):
                with self.assertRaises(hosts.AccessNeeded, msg=salida) as caught:
                    nas_session.execute('/tmp', 'synology 1', 'system')
            self.assertEqual(caught.exception.reason, 'rejected')
        # Una salida normal no debe confundirse con un rechazo.
        with patch.object(nas_session.hosts, 'resolve', return_value=ubicado), \
             patch.object(nas_session.hosts, 'credentials', return_value=acceso), \
             patch.object(pexpect, 'spawn', return_value=SshFalso('md0 : active raid1 sda1[0]')):
            resultado = nas_session.execute('/tmp', 'synology 1', 'system')
        self.assertIn('md0', resultado['output'])


class RetomarTrasGuardarTest(unittest.TestCase):
    """Rellenar la ventana no debería obligar a repetir la petición."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-retomar-')

    def tearDown(self):
        self.tmp.cleanup()

    def test_devuelve_lo_que_se_estaba_pidiendo(self):
        from unittest.mock import patch
        from hexos.agent import hosts
        from hexos.agent.chat import Agent

        class Runtime:
            def call(self, request): pass
            def generate(self, messages): return {'reply': '', 'work': None}

        agente = Agent(self.tmp.name, Runtime())
        peticion = 'revisa el estado de synology 1'
        with agente.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             ('u1', now(), 'user', peticion, peticion))
            store.db.commit()
            with patch('hexos.agent.chat.nas_read',
                       side_effect=hosts.AccessNeeded('synology 1', dict(host='casa.ddns.net'))):
                agente.tool(store, 'nas.read', {'section': 'diagnosis'}, turn_id='u1')
        self.assertEqual(agente.credential_request['pending_request'], peticion)
        guardado = agente.save_access(dict(device='synology 1', user='helios',
                                           password='x', host='casa.ddns.net', port=30))
        self.assertEqual(guardado['resume'], peticion)
        # Y no se queda pegado: el siguiente guardado no reenvía nada.
        self.assertIsNone(agente.credential_request)
        self.assertIsNone(agente.save_access(dict(device='synology 1', user='helios',
                                                  password='x', host='casa.ddns.net'))['resume'])


class DescartarPeticionTest(unittest.TestCase):
    """«Ahora no» tiene que valer también en el servidor."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-descartar-')
        class Runtime:
            def call(self, request): pass
            def generate(self, messages): return {'reply': '', 'work': None}
        from hexos.agent.chat import Agent
        self.agente = Agent(self.tmp.name, Runtime())
        self.agente.credential_request = dict(device='synology 1', requested_at=now())

    def tearDown(self):
        self.tmp.cleanup()

    def test_retira_la_peticion_sin_guardar_credencial(self):
        from hexos.agent.hosts import load
        resultado = self.agente.save_access(dict(device='synology 1', dismiss=True))
        self.assertFalse(resultado['saved'])
        self.assertIsNone(self.agente.credential_request)
        self.assertEqual(load(self.tmp.name), {}, 'descartar no puede escribir nada')

    def test_no_retira_la_de_otro_equipo(self):
        with self.assertRaises(ValueError):
            self.agente.save_access(dict(device='otro', dismiss=True))
        self.assertIsNotNone(self.agente.credential_request)

    def test_descartar_no_admite_colar_una_contrasena(self):
        with self.assertRaises(ValueError):
            self.agente.save_access(dict(device='synology 1', dismiss=True, password='x'))
        self.assertIsNotNone(self.agente.credential_request)


if __name__ == '__main__':
    unittest.main()
