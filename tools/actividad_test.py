"""Lo hecho en la conversación actual, para el lateral del Agente."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hexos.agent import actividad
from hexos.agent.chat import Agent


class Runtime:
    def call(self, request): pass
    def generate(self, messages): return {'reply': 'Hecho.', 'work': None}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-actividad-')
        self.casa = Path(self.tmp.name).resolve()
        self.parches = [mock.patch.object(Path, 'home', return_value=self.casa),
                        mock.patch.dict(os.environ, {'HEXOS_PROJECTS_HOME': str(self.casa / 'proyectos')})]
        for parche in self.parches:
            parche.start()
        self.agente = Agent(self.casa / 'hexos', Runtime())
        self.agente.set_window('agente')

    def tearDown(self):
        for parche in self.parches:
            parche.stop()
        self.tmp.cleanup()

    def llamar(self, herramienta, argumentos, minuto, **extra):
        """Un turno con una llamada ya registrada, como la deja el despachador."""
        self.agente.chat('petición %d' % minuto)
        with self.agente.store() as store:
            turno = store.db.execute("SELECT id FROM esta_ventana WHERE role='user' ORDER BY rowid DESC").fetchone()[0]
            cuerpo = dict(dict(tool=herramienta, arguments=argumentos, seconds=0.25, failed=False, result=dict(ok=True)), **extra)
            store.db.execute('INSERT INTO tool_events(turn_id,ts,body) VALUES (?,?,?)',
                             (turno, '2026-11-13T16:%02d:00+00:00' % minuto, json.dumps(cuerpo)))
            store.db.commit()
            return store.db.execute('SELECT MAX(seq) FROM tool_events').fetchone()[0]

    def reciente(self, **efectos):
        with self.agente.store() as store:
            return actividad.reciente(store, efectos)


class ResumenTest(unittest.TestCase):
    def test_dice_lo_que_se_pidio_no_el_json(self):
        self.assertEqual(actividad.resumen('terminal.read', dict(command='dpkg -l', filter='gimp')), 'dpkg -l · filter gimp')
        self.assertEqual(actividad.resumen('terminal.read', dict(command='ls', path='/home/x/p')), 'ls /home/x/p')
        self.assertEqual(actividad.resumen('system.package_plan', dict(action='install', package='sl', manager='apt')), 'install sl apt')
        self.assertEqual(actividad.resumen('web.search', dict(query='home assistant', limit=5)), 'home assistant')
        self.assertEqual(actividad.resumen('nas.find', dict(device='synology 1', query='avatar')), 'avatar synology 1')
        self.assertEqual(actividad.resumen('system.status', {}), '')

    def test_lo_desconocido_cae_en_los_argumentos_y_lo_largo_se_corta(self):
        self.assertEqual(actividad.resumen('otra.cosa', dict(a=1)), '{"a": 1}')
        self.assertLessEqual(len(actividad.resumen('web.read', dict(url='https://x.es/' + 'a' * 500))), actividad.MAX_LINEA)


class RecienteTest(Base):
    def test_lo_mas_nuevo_primero_con_su_duracion_y_si_fallo(self):
        self.llamar('terminal.read', dict(command='ls'), 1)
        self.llamar('web.search', dict(query='cuda'), 2, failed=True)
        llamadas = self.reciente()['tools']
        self.assertEqual([(l['tool'], l['summary'], l['failed'], l['seconds']) for l in llamadas],
                         [('web.search', 'cuda', True, 0.25), ('terminal.read', 'ls', False, 0.25)])

    def test_cambios_son_lo_que_tuvo_efecto_y_lo_decidido_en_la_tarjeta(self):
        self.llamar('terminal.read', dict(command='ls'), 1)
        self.llamar('note.save', dict(title='kernel'), 2)
        self.llamar('note.save', dict(title='rota'), 3, failed=True)
        with self.agente.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             ('nota', '2026-11-13T16:30:00+00:00', 'user',
                              '[La persona aprobó en la interfaz: Instalar sl con apt. HexOS lo ejecutó: hecho y comprobado.]', ''))
            store.db.commit()
        cambios = self.reciente(**{'note.save': 'write'})['changes']
        self.assertEqual([(c['kind'], c['text'][:28]) for c in cambios],
                         [('decision', 'La persona aprobó en la inte'), ('tool', 'note.save kernel')])

    def test_cada_proyecto_ve_solo_su_actividad(self):
        self.llamar('terminal.read', dict(command='ls general'), 1)
        self.agente.create_project('uno')
        self.assertEqual(self.reciente()['tools'], [])
        del_uno = self.llamar('terminal.read', dict(command='ls uno'), 2)
        self.agente.create_project('dos')
        self.assertEqual(self.reciente()['tools'], [])
        with self.agente.store() as store, self.assertRaisesRegex(ValueError, 'esta conversación'):
            actividad.detalle(store, del_uno)                      # ni pidiéndola por su número
        self.agente.set_project('uno')
        self.assertEqual([l['summary'] for l in self.reciente()['tools']], ['ls uno'])


class DetalleTest(Base):
    def test_trae_argumentos_y_la_salida_con_tope(self):
        seq = self.llamar('terminal.read', dict(command='ls'), 1)
        with self.agente.store() as store:
            store.db.execute('UPDATE tool_events SET body=? WHERE seq=?', (json.dumps(dict(
                tool='terminal.read', arguments=dict(command='ls'), seconds=0.1,
                result=dict(command='ls', exit_code=0, output='a\n' * 5000))), seq))
            store.db.commit()
            d = actividad.detalle(store, seq)
        self.assertEqual((d['tool'], d['arguments'], d['truncated']), ('terminal.read', dict(command='ls'), True))
        self.assertTrue(d['output'].startswith('a\na\n'))
        self.assertEqual(len(d['output']), actividad.MAX_SALIDA)

    def test_sin_salida_de_texto_ensena_el_resultado(self):
        seq = self.llamar('system.status', {}, 1)
        with self.agente.store() as store:
            self.assertIn('"ok": true', actividad.detalle(store, seq)['output'])
            for malo in (0, -1, 'x', 99999):
                with self.subTest(malo=malo), self.assertRaises(ValueError):
                    actividad.detalle(store, malo)


class ServidorTest(Base):
    def setUp(self):
        super().setUp()
        from http.server import ThreadingHTTPServer
        import threading
        from hexos.agent.chat_backend.server import make_handler
        ui = self.casa / 'ui.html'
        ui.write_text('x')
        self.servidor = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.agente, lambda: {}, set(), ui))
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.url = 'http://127.0.0.1:%d' % self.servidor.server_address[1]

    def tearDown(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        super().tearDown()

    def pedir(self, ruta):
        import urllib.error
        import urllib.request
        try:
            with urllib.request.urlopen(self.url + ruta, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def test_la_lista_y_el_detalle_por_http(self):
        seq = self.llamar('terminal.read', dict(command='ls'), 1)
        codigo, lista = self.pedir('/api/activity')
        self.assertEqual((codigo, lista['tools'][0]['summary'], lista['changes']), (200, 'ls', []))
        self.assertEqual(self.pedir('/api/activity/%d' % seq)[1]['tool'], 'terminal.read')
        self.assertEqual(self.pedir('/api/activity/99999')[0], 404)
        self.assertEqual(self.pedir('/api/activity/abc')[0], 404)


if __name__ == '__main__':
    unittest.main()
