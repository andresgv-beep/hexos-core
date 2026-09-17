"""Pruebas de la frontera web: contrato, aislamiento y lectura acotada."""
from email.message import Message
from pathlib import Path
import io
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent import catalog, web
from hexos.agent.chat import Agent
from hexos.agent.chat_backend.state import AgentDependencies


class FakeRuntime:
    def call(self, request):
        return {'ok': True}

    def generate(self, messages):
        return {'reply': 'ok', 'work': None}


class ScriptedRuntime(FakeRuntime):
    native = False

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.prompts = []

    def generate(self, messages):
        self.prompts.append(messages)
        return self.outputs.pop(0)


class Response(io.BytesIO):
    def __init__(self, body, url='https://example.com/page', content_type='text/html; charset=utf-8'):
        super().__init__(body.encode())
        self.url = url
        self.headers = Message()
        self.headers['Content-Type'] = content_type

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Opener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def open(self, request, timeout=0):
        self.requests.append((request.full_url, timeout))
        return self.response


def public_resolver(host, port):
    return [(2, 1, 6, '', ('93.184.216.34', port))]


class WebBoundaryTest(unittest.TestCase):
    def test_catalogo_expone_dos_lecturas_sin_escritura(self):
        self.assertEqual(catalog.TOOLS['web.search']['effect'], 'read')
        self.assertEqual(catalog.TOOLS['web.read']['effect'], 'read')

    def test_search_parsea_resultados_sin_abrirlos(self):
        html = '''<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdoc">Documento oficial</a><a class="result__snippet">Resumen útil.</a></div>'''
        result = web.search('prueba', opener=Opener(Response(html)), limit=1)
        self.assertEqual(result['items'], [{'title':'Documento oficial',
                                           'url':'https://example.com/doc',
                                           'snippet':'Resumen útil.'}])

    def test_read_extrae_texto_y_elimina_scripts(self):
        page = '<html><head><title>Fuente</title><script>robar()</script></head><body><h1>Dato</h1><p>Contenido verificable.</p></body></html>'
        result = web.read('https://example.com/page', opener=Opener(Response(page)),
                          resolver=public_resolver)
        self.assertEqual(result['title'], 'Fuente')
        self.assertIn('Contenido verificable.', result['text'])
        self.assertNotIn('robar', result['text'])

    def test_read_rechaza_vias_hacia_la_red_privada(self):
        cases = ('file:///etc/passwd', 'http://127.0.0.1/', 'http://192.168.1.10/',
                 'http://user:pass@example.com/', 'https://example.com:8443/')
        for url in cases:
            with self.subTest(url=url), self.assertRaises(ValueError):
                web.read(url)

    def test_redireccion_final_privada_tambien_se_rechaza(self):
        opener = Opener(Response('<p>x</p>', url='http://127.0.0.1/private'))
        with self.assertRaisesRegex(ValueError, 'redes privadas'):
            web.read('https://example.com/', opener=opener, resolver=public_resolver)

    def test_dispatch_usa_dependencias_sin_tocar_workspace(self):
        calls = []
        dependencies = AgentDependencies(
            nas_read=lambda *a, **k: None,
            web_search=lambda query, limit=5: calls.append(('search', query, limit)) or {'items':[]},
            web_read=lambda url: calls.append(('read', url)) or {'text':'dato'})
        with tempfile.TemporaryDirectory(prefix='hexos-web-test-') as tmp:
            agent = Agent(tmp, FakeRuntime(), dependencies=dependencies)
            with agent.store() as store:
                self.assertEqual(agent.tool(store, 'web.search', {'query':'hoy','limit':3}), {'items':[]})
                self.assertEqual(agent.tool(store, 'web.read', {'url':'https://example.com'}), {'text':'dato'})
                self.assertEqual(store.db.execute('select count(*) from network_devices').fetchone()[0], 0)
        self.assertEqual(calls, [('search','hoy',3), ('read','https://example.com')])

    def test_buscar_no_puede_cerrar_sin_leer_y_la_fuente_se_hace_visible(self):
        runtime = ScriptedRuntime([
            {'tool':'web.search', 'arguments':{'query':'dato actual'}},
            {'reply':'El buscador dice que ocurrió.', 'work':None},
            {'tool':'web.read', 'arguments':{'url':'https://example.com/source'}},
            {'reply':'La fuente confirma el dato.', 'work':None},
        ])
        dependencies = AgentDependencies(
            nas_read=lambda *a, **k: None,
            web_search=lambda query, limit=5: {'items':[{'url':'https://example.com/source'}]},
            web_read=lambda url: {'url':url, 'title':'Fuente', 'text':'Dato confirmado.'})
        with tempfile.TemporaryDirectory(prefix='hexos-web-cycle-') as tmp:
            result = Agent(tmp, runtime, dependencies=dependencies).chat('Busca información actual')
        self.assertEqual([step['tool'] for step in result['tools']], ['web.search','web.read'])
        self.assertIn('Fuentes consultadas:', result['reply'])
        self.assertIn('https://example.com/source', result['reply'])
        self.assertTrue(any('solo has visto fragmentos' in message[0]['content']
                            for message in runtime.prompts if message and message[0]['role'] == 'user'))


if __name__ == '__main__':
    unittest.main()
