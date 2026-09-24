"""Bounded continuation without GPU, tool side effects or live chat messages."""
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock
import tempfile
import unittest

from hexos.agent.native import NativeRuntime
from hexos.agent.native_transport import GenerationInterrupted, TurnCancelled
from hexos.agent.chat import Agent


class ContinuityTest(unittest.TestCase):
    def runtime(self, chunks):
        rt = NativeRuntime.__new__(NativeRuntime)
        rt.names = {'nas_file_read': 'nas.file_read'}
        rt.tools = []; rt.messages = []; rt.pending = deque(); rt.current = None
        rt.template = SimpleNamespace(render=lambda **_: 'PROMPT')
        rt.send = Mock(side_effect=lambda prompt, image: prompt.encode())
        def event():
            value = next(chunks)
            if isinstance(value, Exception):
                raise value
            reason, text = value
            return ['0', '10', '3', '1' if reason == 'stop' else '0', reason], text
        rt.event = event
        rt.notify = Mock()
        return rt

    def test_exact_prefix_no_repeated_code_or_new_user_turn(self):
        rt = self.runtime(iter([('max_tokens', '```html\n<div>'),
                                ('max_tokens', 'hola'), ('eos', '</div>\n```')]))
        result = rt.generate([dict(role='user', content='Crea HTML')])
        self.assertEqual(result['reply'], '```html\n<div>hola</div>\n```')
        self.assertEqual([c.args[0] for c in rt.send.call_args_list],
                         ['PROMPT', 'PROMPT```html\n<div>', 'PROMPT```html\n<div>hola'])
        self.assertEqual(rt.last_generation['continuations'], 2)
        self.assertEqual(rt.last_generation['tokens'], 9)
        self.assertEqual(len(rt.messages), 3)

    def test_split_call_is_queued_only_when_finished(self):
        rt = self.runtime(iter([('max_tokens', '<|tool_call>call:nas_file_read{file_id:'),
                                ('stop', '<|"|>abc<|"|>,offset:0,count:100}<tool_call|>')]))
        out = rt.generate([])
        self.assertEqual(out['tool'], 'nas.file_read')
        self.assertEqual(out['arguments']['file_id'], 'abc')
        self.assertEqual(len(rt.messages[-1]['tool_calls']), 1)

    def test_partial_call_never_executes_or_leaks(self):
        rt = self.runtime(iter([('max_tokens', '<|tool_call>call:nas_file_read{'),
                                ('context_full', 'file_id:')]))
        with self.assertRaises(GenerationInterrupted) as caught:
            rt.generate([])
        self.assertEqual(caught.exception.text, '')
        self.assertFalse(rt.pending)
        self.assertIsNone(rt.current)

    def test_bounded_and_stalled_output_preserved(self):
        for chunks, expected in [([('max_tokens', 'abc')] * 4, 'abc'*4),
                                 ([('max_tokens', 'abc'), ('max_tokens', '')], 'abc'),
                                 ([('max_tokens', 'abc'), ('context_full', 'def')], 'abcdef'),
                                 ([('max_tokens', 'abc'), RuntimeError('context_full')], 'abc')]:
            rt = self.runtime(iter(chunks))
            with self.assertRaises(GenerationInterrupted) as caught:
                rt.generate([])
            self.assertEqual(caught.exception.text, expected)
            self.assertLessEqual(rt.send.call_count, 4)

    def test_cancel_does_not_start_another_segment(self):
        rt = self.runtime(iter([('max_tokens', 'abc'), TurnCancelled()]))
        with self.assertRaises(TurnCancelled):
            rt.generate([])
        self.assertEqual(rt.send.call_count, 2)

    def test_partial_is_archived_and_chat_unlocks(self):
        class Runtime:
            native = False
            def generate(self, messages):
                raise GenerationInterrupted('```html\n<div>hola', 'context_full')
            def call(self, request):
                return {'ok': True}
        with tempfile.TemporaryDirectory() as workspace:
            agent = Agent(workspace, Runtime())
            result = agent.chat('Crea una página')
            self.assertTrue(result['incomplete'])
            self.assertIn('<div>hola\n```', result['reply'])
            with agent.store() as store:
                rows = store.db.execute('SELECT text FROM conversation ORDER BY rowid').fetchall()
            self.assertEqual(rows[-1][0], result['reply'])
            self.assertEqual(agent.state, 'idle')
            self.assertFalse(agent.lock.locked())
            self.assertIsNone(agent.generation_snapshot())


if __name__ == '__main__':
    unittest.main()
