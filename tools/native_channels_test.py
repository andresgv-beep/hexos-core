"""Compatibilidad del canal thought entre preámbulo visible y llamada nativa."""
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

from hexos.agent.native import NativeRuntime, NativeSyntax, split_thinking, calls_from_text
from hexos.agent.native_transport import visible_preview

CALL = '<|tool_call>call:nas_file_read{file_id:<|"|>abc<|"|>,offset:4000,count:4000}<tool_call|>'
PREAMBLE = 'He leído solo la primera parte. Continuaré desde donde me quedé.\n'


class NativeChannelsTest(unittest.TestCase):
    def runtime(self, completion, finish='stop'):
        runtime = NativeRuntime.__new__(NativeRuntime)
        runtime.names = {'nas_file_read':'nas.file_read'}
        runtime.tools = []
        runtime.pending = deque()
        runtime.messages = []
        runtime.current = None
        runtime.template = SimpleNamespace(render=Mock(return_value='stable prompt'))
        runtime.send = lambda prompt, image: prompt.encode()
        runtime.event = lambda: (['0','1','1','1',finish], completion)
        runtime.notify = Mock()
        return runtime

    def test_reported_sequence_preserves_offset_and_registers_one_call(self):
        raw = PREAMBLE + '<|channel>thought\n<channel|>' + CALL
        runtime = self.runtime(raw)
        decision = runtime.generate([{'role':'user','content':'Continúa la lectura'}])
        self.assertEqual(decision, {'tool':'nas.file_read', 'arguments':{'file_id':'abc','offset':4000,'count':4000}})
        self.assertEqual(runtime.last_preamble, PREAMBLE.strip())
        self.assertEqual(runtime.last_generation['raw'], raw)
        self.assertNotIn('<|channel>', runtime.last_generation['visible_output'])
        self.assertEqual(runtime.messages[-1]['reasoning'], '')
        runtime.tool_result({'text':'siguiente fragmento','next_offset':8000})
        self.assertEqual(len(runtime.messages[-1]['tool_calls']),1)
        self.assertEqual(len(runtime.messages[-1]['tool_responses']),1)
        self.assertIsNone(runtime.current)
        self.assertFalse(runtime.pending)

    def test_reasoning_is_not_preamble_or_executable_calls(self):
        hidden = 'SECRETO ' + '<|tool_call>call:delete_everything{}<tool_call|>'
        runtime = self.runtime(PREAMBLE + '<|channel>thought\n'+hidden+'<channel|>'+CALL)
        self.assertEqual(runtime.generate([])['tool'],'nas.file_read')
        self.assertNotIn('SECRETO',runtime.last_preamble)
        self.assertEqual(runtime.messages[-1]['reasoning'],hidden)

    def test_initial_and_prefilled_thought_still_work(self):
        self.assertEqual(split_thinking('<|channel>thought\nrazón<channel|>Hola'),('Hola','razón'))
        self.assertEqual(split_thinking('razón<channel|>Hola',True),('Hola','razón'))
        self.assertEqual(split_thinking('Sin canales'),('Sin canales',None))

    def test_empty_thought_blocks_around_the_preamble_are_dropped(self):
        # Salida real (HQS v4 y original BF16): bloque vacío, anuncio, otro bloque vacío.
        empty = '<|channel>thought\n<channel|>'
        raw = empty + empty + 'Voy a leer el siguiente fragmento.\n\n' + empty + CALL
        runtime = self.runtime(raw)
        self.assertEqual(runtime.generate([])['tool'], 'nas.file_read')
        self.assertEqual(runtime.last_preamble, 'Voy a leer el siguiente fragmento.')
        self.assertNotIn('<|channel>', runtime.last_generation['visible_output'])
        self.assertEqual(split_thinking(empty + 'Hola' + empty), ('Hola', ''))

    def test_escaped_media_markers_are_removed_from_a_reply(self):
        runtime = self.runtime('Es un ESP32 montado sobre una placa de<audio|> pruebas.', finish='eos')
        reply = runtime.generate([])['reply']
        self.assertEqual(reply, 'Es un ESP32 montado sobre una placa de pruebas.')
        self.assertNotIn('<audio|>', runtime.messages[-1]['content'])

    def test_do_not_modify_markers_inside_tool_string_arguments(self):
        raw = '<|tool_call>call:nas_file_read{file_id:<|"|>a<|channel>thought\nx<channel|>b<|"|>}<tool_call|>'
        clean,reason=split_thinking(raw)
        self.assertEqual(clean,raw)
        self.assertIsNone(reason)
        self.assertEqual(calls_from_text(clean)[0]['arguments']['file_id'],'a<|channel>thought\nx<channel|>b')

    def test_malformed_channels_and_calls_are_still_rejected_before_queueing(self):
        for raw in (
            PREAMBLE+'<|channel>thought\nunfinished'+CALL,
            PREAMBLE+'<|channel>analysis\nx<channel|>'+CALL,
            PREAMBLE+'<|channel>thought\nx<|channel>thought\ny<channel|>'+CALL,
            PREAMBLE+'<|channel>thought\nx<channel|><|channel>thought\ny<channel|>'+CALL,
            PREAMBLE+'<|channel>thought\n<channel|>'+CALL+' trailing garbage',
            PREAMBLE+'<|channel>thought\n<channel|>'+CALL.replace('offset:4000','offset:4000,offset:1'),
        ):
            with self.subTest(raw=raw):
                runtime=self.runtime(raw)
                with self.assertRaises(NativeSyntax): runtime.generate([])
                self.assertFalse(runtime.pending)
                self.assertIsNone(runtime.current)
                self.assertFalse(any('tool_calls' in m for m in runtime.messages))

    def test_no_reasoning_or_protocol_leaks_at_any_stream_boundary(self):
        raw = PREAMBLE+'<|channel>thought\nSECRETO PRIVADO<channel|>'+CALL
        for end in range(len(raw)+1):
            preview=visible_preview(raw[:end])
            self.assertNotIn('SECRETO',preview)
            self.assertNotIn('<|',preview)
            self.assertNotIn('<channel',preview)
            self.assertNotIn('nas_file_read',preview)
        self.assertEqual(visible_preview(raw),'')

    def test_visible_text_after_thought_without_tool_remains_valid(self):
        runtime=self.runtime('Introducción.<|channel>thought\nrazón<channel|>Conclusión.',finish='eos')
        self.assertEqual(runtime.generate([])['reply'],'Introducción.\nConclusión.')


if __name__=='__main__':unittest.main()
