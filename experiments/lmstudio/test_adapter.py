import json
import tempfile
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from experiments.lmstudio.adapter import Runtime
from hexos.agent.chat import Agent
from hexos.agent.decisions import InvalidDecision


def answer(content='', calls=None, finish='stop'):
    return {'choices': [{'finish_reason': finish, 'message': {
        'role': 'assistant', 'content': content, 'tool_calls': calls or []}}]}


def call(identifier='a', name='history_recent', arguments='{}'):
    return {'id': identifier, 'type': 'function', 'function': {'name': name, 'arguments': arguments}}


class Tests(unittest.TestCase):
    def test_agent_executes_then_returns_results_and_progress(self):
        runtime = Runtime('http://127.0.0.1:1234/v1', 'test')
        sent = []
        responses = iter([answer('Voy a consultar el historial.', [call(), call('b', 'device_list')], 'tool_calls'), answer('Consulta completada.')])
        def request(path, payload):
            sent.append(json.loads(json.dumps(payload)))
            return next(responses)
        runtime.request = request
        with tempfile.TemporaryDirectory() as tmp:
            result = Agent(tmp, runtime).chat('Consulta historial e inventario.')
        self.assertEqual(result['reply'], 'Consulta completada.')
        self.assertEqual([t['tool'] for t in result['tools']], ['history.recent', 'device.list'])
        self.assertEqual(result['progress']['messages'][0]['text'], 'Voy a consultar el historial.')
        self.assertEqual([m['tool_call_id'] for m in sent[1]['messages'] if m['role'] == 'tool'], ['a', 'b'])

    def test_invalid_second_call_prevents_first_execution(self):
        runtime = Runtime('http://localhost:1234/v1', 'test')
        runtime.request = lambda *a: answer(calls=[call(), call('b', 'unknown')], finish='tool_calls')
        with self.assertRaises(InvalidDecision):
            runtime.generate([{'role': 'user', 'content': 'consulta'}])
        self.assertFalse(runtime.pending)
        self.assertIsNone(runtime.current)

    def test_truncation_and_duplicate_ids_are_rejected(self):
        for response in [answer(calls=[call()], finish='length'), answer(calls=[call(), call()], finish='tool_calls')]:
            runtime = Runtime('http://localhost:1234/v1', 'test')
            runtime.request = lambda *a: response
            with self.assertRaises((RuntimeError, InvalidDecision)):
                runtime.generate([{'role': 'user', 'content': 'consulta'}])
            self.assertFalse(runtime.pending)

    def test_history_and_reset(self):
        runtime = Runtime('http://localhost:1234/v1', 'test')
        history = runtime.history([{'role': 'assistant', 'tool_calls': [{'function': {'name': 'device_list', 'arguments': {}}}],
                                    'tool_responses': [{'name': 'device_list', 'response': {'devices': []}}]}])
        self.assertEqual(history[0]['tool_calls'][0]['id'], history[1]['tool_call_id'])
        runtime.messages = history
        runtime.call({'type': 'reset'})
        self.assertEqual(runtime.messages, [])

    def test_http_roundtrip(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                raw = json.dumps(answer('Hola.')).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            runtime = Runtime(f'http://127.0.0.1:{server.server_port}/v1', 'test-model')
            result = runtime.generate([{'role': 'user', 'content': 'Hola'}])
            self.assertEqual(result['reply'], 'Hola.')
            self.assertEqual(received[0]['model'], 'test-model')
            self.assertTrue(received[0]['tools'])
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_nas_bridge_is_explicit_and_keeps_workspace_separate(self):
        from experiments.lmstudio.run import ExperimentAgent, ROOT
        runtime = Runtime('http://localhost:1234/v1', 'test')
        with tempfile.TemporaryDirectory() as tmp:
            agent = ExperimentAgent(tmp, runtime, nas_session=True)
            with patch('experiments.lmstudio.run.nas_read', return_value={'ok': True}) as read:
                with agent.store() as store:
                    self.assertEqual(agent.tool(store, 'nas.read', {'section': 'diagnosis'}), {'ok': True})
                    with self.assertRaises(ValueError):
                        agent.tool(store, 'nas.read', {'section': 'diagnosis', 'host': 'other'})
                read.assert_called_once_with(str(ROOT / 'runtime/workspace'), section='diagnosis')
            agent = ExperimentAgent(tmp, runtime)
            with patch('hexos.agent.chat.nas_read', return_value={}) as read:
                with agent.store() as store:
                    agent.tool(store, 'nas.read', {'section': 'system'})
                read.assert_called_once_with(agent.workspace, section='system')

    def test_remote_endpoint_rejected(self):
        for url in ['https://example.com/v1', 'http://192.168.1.243/v1', 'http://u:p@localhost/v1']:
            with self.assertRaises(ValueError):
                Runtime(url, 'test')


if __name__ == '__main__':
    unittest.main()
