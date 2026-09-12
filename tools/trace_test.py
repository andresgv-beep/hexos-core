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


if __name__ == '__main__':
    unittest.main()
