"""Una ruta que no existe en un NAS devuelve las raíces observadas de ese mismo NAS."""
import tempfile
import unittest
from unittest import mock

from hexos.agent.chat import Agent
from hexos.agent.file_catalog.presentation import bounded_page
from hexos.agent.file_catalog.sqlite_repository import database, remember_directories


class Runtime:
    def call(self, request): pass
    def generate(self, messages): return {'reply': '', 'work': None}


class RaicesConocidasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.agent = Agent(self.tmp.name, Runtime())
        db = database(self.tmp.name)
        with db:
            remember_directories(db, 'synology 1', ['/volume1/multimedia 1/Multimedia', '/volume4/multimedia 3/multimedia',
                                                    '/volume4/multimedia 3/multimedia/marvel/Capitana Marvel'], '2026-10-08T12:00:00Z')
            remember_directories(db, 'synology home', ['/volume1/multimedia', '/volume1/multimedia/peliculas'],
                                 '2026-10-08T12:00:00Z')
        db.close()

    def buscar(self, errores, buenas=()):
        """Pasa por bounded_page, como el nas.find real: los errores quedan en coverage."""
        def find(workspace, **args):
            return bounded_page(dict(device=args['device'], items=[], roots=list(args['roots']), totals=[], offset=0,
                                     total_matches=0, complete=not errores,
                                     coverage=dict(complete=not errores, errors=[
                                         dict(path=r, errno=2, reason='invalid_or_unreadable_root') for r in errores])))
        with mock.patch('hexos.agent.nas_files.find', find), self.agent.store() as store:
            return self.agent.tool(store, 'nas.find', dict(device='synology 1', query='spider',
                                                         roots=[*errores, *buenas] or ['/volume4/multimedia 3/multimedia']))

    def test_ruta_inexistente_trae_las_raices_del_mismo_equipo(self):
        r = self.buscar(['/volume1/multimedia'])
        # Primero lo parecido a «multimedia»; la subcarpeta de Marvel no se parece y no es compartida.
        self.assertEqual(r['known_roots'][:2], ['/volume1/multimedia 1/Multimedia', '/volume4/multimedia 3/multimedia'])
        self.assertNotIn('/volume4/multimedia 3/multimedia/marvel/Capitana Marvel', r['known_roots'])
        self.assertNotIn('/volume1/multimedia/peliculas', r['known_roots'])  # es del otro NAS
        self.assertIn('synology 1', r['known_roots_note'])

    def test_una_raiz_buena_no_esconde_la_mala(self):
        # El 30/10 respondió /volume4 y la raíz equivocada de /volume1 pasó sin que nadie la corrigiera.
        r = self.buscar(['/volume1/multimedia'], buenas=['/volume4/multimedia 3/multimedia'])
        self.assertEqual(r['known_roots'][0], '/volume1/multimedia 1/Multimedia')

    def test_nas_browse_trae_el_error_arriba(self):
        def browse(workspace, **args):
            return dict(device=args['device'], path=args['path'], items=[], complete=False,
                        errors=[dict(path=args['path'], errno=2, reason='invalid_or_unreadable_root')])
        with mock.patch('hexos.agent.nas_files.browse', browse), self.agent.store() as store:
            r = self.agent.tool(store, 'nas.browse', dict(device='synology 1', path='/volume1/multimedia'))
        self.assertEqual(r['known_roots'][:2], ['/volume1/multimedia 1/Multimedia', '/volume4/multimedia 3/multimedia'])

    def test_sin_error_no_añade_nada(self):
        self.assertNotIn('known_roots', self.buscar([]))


if __name__ == '__main__':
    unittest.main()
