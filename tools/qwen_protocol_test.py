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

    def test_size_arithmetic_is_folded_outside_strings(self):
        # La llamada literal que tumbó un turno: «Expecting ',' delimiter».
        raw = ('<tool_call>\n{"name": "nas_find", "arguments": {"device": "Synology", "extensions": '
               '["mkv", "mp4", "avi"], "min_bytes": 20 * 1024 * 1024 * 1024, '
               '"max_bytes": 40*1024*1024*1024}}\n</tool_call>')
        args = q.calls(raw)[0]['arguments']
        self.assertEqual((args['min_bytes'], args['max_bytes']), (20*1024**3, 40*1024**3))
        kept = q.calls('<tool_call>{"name":"a","arguments":{"query":"2 * 3 \\" 4*5","n":2*3}}</tool_call>')
        self.assertEqual(kept[0]['arguments'], {'query': '2 * 3 " 4*5', 'n': 6})
        for bad in ('"n":2*x', '"n":2**3', '"n":eval(1)'):
            with self.subTest(bad), self.assertRaises(ValueError):
                q.calls('<tool_call>{"name":"a","arguments":{' + bad + '}}</tool_call>')

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
