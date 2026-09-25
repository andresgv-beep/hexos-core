import unittest
from hexos.agent import qwen_protocol as q
from hexos.agent.native_transport import visible_preview

class Tests(unittest.TestCase):
    def test_calls(self):
        self.assertEqual(q.calls('<tool_call>{"name":"note_list","arguments":{}}</tool_call>'),
                         [dict(name='note_list', arguments={})])
        for value in ('{"name":"a","name":"b","arguments":{}}', '{"name":"a","arguments":null}'):
            with self.assertRaises(ValueError):q.calls('<tool_call>'+value+'</tool_call>')
        with self.assertRaises(ValueError):q.calls('<tool_call>{"name":"a","arguments":{}}</tool_call>extra')

    def test_results_and_thought(self):
        source = [dict(role='assistant', tool_calls=[], tool_responses=[
            dict(name='note_list',response={'total':2})])]
        rendered = q.render_messages(source)
        self.assertEqual(rendered[1]['role'], 'tool')
        self.assertIn('"total": 2', rendered[1]['content'])
        self.assertIn('tool_responses',source[0])
        self.assertEqual(q.split_thought('<think>private</think>Hola'), ('Hola','private'))
        self.assertEqual(visible_preview('<think>private'), '')
        self.assertEqual(visible_preview('<think>private</think>Hola'), 'Hola')
