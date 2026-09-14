"""Notas del núcleo: guardar, retocar sin destruir, y que lo guardado se relea."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent import notes
from hexos.agent.work import WorkStore


class NotasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-notas-')
        self.addCleanup(self.tmp.cleanup)
        self.store = WorkStore(self.tmp.name)
        self.addCleanup(self.store.close)
        notes.initialize(self.store)

    def crear(self, title='Cambiar el cable de sda', body='El disco pierde el enlace.'):
        return notes.dispatch(self.store, 'note.save', dict(title=title, body=body), 'turno-1')

    def test_una_nota_nueva_nace_pendiente_y_se_relee(self):
        n = self.crear()
        self.assertTrue(n['created'])
        self.assertEqual(n['state'], 'pendiente')
        self.assertEqual(n['revision'], 1)
        # La prueba de que se guardó no es que no fallara: es haberlo releído.
        self.assertEqual(n['outcome'], 'hecho')
        self.assertIn('releído del almacén', n['checked'])

    def test_retocar_no_destruye_la_version_anterior(self):
        n = self.crear()
        notes.dispatch(self.store, 'note.save',
                       dict(id=n['id'], body='El disco pierde el enlace. Cable pedido.'), 'turno-2')
        cuerpos = [r['body'] for r in notes.history(self.store, n['id'])]
        self.assertEqual(cuerpos, ['El disco pierde el enlace.',
                                   'El disco pierde el enlace. Cable pedido.'])

    def test_retocar_solo_el_titulo_conserva_el_cuerpo(self):
        n = self.crear()
        r = notes.dispatch(self.store, 'note.save', dict(id=n['id'], title='Cable de sda'), 'turno-2')
        self.assertEqual(r['body'], 'El disco pierde el enlace.')
        self.assertEqual(r['revision'], 2)

    def test_editar_sobre_una_version_vieja_se_rechaza(self):
        n = self.crear()
        notes.dispatch(self.store, 'note.save', dict(id=n['id'], body='otra cosa'), 'turno-2')
        with self.assertRaises(ValueError) as e:
            notes.dispatch(self.store, 'note.save',
                           dict(id=n['id'], body='tercera', revision=n['revision']), 'turno-3')
        self.assertIn('cambió desde que la leíste', str(e.exception))

    def test_descartar_la_saca_de_la_lista_pero_no_borra_el_texto(self):
        n = self.crear()
        notes.dispatch(self.store, 'note.mark', dict(id=n['id'], state='descartada'), 'turno-2')
        self.assertEqual(notes.dispatch(self.store, 'note.list', {}, 't')['notes'], [])
        # Sigue ahí, y se puede pedir a propósito.
        pedidas = notes.dispatch(self.store, 'note.list', dict(state='descartada'), 't')['notes']
        self.assertEqual([x['id'] for x in pedidas], [n['id']])
        self.assertEqual(notes.get(self.store, n['id'])['body'], 'El disco pierde el enlace.')

    def test_anclar_a_favoritos_se_comprueba_releyendo(self):
        n = self.crear()
        r = notes.dispatch(self.store, 'note.mark', dict(id=n['id'], favorite=True), 'turno-2')
        self.assertTrue(r['favorite'])
        self.assertEqual(r['outcome'], 'hecho')
        anclada = notes.dispatch(self.store, 'note.list', dict(favorite=True), 't')['notes']
        self.assertEqual([x['id'] for x in anclada], [n['id']])

    def test_la_lista_recorta_el_cuerpo_y_lo_dice(self):
        self.crear(body='x' * 500)
        fila = notes.dispatch(self.store, 'note.list', {}, 't')['notes'][0]
        self.assertEqual(len(fila['body']), 300)
        self.assertTrue(fila['truncated'])

    def test_buscar_mira_titulo_cuerpo_y_etiquetas(self):
        self.crear()
        notes.dispatch(self.store, 'note.save',
                       dict(title='Comprar pan', body='del bueno', tags=['casa']), 't')
        for consulta, cuantas in (('sda', 1), ('casa', 1), ('disco', 1), ('zzz', 0)):
            with self.subTest(consulta):
                self.assertEqual(len(notes.dispatch(self.store, 'note.list',
                                                    dict(query=consulta), 't')['notes']), cuantas)

    def test_una_nota_nueva_sin_texto_no_se_crea(self):
        with self.assertRaises(ValueError):
            notes.dispatch(self.store, 'note.save', dict(title='sola'), 't')

    def test_estado_inventado_se_rechaza(self):
        n = self.crear()
        with self.assertRaises(ValueError) as e:
            notes.dispatch(self.store, 'note.mark', dict(id=n['id'], state='archivada'), 't')
        self.assertIn('pendiente', str(e.exception))

    def test_tocar_una_nota_que_no_existe_no_crea_una(self):
        with self.assertRaises(ValueError):
            notes.dispatch(self.store, 'note.save', dict(id='inventado', body='hola'), 't')
        self.assertEqual(notes.dispatch(self.store, 'note.list', {}, 't')['total'], 0)


if __name__ == '__main__':
    unittest.main()
