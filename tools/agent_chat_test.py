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


class AfirmacionSinEscrituraTest(unittest.TestCase):
    """Si canta una escritura que no hizo, HexOS le devuelve el turno para que la haga."""

    class Guionizado:
        """Runtime que responde una lista de salidas, en orden."""
        def __init__(self, salidas):
            self.salidas = list(salidas)
            self.recibido = []

        def call(self, request):
            assert request == {'type': 'reset'}

        def generate(self, messages):
            self.recibido.append(messages)
            return self.salidas.pop(0)

    def correr(self, salidas):
        tmp = tempfile.TemporaryDirectory(prefix='hexos-afirma-')
        self.addCleanup(tmp.cleanup)
        runtime = self.Guionizado(salidas)
        agent = Agent(tmp.name, runtime)
        return agent, runtime, agent.chat('apunta el estado del NAS')

    def test_se_le_devuelve_el_turno_y_entonces_guarda(self):
        agent, runtime, result = self.correr([
            {'reply': 'He recopilado el estado y lo he guardado en una nota.', 'work': None},
            {'tool': 'note.save', 'arguments': {'title': 'Estado del NAS', 'body': 'Todo correcto.'}},
            {'reply': 'Hecho, la nota queda guardada.', 'work': None},
        ])
        self.assertEqual([t['tool'] for t in result['tools']], ['note.save'])
        self.assertEqual(result['closure']['reason'], 'comprobado')
        # Y el aviso que se le mandó dice de dónde viene, para que no lo lea como a la persona.
        self.assertIn('AVISO DE HEXOS', runtime.recibido[1][0]['content'])
        with agent.store() as store:
            self.assertEqual(notes_count(store), 1)

    def test_si_no_había_nada_que_guardar_se_queda_en_la_respuesta(self):
        _, _, result = self.correr([
            {'reply': 'Ya lo había guardado antes.', 'work': None},
            {'reply': 'Te cuento el estado; no he guardado nada en este turno.', 'work': None},
        ])
        self.assertEqual(result['tools'], [])
        self.assertEqual(result['reply'], 'Te cuento el estado; no he guardado nada en este turno.')

    def test_solo_se_le_devuelve_una_vez(self):
        _, runtime, result = self.correr([
            {'reply': 'Lo he guardado.', 'work': None},
            {'reply': 'Lo he guardado, de verdad.', 'work': None},
        ])
        # No se insiste en bucle: se cierra diciendo que no consta.
        self.assertEqual(result['closure']['reason'], 'no_consta')
        self.assertEqual(len(runtime.recibido), 2)

    def test_una_respuesta_que_no_afirma_nada_no_gasta_turnos(self):
        _, runtime, result = self.correr([
            {'reply': 'El disco sda pierde el enlace.', 'work': None},
        ])
        self.assertEqual(len(runtime.recibido), 1)


def notes_count(store):
    return store.db.execute('SELECT COUNT(*) FROM notes').fetchone()[0]


class PromesaEnElBucleTest(unittest.TestCase):
    """Si promete y el turno acaba, se le devuelve una vez para que lo haga."""

    class Guionizado:
        def __init__(self, salidas):
            self.salidas = list(salidas); self.recibido = []
        def call(self, request): pass
        def generate(self, messages):
            self.recibido.append(messages); return self.salidas.pop(0)

    def correr(self, salidas):
        tmp = tempfile.TemporaryDirectory(prefix='hexos-promesa-')
        self.addCleanup(tmp.cleanup)
        runtime = self.Guionizado(salidas)
        agent = Agent(tmp.name, runtime)
        return runtime, agent.chat('revisa los contenedores')

    def test_se_le_devuelve_el_turno_y_entonces_lo_hace(self):
        runtime, result = self.correr([
            {'reply': 'Ahora voy a revisar los contenedores. Dame un momento.', 'work': None},
            {'tool': 'note.save', 'arguments': {'title': 'Contenedores', 'body': 'Todos en marcha.'}},
            {'reply': 'Listo: todos en marcha.', 'work': None},
        ])
        self.assertEqual([t['tool'] for t in result['tools']], ['note.save'])
        self.assertIn('AVISO DE HEXOS', runtime.recibido[1][0]['content'])
        self.assertIn('sin haberlo hecho', runtime.recibido[1][0]['content'])

    def test_solo_se_insiste_una_vez(self):
        runtime, result = self.correr([
            {'reply': 'Voy a revisar el NAS.', 'work': None},
            {'reply': 'Voy a revisar el NAS, en serio.', 'work': None},
        ])
        self.assertEqual(result['reply'], 'Voy a revisar el NAS, en serio.')
        self.assertEqual(len(runtime.recibido), 2)

    def test_una_respuesta_que_no_promete_nada_no_gasta_turnos(self):
        runtime, _ = self.correr([{'reply': 'Hay tres contenedores en marcha.', 'work': None}])
        self.assertEqual(len(runtime.recibido), 1)


class CoberturaEnElBucleTest(unittest.TestCase):
    """Se insiste mientras avance, y se para cuando deja de avanzar."""

    class Guionizado:
        def __init__(self, salidas):
            self.salidas = list(salidas); self.recibido = []
        def call(self, request): pass
        def generate(self, messages):
            self.recibido.append(messages)
            return self.salidas.pop(0) if self.salidas else {'reply': 'Ya está.', 'work': None}

    def correr(self, salidas, texto):
        from hexos.agent import hosts
        tmp = tempfile.TemporaryDirectory(prefix='hexos-cob-bucle-')
        self.addCleanup(tmp.cleanup)
        hosts.save(tmp.name, 'uno', 'helios', 'x')
        hosts.save(tmp.name, 'dos', 'helios', 'x')
        runtime = self.Guionizado(salidas)
        agent = Agent(tmp.name, runtime)
        lee = lambda **args: {'tool': 'nas.read', 'arguments': args}
        return runtime, agent.chat(texto), lee

    def test_insiste_hasta_cubrir_lo_pedido(self):
        from unittest.mock import patch
        salidas = [
            {'reply': 'Aquí tienes el resumen de los dos.', 'work': None},
            {'tool': 'nas.read', 'arguments': dict(device='uno', section='containers')},
            {'reply': 'Listo con uno.', 'work': None},
            {'tool': 'nas.read', 'arguments': dict(device='dos', section='containers')},
            {'reply': 'Ahora sí, los dos revisados.', 'work': None},
        ]
        with patch('hexos.agent.chat.nas_read', return_value=dict(output='', exit_code=0)):
            runtime, result, _ = self.correr(salidas, 'revisa uno y dos y sus contenedores')
        self.assertEqual(len({(t['arguments']['device']) for t in result['tools']}), 2)
        self.assertEqual(result['reply'], 'Ahora sí, los dos revisados.')

    def test_si_un_aviso_no_trae_lectura_nueva_no_se_repite(self):
        salidas = [
            {'reply': 'Resumen de los dos.', 'work': None},
            {'reply': 'Te lo repito igual.', 'work': None},
        ]
        runtime, result, _ = self.correr(salidas, 'revisa uno y dos y sus contenedores')
        # Un aviso, y al no avanzar se cierra en vez de porfiar.
        self.assertEqual(result['reply'], 'Te lo repito igual.')
        self.assertEqual(len(runtime.recibido), 2)
