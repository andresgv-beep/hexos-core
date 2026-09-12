import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from hexos.agent import hosts
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


if __name__ == '__main__':
    unittest.main()
