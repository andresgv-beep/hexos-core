"""Resultados de herramientas antiguos: se resumen en vez de viajar en cada turno."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from hexos.agent import tool_digest
from hexos.agent.context import native_messages

NOW = 1_790_000_000.0
BIG = {'disks': [{'name': 'sd' + c, 'smart': 'PASSED', 'log': 'x' * 300} for c in 'abc']}
SMALL = {'id': 'nota-1', 'saved': True}
NAMES = {'nas_read': 'nas.read', 'note_save': 'note.save'}
EFFECTS = {'nas.read': 'read', 'note.save': 'write'}


def tool_turn(alias, response, ts):
    return {'role': 'assistant', 'tool_calls': [{'function': {'name': alias, 'arguments': {}}}],
            'tool_responses': [{'name': alias, 'response': response, 'ts': ts}]}


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


class LiveConversationTest(unittest.TestCase):
    def conversation(self, last_age):
        return [
            {'role': 'system', 'content': 'política'},
            {'role': 'user', 'content': 'mira los discos'},
            tool_turn('nas_read', BIG, NOW - 900),
            {'role': 'assistant', 'content': 'Los tres discos están bien.'},
            {'role': 'user', 'content': 'guarda una nota'},
            tool_turn('note_save', SMALL, NOW - 600),
            {'role': 'assistant', 'content': 'Guardada.'},
            {'role': 'user', 'content': 'y los contenedores'},
            tool_turn('nas_read', dict(BIG), NOW - last_age),
            {'role': 'assistant', 'content': 'Todos en marcha.'},
        ]

    def test_old_big_result_becomes_a_dated_stub_and_small_ones_stay(self):
        messages = self.conversation(last_age=60)
        self.assertEqual(tool_digest.compact_live(messages, NAMES, EFFECTS, now=NOW), 1)
        old = messages[2]['tool_responses'][0]['response']
        self.assertTrue(tool_digest.is_stub(old))
        self.assertIn('hace 15 min', old['resultado_anterior'])
        self.assertIn('nas_read', old['nota'])
        self.assertEqual(messages[5]['tool_responses'][0]['response'], SMALL)
        self.assertEqual(messages[8]['tool_responses'][0]['response'], BIG)
        self.assertEqual(messages[2]['tool_calls'][0]['function']['name'], 'nas_read')

    def test_last_group_is_summarised_once_it_is_stale(self):
        messages = self.conversation(last_age=tool_digest.FRESH_SECONDS + 60)
        self.assertEqual(tool_digest.compact_live(messages, NAMES, EFFECTS, now=NOW), 2)
        self.assertTrue(tool_digest.is_stub(messages[8]['tool_responses'][0]['response']))
        self.assertEqual(tool_digest.compact_live(messages, NAMES, EFFECTS, now=NOW), 0)

    def test_write_results_point_to_history_and_forbid_repeating(self):
        messages = [{'role': 'user', 'content': 'guarda'}, tool_turn('note_save', BIG, NOW - 900),
                    {'role': 'user', 'content': 'otra cosa'}, tool_turn('nas_read', BIG, NOW - 30)]
        tool_digest.compact_live(messages, NAMES, EFFECTS, now=NOW)
        note = messages[1]['tool_responses'][0]['response']['nota']
        self.assertIn('no repitas la acción', note)
        self.assertEqual(messages[3]['tool_responses'][0]['response'], BIG)

    def test_nothing_to_do_without_tools(self):
        self.assertEqual(tool_digest.compact_live([{'role': 'user', 'content': 'hola'}], NAMES, EFFECTS, now=NOW), 0)


class RebuildTest(unittest.TestCase):
    def rebuild(self, newest_age, now):
        history = [dict(id='u1', role='user', text='mira los discos'),
                   dict(id='a1', role='assistant', text='Los tres discos están bien.'),
                   dict(id='u2', role='user', text='y los contenedores'),
                   dict(id='a2', role='assistant', text='Todos en marcha.')]
        events = {'u1': [dict(tool='nas.read', arguments={}, result=BIG, ts=iso(now - 900))],
                  'u2': [dict(tool='nas.read', arguments={}, result=BIG, ts=iso(now - newest_age))]}
        messages = native_messages(history, '', 'siguiente', events, budget=20000)
        return [m['tool_responses'][0] for m in messages if m.get('tool_responses')]

    def test_rebuild_applies_the_same_rule(self):
        import time
        now = time.time()
        old, newest = self.rebuild(newest_age=30, now=now)
        self.assertTrue(tool_digest.is_stub(old['response']))
        self.assertEqual(newest['response'], BIG)
        self.assertAlmostEqual(newest['ts'], now - 30, delta=1)
        old, newest = self.rebuild(newest_age=tool_digest.FRESH_SECONDS + 60, now=now)
        self.assertTrue(tool_digest.is_stub(newest['response']))


class TemplateTest(unittest.TestCase):
    def test_timestamp_is_not_rendered_into_the_prompt(self):
        import jinja2
        template_path = Path('/home/andres/Documentos/GitHub/helios_convert_v9.1/models/gemma 4 12b-it/chat_template.jinja')
        if not template_path.exists():
            self.skipTest('plantilla del modelo no disponible')
        template = jinja2.Environment().from_string(template_path.read_text())
        messages = [{'role': 'user', 'content': 'mira'}, tool_turn('nas_read', SMALL, NOW)]
        prompt = template.render(messages=messages, tools=[], bos_token='<bos>', add_generation_prompt=True)
        self.assertIn('nota-1', prompt)
        self.assertNotIn(str(int(NOW)), prompt)
        self.assertNotIn('ts:', prompt)


if __name__ == '__main__':
    unittest.main()
