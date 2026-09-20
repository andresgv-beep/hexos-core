"""Read-before-answer guidance without network, GPU or production data."""
from collections import deque
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from hexos.agent.native import NativeRuntime, NativeSyntax
from hexos.agent.native_transport import visible_preview
from hexos.agent.chat_backend.recovery import RecoveryController
from hexos.agent.chat_backend.state import TurnState


class GuidanceTest(unittest.TestCase):
    def runtime(self, completion):
        rt = NativeRuntime.__new__(NativeRuntime)
        rt.names = {'web_read': 'web.read', 'note_save': 'note.save'}
        rt.tools = [{'name': 'unchanged catalog'}]
        rt.pending = deque()
        rt.messages = []
        rt.template = SimpleNamespace(render=Mock(return_value='stable prompt'))
        rt.send = lambda prompt, image: prompt.encode()
        rt.event = lambda: (['0', '1', '1', '1', 'stop'], completion)
        rt.notify = Mock()
        return rt

    def test_native_prefix_is_hidden_preserves_catalog_and_is_one_shot(self):
        rt = self.runtime('{url:<|"|>https://example.org/<|"|>}<tool_call|>')
        self.assertTrue(rt.require_read('web.read'))
        result = rt.generate([{'role':'user', 'content':'consulta'}])
        self.assertEqual(result, {'tool':'web.read', 'arguments':{'url':'https://example.org/'}})
        self.assertIs(rt.template.render.call_args.kwargs['tools'], rt.tools)
        self.assertIsNone(rt._required_read)
        raw = rt.last_generation['raw']
        for end in range(len(raw)+1):
            self.assertEqual(visible_preview(raw[:end]), '')
        rt.tool_result({'text':'fuente'})
        rt.event = lambda: (['0','1','1','0','eos'], 'Respuesta final.')
        self.assertEqual(rt.generate([])['reply'], 'Respuesta final.')
        self.assertEqual(rt._completion_prefix, '')

    def test_cannot_require_write_or_append_extra_calls(self):
        rt = self.runtime('{url:<|"|>https://example.org/<|"|>}<tool_call|>'
            '<|tool_call>call:note_save{title:<|"|>x<|"|>}<tool_call|>')
        with self.assertRaises(ValueError): rt.require_read('note.save')
        rt.require_read('web.read')
        with self.assertRaises(NativeSyntax): rt.generate([])
        self.assertFalse(rt.pending)

    def run_gate(self, trace, guided=False, native=True):
        rt = SimpleNamespace(require_read=Mock(return_value=True),
            generate=Mock(return_value={'reply':'Respuesta.'}))
        turn = TurnState('consulta', native=native, trace=trace)
        turn.retries.web_read_guided = guided
        RecoveryController(SimpleNamespace(runtime=rt)).generate(None, turn)
        return rt, turn

    def test_search_guides_once_but_empty_failed_or_read_does_not(self):
        search = {'tool':'web.search', 'result':{'items':[{'url':'https://example.org/'}]}}
        rt, turn = self.run_gate([search])
        rt.require_read.assert_called_once_with('web.read')
        self.assertTrue(turn.retries.web_read_guided)
        for trace, guided, native in [([],False,True), ([search],True,True),
                ([search],False,False), ([dict(search,failed=True)],False,True),
                ([{'tool':'web.search','result':{'items':[]}}],False,True),
                ([search,{'tool':'web.read','failed':True}],False,True),
                ([search,{'tool':'web.read','result':{'text':'ok'}}],False,True)]:
            with self.subTest(trace=trace,guided=guided,native=native):
                rt,_ = self.run_gate(trace,guided,native)
                rt.require_read.assert_not_called()


if __name__ == '__main__': unittest.main()
