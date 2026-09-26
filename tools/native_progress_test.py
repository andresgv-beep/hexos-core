"""Transport/agent contracts without GPU or external effects."""
import io
import json
from pathlib import Path
import queue
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.native_transport import NativeTransport, TurnCancelled, visible_preview
from hexos.agent.chat import Agent
from hexos.agent.native import NativeRuntime
from collections import deque


class PreviewTest(unittest.TestCase):
    def test_reset_preserves_this_turn_image_and_text_model_rejects_it(self):
        rt = NativeRuntime.__new__(NativeRuntime)
        rt._transport = SimpleNamespace(model_info={'multimodal': True}, control=lambda _: None)
        rt.messages=[]; rt.pending=deque(); rt.current=None
        rt.attach_image(b'\x00\x00\xff', 1, 1)
        rt.call({'type':'reset'})
        self.assertEqual(rt.pending_image, (b'\x00\x00\xff', 1, 1))
        rt._transport.model_info['multimodal'] = False
        with self.assertRaisesRegex(RuntimeError, 'unsupported_attachment'):
            rt.attach_image(b'\x00\x00\xff', 1, 1)

    def test_thought_and_tools_are_hidden_at_every_fragment_boundary(self):
        thought = '<|channel>thought\nSECRETO<channel|>Hola, mundo.'
        for n in range(len(thought)+1):
            preview = visible_preview(thought[:n])
            self.assertNotIn('SECRETO', preview)
            self.assertNotIn('<', preview)
        self.assertEqual(visible_preview(thought), 'Hola, mundo.')
        for n in range(len('SECRETO<channel|>Hola')+1):
            self.assertNotIn('SECRETO', visible_preview('SECRETO<channel|>Hola'[:n], True))
        call = 'Voy a consultar. <|tool_call>call:note_create{text:<|"|>hola<|"|>}<tool_call|>'
        for n in range(len(call)+1):
            preview = visible_preview(call[:n])
            self.assertNotIn('call:', preview)
            self.assertNotIn('note_create', preview)
            self.assertNotIn('<|', preview)
        self.assertEqual(visible_preview(call), '')

    def test_html_is_text_not_a_hidden_channel(self):
        code = '```html\n<div class="hola">Qué tal</div>\n```'
        self.assertEqual(visible_preview(code), code)

    def test_cancel_target_and_aux_capacity(self):
        tr = NativeTransport.__new__(NativeTransport)
        tr.proc = SimpleNamespace(stdin=io.BytesIO())
        tr.write_lock = threading.Lock(); tr.state_lock = threading.Lock()
        tr.active = 'active'; tr.cancelled = threading.Event(); tr.aux_ready = False
        tr.reset_sessions = set()
        tr.cancel()
        request = json.loads(tr.proc.stdin.getvalue())
        self.assertEqual(request['target'], 'active')
        tr.cancelled.clear(); tr.proc.stdin = io.BytesIO()
        controls = []
        tr.control = lambda obj: controls.append(obj)
        tr.start('prompt', auxiliar=True)
        tr.start('prompt2', auxiliar=True)
        self.assertEqual(controls, [dict(type='session_open', session='aux', max_seq_len=1536)])
        sent = [json.loads(line) for line in tr.proc.stdin.getvalue().splitlines()]
        self.assertTrue(all(r['session'] == 'aux' for r in sent))
        self.assertFalse(sent[0]['generation']['close_turn'])
        self.assertTrue(sent[0]['generation']['reuse_prefix'])

    def test_visual_turn_drops_attachment_and_rebuilds_next_text_prompt(self):
        tr = NativeTransport.__new__(NativeTransport)
        tr.proc = SimpleNamespace(stdin=io.BytesIO())
        tr.write_lock = threading.Lock(); tr.state_lock = threading.Lock()
        tr.cancelled = threading.Event(); tr.reset_sessions = set()
        tr.pending = ('visual', '0', ['image']); tr.active = 'visual'
        controls = []
        tr.control = lambda obj: controls.append(obj)
        tr.receive = lambda: dict(type='completed', request_id='visual')
        tr.finish()
        tr.start('full history without image markers')
        tr.start('next text turn')
        self.assertEqual(controls, [dict(type='attachment_drop', attachment_id='image'),
                                    dict(type='reset', session='0')])
        self.assertFalse(tr.reset_sessions)


class FakeRuntime:
    progressive = True
    native = False
    def __init__(self):
        self.entered = threading.Event(); self.cancelled = threading.Event()
        self.resets = 0; self.calls = 0
    def begin_request(self, callback):
        self.on_update = callback; self.cancelled.clear()
    def call(self, request):
        self.resets += 1
        return {'ok': True}
    def cancel(self):
        self.cancelled.set()
    def generate(self, messages):
        self.calls += 1
        if self.calls > 1:
            return {'reply':'Seguimos.', 'work':None}
        self.on_update(dict(phase='generating', text='Un texto parcial'))
        self.entered.set()
        if not self.cancelled.wait(5):
            raise RuntimeError('test cancellation timeout')
        raise TurnCancelled('cancelled')


class AgentTest(unittest.TestCase):
    def test_cancel_archives_partial_and_next_chat_works(self):
        with tempfile.TemporaryDirectory() as workspace:
            rt = FakeRuntime(); agent = Agent(workspace, rt)
            replies = queue.Queue()
            def worker():
                try: replies.put(agent.chat('Escribe un cuento.', request_id='one'))
                except Exception as exc: replies.put(exc)
            thread = threading.Thread(target=worker); thread.start()
            self.assertTrue(rt.entered.wait(5))
            self.assertEqual(agent.generation_snapshot()['text'], 'Un texto parcial')
            self.assertFalse(agent.cancel_generation('other')['ok'])
            self.assertFalse(rt.cancelled.is_set())
            self.assertTrue(agent.cancel_generation('one')['ok'])
            thread.join(5)
            result = replies.get(timeout=1)
            if isinstance(result, Exception): raise result
            self.assertTrue(result['cancelled'])
            self.assertIn('interrumpida', result['reply'])
            self.assertIsNone(agent.generation_snapshot())
            with agent.store() as store:
                rows = store.db.execute('SELECT text FROM conversation ORDER BY rowid').fetchall()
                self.assertEqual(len(rows), 2)
                self.assertIn('Un texto parcial', rows[-1][0])
            self.assertEqual(agent.chat('Hola de nuevo.', request_id='two')['reply'], 'Seguimos.')


if __name__ == '__main__': unittest.main()
