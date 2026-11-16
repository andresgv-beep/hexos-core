"""Ajustes de la interfaz: claves de servicios, Tavily en web.search y freno de búsquedas.

Sin red ni GPU. Reproduce el turno del 16/11: DuckDuckGo contestó con su reto antibots
y el 26B lanzó ocho consultas distintas en diez segundos contra el mismo bloqueo.
"""
from email.message import Message
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
import io
import json
import stat
import sys
import tempfile
import threading
import unittest
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent import ajustes, web
from hexos.agent.chat import Agent
from hexos.agent.chat_backend.server import make_handler
from hexos.agent.chat_backend.state import AgentDependencies

CLAVE = 'tvly-prueba-0123456789abcd'
RETO = ('<html><body><form id="challenge-form"><div class="anomaly-modal__title">Unfortunately, '
        'bots use DuckDuckGo too.</div></form></body></html>')
TAVILY = {'query': 'apple 1', 'results': [
    {'title': ' Apple-1  schematics ', 'url': 'https://archive.org/details/apple1', 'content': 'Esquemas\ndel Apple 1.',
     'score': 0.9},
    {'title': 'Sin dirección válida', 'url': 'javascript:alert(1)', 'content': 'x'},
    {'title': 'Bitsavers', 'url': 'http://bitsavers.org/pdf/apple/', 'content': 'y' * 2000}]}


class Response(io.BytesIO):
    def __init__(self, body):
        super().__init__(body.encode())
        self.headers = Message()
        self.headers['Content-Type'] = 'text/html; charset=utf-8'

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Opener:
    """Devuelve una respuesta fija, o lanza el HTTPError que se le dé."""
    def __init__(self, body=None, status=None):
        self.body, self.status, self.requests = body, status, []

    def open(self, request, timeout=0):
        self.requests.append(request)
        if self.status:
            raise HTTPError(request.full_url, self.status, 'error', Message(), io.BytesIO(b'{}'))
        return Response(self.body)


class ScriptedRuntime:
    native = False

    def __init__(self, outputs):
        self.outputs = list(outputs)

    def call(self, request):
        return {'ok': True}

    def generate(self, messages):
        # La respuesta final se repite si un aviso de HexOS pide otra generación.
        return self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]


class ClavesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-ajustes-')
        self.casa = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sin_clave_se_busca_con_duckduckgo(self):
        estado = ajustes.listado(self.casa)
        self.assertEqual(estado['web']['search'], 'DuckDuckGo')
        self.assertEqual([(p['id'], p['configured'], p['hint']) for p in estado['web']['providers']],
                         [('tavily', False, None)])
        self.assertIsNone(ajustes.buscador(self.casa))

    def test_guardar_no_devuelve_la_clave_y_el_fichero_es_privado(self):
        estado = ajustes.guardar(self.casa, 'tavily', '  ' + CLAVE + '\n')
        self.assertNotIn(CLAVE, json.dumps(estado))
        self.assertEqual(estado['web']['search'], 'Tavily')
        self.assertEqual((estado['web']['providers'][0]['configured'], estado['web']['providers'][0]['hint']),
                         (True, '…abcd'))
        self.assertEqual(stat.S_IMODE(ajustes.keys_path(self.casa).stat().st_mode), 0o600)
        self.assertEqual(ajustes.buscador(self.casa), {'id': 'tavily', 'key': CLAVE})

    def test_quitar_vuelve_a_duckduckgo(self):
        ajustes.guardar(self.casa, 'tavily', CLAVE)
        self.assertEqual(ajustes.guardar(self.casa, 'tavily', None)['web']['search'], 'DuckDuckGo')
        self.assertIsNone(ajustes.clave(self.casa, 'tavily'))

    def test_rechaza_lo_que_no_es_una_clave_ni_un_servicio(self):
        for mala in ('', 'corta', 'con espacios dentro de la clave', 'salto\nde-linea-0000', 7, {'a': 1}):
            with self.assertRaises(ValueError):
                ajustes.guardar(self.casa, 'tavily', mala)
        with self.assertRaises(ValueError):
            ajustes.guardar(self.casa, 'otro', CLAVE)
        with self.assertRaises(ValueError) as fallo:
            ajustes.guardar(self.casa, 'tavily', '7ABCdEfgh1JKlM2N3OpQrstuVW4xY56ZaBcDefGHijK7')
        self.assertIn('empiezan por «tvly-»', str(fallo.exception))
        self.assertFalse(ajustes.keys_path(self.casa).exists())

    def test_un_fichero_legible_por_otros_no_se_usa(self):
        ajustes.guardar(self.casa, 'tavily', CLAVE)
        ajustes.keys_path(self.casa).chmod(0o644)
        with self.assertRaises(ValueError):
            ajustes.buscador(self.casa)

    def test_probar_hace_una_busqueda_con_la_clave_guardada(self):
        with self.assertRaises(ValueError):
            ajustes.probar(self.casa, 'tavily', web.search)
        ajustes.guardar(self.casa, 'tavily', CLAVE)
        visto = []
        salida = ajustes.probar(self.casa, 'tavily',
                                lambda query, limit, proveedor: visto.append(proveedor) or {'count': 1})
        self.assertEqual((salida, visto), ({'ok': True, 'provider': 'tavily', 'results': 1},
                                           [{'id': 'tavily', 'key': CLAVE}]))
        with self.assertRaises(ValueError) as fallo:
            ajustes.probar(self.casa, 'tavily', lambda query, limit, proveedor: web.search(
                query, opener=Opener(status=401), limit=limit, proveedor=proveedor))
        self.assertEqual(str(fallo.exception), 'la clave de Tavily no es válida')


class BuscadoresTest(unittest.TestCase):
    PROVEEDOR = {'id': 'tavily', 'key': CLAVE}

    def test_tavily_va_por_su_api_con_la_clave_en_la_cabecera(self):
        opener = Opener(json.dumps(TAVILY))
        salida = web.search('apple 1', opener=opener, limit=5, recency='mes', proveedor=self.PROVEEDOR)
        pedido = opener.requests[0]
        self.assertEqual(pedido.full_url, 'https://api.tavily.com/search')
        self.assertEqual(pedido.get_header('Authorization'), 'Bearer ' + CLAVE)
        self.assertEqual(json.loads(pedido.data), {'query': 'apple 1', 'max_results': 5,
                                                   'search_depth': 'basic', 'time_range': 'month'})
        self.assertEqual(salida['items'][0], {'title': 'Apple-1 schematics',
                                              'url': 'https://archive.org/details/apple1',
                                              'snippet': 'Esquemas del Apple 1.'})
        self.assertEqual([i['url'] for i in salida['items']],
                         ['https://archive.org/details/apple1', 'http://bitsavers.org/pdf/apple/'])
        self.assertEqual(len(salida['items'][1]['snippet']), web.MAX_SNIPPET)
        self.assertNotIn(CLAVE, json.dumps(salida))

    def test_los_fallos_de_tavily_dicen_la_causa_y_no_llevan_la_clave(self):
        for estado, texto in ((401, 'no es válida'), (432, 'cupo'), (429, 'ritmo')):
            with self.assertRaises(ValueError) as fallo:
                web.search('x', opener=Opener(status=estado), proveedor=self.PROVEEDOR)
            self.assertIn(texto, str(fallo.exception))
            self.assertIn(web.SIN_REINTENTO, str(fallo.exception))
            self.assertNotIn(CLAVE, str(fallo.exception))
        with self.assertRaises(ValueError) as fallo:
            web.search('x', opener=Opener(status=500), proveedor=self.PROVEEDOR)
        self.assertNotIn(web.SIN_REINTENTO, str(fallo.exception))
        with self.assertRaises(ValueError):
            web.search('x', opener=Opener('<html>no es json</html>'), proveedor=self.PROVEEDOR)
        with self.assertRaises(ValueError):
            web.search('x', proveedor={'id': 'otro', 'key': CLAVE})

    def test_el_reto_antibots_de_duckduckgo_se_dice_como_bloqueo(self):
        with self.assertRaises(ValueError) as fallo:
            web.search('Apple 1 schematics electrical diagrams', opener=Opener(RETO))
        self.assertIn('reto antibots', str(fallo.exception))
        self.assertIn(web.SIN_REINTENTO, str(fallo.exception))

    def test_una_busqueda_vacia_sin_reto_no_es_un_bloqueo(self):
        with self.assertRaises(ValueError) as fallo:
            web.search('anomaly-modal', opener=Opener('<html><body>No results.</body></html>'))
        self.assertNotIn(web.SIN_REINTENTO, str(fallo.exception))


class TurnoTest(unittest.TestCase):
    def chat(self, outputs, search, clave=None):
        with tempfile.TemporaryDirectory(prefix='hexos-ajustes-turno-') as tmp:
            if clave:
                ajustes.guardar(tmp, 'tavily', clave)
            agente = Agent(tmp, ScriptedRuntime(outputs), dependencies=AgentDependencies(
                nas_read=lambda *a, **k: None, web_search=search, web_read=lambda url: {'text': 'dato'}))
            return agente.chat('podrías buscar los planos del Apple 1 por archives?')

    def test_turno_del_16_11_el_bloqueo_corta_las_busquedas_siguientes(self):
        salidas = []

        def bloqueado(query, limit=5):
            salidas.append(query)
            return web.search(query, opener=Opener(RETO), limit=limit)

        resultado = self.chat([
            {'tool': 'web.search', 'arguments': {'query': 'Apple 1 blueprints and electrical schematics archive'}},
            {'tool': 'web.search', 'arguments': {'query': 'Apple 1 schematics and blueprints download PDF'}},
            {'tool': 'web.search', 'arguments': {'query': 'Apple 1 schematics bitsavers.org'}},
            {'reply': 'El buscador está bloqueado.', 'work': None}], bloqueado)
        self.assertEqual(len(salidas), 1, 'solo la primera búsqueda sale a la red')
        errores = [paso['result']['error'] for paso in resultado['tools'] if paso.get('failed')]
        self.assertEqual(len(errores), 3)
        self.assertIn('reto antibots', errores[0])
        for repetida in errores[1:]:
            self.assertIn('No se ha buscado otra vez', repetida)
            self.assertIn('reto antibots', repetida)

    def test_un_fallo_que_depende_de_la_consulta_si_deja_buscar_otra_vez(self):
        salidas = []

        def vacia(query, limit=5):
            salidas.append(query)
            raise ValueError('el buscador no devolvió resultados legibles')

        self.chat([{'tool': 'web.search', 'arguments': {'query': 'uno'}},
                   {'tool': 'web.search', 'arguments': {'query': 'dos'}},
                   {'reply': 'Nada.', 'work': None}], vacia)
        self.assertEqual(salidas, ['uno', 'dos'])

    def test_con_clave_la_busqueda_recibe_el_proveedor_y_el_modelo_no_la_ve(self):
        visto = []

        def buscar(query, limit=5, proveedor=None):
            visto.append(proveedor)
            return {'items': [{'url': 'https://archive.org/details/apple1', 'title': 'Apple 1', 'snippet': 'x'}],
                    'count': 1}

        resultado = self.chat([{'tool': 'web.search', 'arguments': {'query': 'apple 1'}},
                               {'tool': 'web.read', 'arguments': {'url': 'https://archive.org/details/apple1'}},
                               {'reply': 'Está en archive.org.', 'work': None}], buscar, clave=CLAVE)
        self.assertEqual(visto, [{'id': 'tavily', 'key': CLAVE}])
        self.assertNotIn(CLAVE, json.dumps(resultado, ensure_ascii=False, default=str))


class ServidorTest(unittest.TestCase):
    ORIGEN = 'http://127.0.0.1:3000'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-ajustes-http-')
        self.casa = Path(self.tmp.name)
        ui = self.casa / 'ui.html'
        ui.write_text('x')
        self.buscado = []
        agente = Agent(self.casa, ScriptedRuntime([]), dependencies=AgentDependencies(
            nas_read=lambda *a, **k: None,
            web_search=lambda query, limit=5, proveedor=None: self.buscado.append(proveedor) or {'count': 1}))
        self.servidor = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(agente, lambda: {}, {self.ORIGEN}, ui))
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.url = 'http://127.0.0.1:%d' % self.servidor.server_address[1]

    def tearDown(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.tmp.cleanup()

    def pedir(self, ruta, cuerpo=None, origen=ORIGEN):
        cabeceras = {'Content-Type': 'application/json', 'Origin': origen} if cuerpo is not None else {}
        pedido = urllib.request.Request(self.url + ruta, headers=cabeceras,
                                        data=None if cuerpo is None else json.dumps(cuerpo).encode())
        try:
            with urllib.request.urlopen(pedido, timeout=10) as r:
                return r.status, r.read().decode()
        except HTTPError as error:
            with error:
                return error.code, error.read().decode()

    def test_guardar_probar_y_quitar_por_http_sin_que_la_clave_vuelva(self):
        codigo, texto = self.pedir('/api/settings')
        self.assertEqual((codigo, json.loads(texto)['web']['search']), (200, 'DuckDuckGo'))

        codigo, texto = self.pedir('/api/settings/web', {'provider': 'tavily', 'key': CLAVE})
        self.assertEqual((codigo, json.loads(texto)['web']['search']), (200, 'Tavily'))
        self.assertNotIn(CLAVE, texto)
        self.assertNotIn(CLAVE, self.pedir('/api/settings')[1])

        codigo, texto = self.pedir('/api/settings/web/test', {'provider': 'tavily'})
        self.assertEqual((codigo, json.loads(texto)['ok']), (200, True))
        self.assertEqual(self.buscado, [{'id': 'tavily', 'key': CLAVE}])

        codigo, texto = self.pedir('/api/settings/web', {'provider': 'tavily', 'key': None})
        self.assertEqual((codigo, json.loads(texto)['web']['search']), (200, 'DuckDuckGo'))
        self.assertEqual(self.pedir('/api/settings/web/test', {'provider': 'tavily'})[0], 409)

    def test_rechaza_otro_origen_y_cuerpos_mal_formados(self):
        self.assertEqual(self.pedir('/api/settings/web', {'provider': 'tavily', 'key': CLAVE},
                                    origen='https://otra.example')[0], 403)
        self.assertEqual(self.pedir('/api/settings/web', {'provider': 'tavily'})[0], 409)
        self.assertEqual(self.pedir('/api/settings/web', {'provider': 'otro', 'key': CLAVE})[0], 409)
        self.assertEqual(self.pedir('/api/settings/web', {'provider': 'tavily', 'key': 'corta'})[0], 409)
        self.assertEqual(self.pedir('/api/settings/web', {'provider': 'tavily', 'key': 'sk-otra-clave-0123456789'})[0], 409)
        self.assertFalse(ajustes.keys_path(self.casa).exists())


if __name__ == '__main__':
    unittest.main()
