"""Una búsqueda vacía que cierra un turno se señala en el siguiente, una sola vez."""
import json
import sqlite3
import unittest
from types import SimpleNamespace

from hexos.agent import sin_resolver


class SinResolverTest(unittest.TestCase):
    def setUp(self):
        db = sqlite3.connect(':memory:')
        db.row_factory = sqlite3.Row
        db.executescript('CREATE TABLE conversation(id,role);'
                         'CREATE VIEW esta_ventana AS SELECT rowid AS rowid, id, role FROM conversation;'
                         'CREATE TABLE tool_events(seq INTEGER PRIMARY KEY, turn_id, body);')
        self.store = SimpleNamespace(db=db)

    def turno(self, id, *eventos):
        self.store.db.execute('INSERT INTO conversation VALUES (?,?)', (id, 'user'))
        for evento in eventos:
            self.store.db.execute('INSERT INTO tool_events(turn_id,body) VALUES (?,?)', (id, json.dumps(evento)))

    def test_busqueda_vacia_con_lo_que_falta(self):
        self.turno('a', dict(tool='nas.find', arguments=dict(query='Deadpool'),
                             result=dict(total_matches=0, falta_por_mirar='el resto del NAS')))
        self.turno('b')
        texto = sin_resolver.bloque(self.store, 'b')
        self.assertIn('Deadpool', texto)
        self.assertIn('el resto del NAS', texto)

    def test_terminal_vacia(self):
        self.turno('a', dict(tool='terminal.read', arguments=dict(command='dpkg -l', filter='x'),
                             result=dict(lines=0, falta_por_mirar=['flatpak', 'snap'])))
        self.turno('b')
        self.assertIn('flatpak, snap', sin_resolver.bloque(self.store, 'b'))

    def test_turno_resuelto_no_dice_nada(self):
        self.turno('a', dict(tool='terminal.read', arguments={}, result=dict(lines=2, falta_por_mirar=['snap'])))
        self.turno('b')
        self.assertEqual(sin_resolver.bloque(self.store, 'b'), '')

    def test_si_siguio_y_encontro_no_dice_nada(self):
        self.turno('a', dict(tool='nas.find', arguments={}, result=dict(total_matches=0, falta_por_mirar='x')),
                   dict(tool='nas.find', arguments={}, result=dict(total_matches=3)))
        self.turno('b')
        self.assertEqual(sin_resolver.bloque(self.store, 'b'), '')

    def test_solo_el_turno_siguiente(self):
        self.turno('a', dict(tool='nas.find', arguments={}, result=dict(total_matches=0, falta_por_mirar='x')))
        self.turno('b')
        self.turno('c')
        self.assertEqual(sin_resolver.bloque(self.store, 'c'), '')

    def test_primer_turno(self):
        self.turno('a')
        self.assertEqual(sin_resolver.bloque(self.store, 'a'), '')


if __name__ == '__main__':
    unittest.main()
