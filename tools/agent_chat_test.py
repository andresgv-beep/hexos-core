"""Pruebas del puente con runtime simulado; no certifican calidad del LLM."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent


class FakeRuntime:
    def call(self, request):
        assert request == {'type': 'reset'}

    def generate(self, messages):
        return {'reply': 'Documento recibido.', 'work': None}


class RuntimeConVision(FakeRuntime):
    def __init__(self):
        self.imagenes = []

    def attach_image(self, pixels, width, height):
        self.imagenes.append((len(pixels), width, height))


class ChatTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-agent-test-')
        self.agent = Agent(self.tmp.name, FakeRuntime())

    def tearDown(self):
        self.tmp.cleanup()

    def test_long_paste_exact_and_reopen(self):
        raw = '\n'.join(f'{i} árbol café 😀' for i in range(8000)) + '\r\nFINAL=47\n'
        result = self.agent.chat(raw)
        doc = result['document']
        self.assertGreater(doc['bytes'], 65536)
        self.assertEqual(doc['sha256'], hashlib.sha256(raw.encode()).hexdigest())
        restarted = Agent(self.tmp.name, FakeRuntime())
        with restarted.store() as store:
            saved = store.db.execute('SELECT content FROM documents WHERE id=?', (doc['id'],)).fetchone()[0]
            self.assertEqual(saved, raw)
            hit = restarted.tool(store, 'document.search', {'id': doc['id'], 'query': 'FINAL='})
            self.assertEqual(hit['matches'][0]['line'], 8001)
            read = restarted.tool(store, 'document.read', {'id': doc['id'], 'start': 8001, 'count': 1})
            self.assertEqual(read['lines'][0]['text'], 'FINAL=47')

    def test_invalid_classification_does_not_create_job(self):
        self.agent.runtime.generate = lambda _: {'reply':'hola','work':dict(
            title='x',kind='inventado',scope='NAS',tags=[],reason='x')}
        with self.assertRaises(ValueError):
            self.agent.chat('Revisa el NAS')
        with self.agent.store() as store:
            self.assertEqual(store.listing(), [])

    def test_classification_visible_and_correctable(self):
        self.agent.runtime.generate = lambda _: {'reply':'Ficha creada','work':dict(
            title='Revisión NAS',kind='diagnostico',scope='NAS',tags=[],reason='Consulta de disco')}
        job = self.agent.chat('Revisa el disco')['work']
        with self.agent.store() as store:
            listed = store.listing(scope='NAS')
            self.assertEqual(listed[0]['classification_status'], 'proposed')
            self.assertEqual(listed[0]['id'], job['id'])
            corrected = store.dispatch(dict(op='classify',id=job['id'],revision=job['revision'],
                kind='mantenimiento',scope='Copias',tags=[],reason='Corrección'), actor='user')
            self.assertEqual(corrected['scope'], 'Copias')


class TurnoSoloImagenTest(unittest.TestCase):
    """Adjuntar una foto sin escribir nada es un turno con sentido."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-imagen-test-')
        self.runtime = RuntimeConVision()
        self.agent = Agent(self.tmp.name, self.runtime)

    def tearDown(self):
        self.tmp.cleanup()

    def test_una_imagen_sin_texto_se_acepta_con_la_pregunta_implicita(self):
        from hexos.agent.chat import IMAGEN_SIN_TEXTO
        self.agent.chat('   ', image=(b'\x00' * 12, 2, 2))
        self.assertEqual(self.runtime.imagenes, [(12, 2, 2)])
        with self.agent.store() as store:
            fila = store.db.execute("SELECT text FROM conversation WHERE role='user'").fetchone()
        # Queda en el historial la pregunta que se dio por hecha, no un turno en blanco.
        self.assertIn(IMAGEN_SIN_TEXTO, fila['text'])
        self.assertIn('adjuntó una imagen', fila['text'])

    def test_sin_imagen_un_mensaje_en_blanco_sigue_siendo_un_error(self):
        for vacio in ('', '   ', '\n'):
            with self.assertRaises(ValueError):
                self.agent.chat(vacio)


if __name__ == '__main__':
    unittest.main()
