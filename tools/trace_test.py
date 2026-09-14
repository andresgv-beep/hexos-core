"""La traza que consume una interfaz: qué se ejecutó, cuánto tardó y si cambió algo."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent


class ScriptedRuntime:
    """Devuelve una secuencia fija de decisiones, como haría el modelo."""

    def __init__(self, *decisions):
        self.decisions = list(decisions)

    def call(self, request):
        pass

    def generate(self, messages):
        return self.decisions.pop(0)


class TraceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-trace-test-')

    def tearDown(self):
        self.tmp.cleanup()

    def run_turn(self, *decisions):
        agent = Agent(self.tmp.name, ScriptedRuntime(*decisions))
        return agent, agent.chat('haz algo')

    def test_each_call_says_whether_it_changed_state(self):
        agent, result = self.run_turn(
            {'tool': 'device.list', 'arguments': {}},
            {'reply': 'Listo.', 'work': None})
        entry = result['tools'][0]
        self.assertEqual(entry['tool'], 'device.list')
        self.assertEqual(entry['effect'], 'read')
        self.assertFalse(entry['changes_state'])
        self.assertFalse(entry['failed'])
        self.assertIsInstance(entry['seconds'], float)
        self.assertTrue(entry['ts'])

    def test_a_write_is_marked_as_such_for_the_interface(self):
        agent, result = self.run_turn(
            {'tool': 'nas.container', 'arguments': {'container': 'plex', 'action': 'stop'}},
            {'reply': 'Hecho.', 'work': None})
        entry = result['tools'][0]
        self.assertEqual(entry['effect'], 'write_container')
        self.assertTrue(entry['changes_state'], 'parar un contenedor no puede figurar como lectura')

    def test_a_failed_call_is_flagged_and_still_timed(self):
        # Falla antes de ejecutarse: la traza debe existir igual, sin romper el turno.
        agent, result = self.run_turn(
            {'tool': 'nas.container', 'arguments': {'container': 'plex'}},
            {'reply': 'No pude.', 'work': None})
        entry = result['tools'][0]
        self.assertTrue(entry['failed'])
        self.assertIn('error', entry['result'])
        self.assertIsInstance(entry['seconds'], float)

    def test_history_returns_what_was_executed_after_a_reload(self):
        agent, _ = self.run_turn(
            {'tool': 'device.list', 'arguments': {}},
            {'reply': 'Listo.', 'work': None})
        with agent.store() as store:
            rows = [dict(r) for r in store.db.execute("SELECT id, role FROM conversation WHERE role='user'")]
            saved = [json.loads(e['body']) for e in store.db.execute(
                'SELECT body FROM tool_events WHERE turn_id=? ORDER BY seq', (rows[0]['id'],))]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]['tool'], 'device.list')
        # Lo persistido lleva los mismos campos que la respuesta en vivo.
        for field in ('effect', 'changes_state', 'ts', 'seconds', 'failed'):
            self.assertIn(field, saved[0])


class AvancePorPasoTest(unittest.TestCase):
    """Un turno con varias herramientas tiene que verse entero, no solo su primer paso."""

    class ConPreambulo(ScriptedRuntime):
        """Como el modelo nativo: a veces antecede la llamada con una frase suya."""

        def __init__(self, *decisions, preambulos=()):
            super().__init__(*decisions)
            self.preambulos = list(preambulos)
            self.last_preamble = None
            self.anuncios = 0

        def generate(self, messages):
            self.last_preamble = self.preambulos.pop(0) if self.preambulos else None
            return super().generate(messages)

        def announce(self, tool, arguments, request):
            self.anuncios += 1
            return 'Voy a mirarlo.'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-avance-test-')

    def tearDown(self):
        self.tmp.cleanup()

    def turno(self, runtime):
        agent = Agent(self.tmp.name, runtime)
        return agent, agent.chat('revisa y luego mira los equipos')

    def test_cada_llamada_deja_su_aviso(self):
        runtime = self.ConPreambulo(
            {'tool': 'device.list', 'arguments': {}},
            {'tool': 'device.list', 'arguments': {'query': 'nas'}},
            {'reply': 'Listo.', 'work': None},
            preambulos=['Primero miro el inventario.', 'Ahora filtro por nas.', None])
        agent, resultado = self.turno(runtime)
        textos = [m['text'] for m in resultado['progress']['messages']]
        self.assertEqual(textos, ['Primero miro el inventario.', 'Ahora filtro por nas.'])
        # Y quedan guardados en orden, no solo en la respuesta.
        with agent.store() as store:
            filas = [r['text'] for r in store.db.execute(
                'SELECT text FROM progress_events ORDER BY rowid')]
        self.assertEqual(filas, textos)

    def test_la_inferencia_de_respaldo_solo_se_paga_una_vez(self):
        # Una generación entera por paso solo para redactar «voy a mirarlo» costaría
        # más que el paso; sin preámbulo propio, la herramienta ya se ve en la traza.
        runtime = self.ConPreambulo(
            {'tool': 'device.list', 'arguments': {}},
            {'tool': 'device.list', 'arguments': {'query': 'nas'}},
            {'reply': 'Listo.', 'work': None},
            preambulos=[None, None, None])
        agent, resultado = self.turno(runtime)
        self.assertEqual(runtime.anuncios, 1)
        self.assertEqual([m['text'] for m in resultado['progress']['messages']],
                         ['Voy a mirarlo.'])

    def test_el_estado_final_no_borra_los_avances(self):
        runtime = self.ConPreambulo(
            {'tool': 'device.list', 'arguments': {}},
            {'reply': 'Ya está.', 'work': None},
            preambulos=['Miro el inventario.', None])
        agent, resultado = self.turno(runtime)
        self.assertEqual(resultado['reply'], 'Ya está.')
        self.assertEqual(len(resultado['progress']['messages']), 1)


if __name__ == '__main__':
    unittest.main()
