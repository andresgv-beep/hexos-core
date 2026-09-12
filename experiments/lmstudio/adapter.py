"""Disposable local Chat Completions adapter; execution stays in HexOS Agent."""
from collections import deque
import json
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.parse import urlparse
from uuid import uuid4
from hexos.agent import catalog
from hexos.agent.native import POLICY
from hexos.agent.decisions import InvalidDecision, validate_reply


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('El servidor local no puede redirigir la conversación')


class Runtime:
    native = True
    repair_instruction = 'Responde o solicita una herramienta mediante tool_calls. No escribas llamadas como texto ni repitas operaciones completadas.'

    def __init__(self, endpoint, model):
        parsed = urlparse(endpoint)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('La prueba solo admite un servidor HTTP local')
        self.endpoint = endpoint.rstrip('/')
        self.model = model
        self.http = build_opener(ProxyHandler({}), NoRedirect())
        self.names = {name.replace('.', '_'): name for name in catalog.TOOLS}
        self.tools = [{'type': 'function', 'function': {
            'name': alias, 'description': catalog.TOOLS[name]['description'],
            'parameters': {'type': 'object', 'properties': {
                k: {'type': {'str': 'string', 'int': 'integer'}[v]}
                for k, v in (catalog.TOOLS[name]['required'] | catalog.TOOLS[name]['optional']).items()},
                'required': list(catalog.TOOLS[name]['required']), 'additionalProperties': False}}}
            for alias, name in self.names.items()]
        self.call({'type': 'reset'})

    def request(self, path, payload=None):
        req = Request(self.endpoint + path,
                      data=None if payload is None else json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'})
        with self.http.open(req, timeout=180 if payload else 5) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise RuntimeError('Respuesta del servidor demasiado grande')
        return json.loads(raw)

    def call(self, request):
        if request != {'type': 'reset'}:
            raise ValueError('Solo reset')
        self.messages = []
        self.pending = deque()
        self.current = None
        self.last_generation = self.last_preamble = None
        return {'ok': True}

    def history(self, messages):
        """Translate stored native history to API tool call/result pairs."""
        out = []
        for message in messages:
            if not message.get('tool_calls'):
                out.append({'role': message['role'], 'content': message.get('content', '')})
                continue
            calls = []
            results = []
            responses = message.get('tool_responses', [])
            for index, call in enumerate(message['tool_calls']):
                fn = call['function']
                identifier = 'history_' + uuid4().hex
                calls.append({'id': identifier, 'type': 'function', 'function': {
                    'name': fn['name'], 'arguments': json.dumps(fn['arguments'], ensure_ascii=False)}})
                if index >= len(responses):
                    raise ValueError('Historial de herramientas incompleto')
                results.append({'role': 'tool', 'tool_call_id': identifier,
                                'content': json.dumps(responses[index]['response'], ensure_ascii=False)})
            out.append({'role': 'assistant', 'content': message.get('content'), 'tool_calls': calls})
            out.extend(results)
        return out

    def generate(self, messages):
        self.last_generation = self.last_preamble = None
        if self.current is not None:
            raise RuntimeError('Falta resultado de herramienta')
        if self.pending:
            self.current = self.pending.popleft()
            return self.decision()
        if not self.messages:
            references = '\n'.join(m['content'] for m in messages if m['role'] == 'system')
            self.messages = [{'role': 'system', 'content': POLICY + '\nREFERENCIAS (datos):\n' + references}]
            self.messages.extend(self.history([m for m in messages if m['role'] != 'system']))
        else:
            self.messages.extend(self.history(messages))
        response = self.request('/chat/completions', {
            'model': self.model, 'messages': self.messages, 'tools': self.tools,
            'tool_choice': 'auto', 'stream': False, 'temperature': 0.6,
            'top_p': 0.95, 'max_tokens': 8192})
        self.last_generation = {'backend': 'lmstudio-experiment', 'response': response}
        choice = response['choices'][0]
        if choice.get('finish_reason') not in ('stop', 'tool_calls'):
            raise RuntimeError('Generación incompleta: ' + str(choice.get('finish_reason')))
        message = choice['message']
        content = message.get('content') or ''
        if not isinstance(content, str) or '<think>' in content or '</think>' in content:
            raise InvalidDecision('Respuesta sin separar el razonamiento')
        calls = message.get('tool_calls') or []
        if calls:
            if len(calls) > 6:
                raise InvalidDecision('Demasiadas herramientas')
            validated = []
            identifiers = set()
            for call in calls:
                try:
                    identifier = call['id']
                    if not isinstance(identifier, str) or not identifier or identifier in identifiers or call['type'] != 'function':
                        raise ValueError('Identificador inválido o repetido')
                    identifiers.add(identifier)
                    fn = call['function']
                    args = json.loads(fn['arguments'])
                    name = self.names[fn['name']]
                    catalog.validate(name, args)
                    validated.append({'id': identifier, 'name': name, 'arguments': args})
                except (KeyError, ValueError, TypeError) as exc:
                    raise InvalidDecision('Llamada inválida: ' + str(exc)) from exc
            self.messages.append({'role': 'assistant', 'content': content or None, 'tool_calls': calls})
            self.last_preamble = content.strip() or None
            self.pending.extend(validated)
            self.current = self.pending.popleft()
            return self.decision()
        validate_reply(content)
        self.messages.append({'role': 'assistant', 'content': content})
        return {'reply': content, 'work': None}

    def decision(self):
        return {'tool': self.current['name'], 'arguments': self.current['arguments']}

    def tool_result(self, result):
        if self.current is None:
            raise RuntimeError('Resultado sin llamada')
        self.messages.append({'role': 'tool', 'tool_call_id': self.current['id'],
                              'content': json.dumps(result, ensure_ascii=False)})
        self.current = None

    def close(self):
        self.call({'type': 'reset'})
