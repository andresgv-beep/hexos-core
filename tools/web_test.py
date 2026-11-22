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
    def test_url_con_titulo_es_un_error_de_lectura_antes_de_salir_a_la_red(self):
        from unittest.mock import Mock
        resolver = Mock()
        with self.assertRaisesRegex(ValueError, 'dirección exacta'):
            web.read('https://versus.com/en/intel-n100: What is the difference?', resolver=resolver)
        resolver.assert_not_called()

    def test_enlace_del_buscador_conserva_los_espacios_codificados(self):
        url = web._duck_url('//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdos%2520palabras')
        self.assertEqual(url, 'https://example.com/dos%20palabras')

    def test_catalogo_expone_dos_lecturas_sin_escritura(self):
        self.assertEqual(catalog.TOOLS['web.search']['effect'], 'read')
        self.assertEqual(catalog.TOOLS['web.read']['effect'], 'read')

    def test_search_parsea_resultados_sin_abrirlos(self):
        html = '''<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdoc">Documento oficial</a><a class="result__snippet">Resumen útil.</a></div>'''
        result = web.search('prueba', opener=Opener(Response(html)), limit=1)
        self.assertEqual(result['items'], [{'title':'Documento oficial',
                                           'url':'https://example.com/doc',
                                           'snippet':'Resumen útil.'}])

    def test_search_quita_anuncios_y_da_la_fecha_de_hoy(self):
        from datetime import date
        html = ('<div class="result result--ad"><a class="result__a" href="https://duckduckgo.com/y.js?'
                'ad_domain=tienda.com&u3=x">Apple iPhone 14</a><a class="result__snippet">Oferta.</a></div>'
                '<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2F'
                'www.apple.com%2Fes%2Fiphone%2F">iPhone - Apple</a><a class="result__snippet">iPhone 18 Pro.</a></div>')
        result = web.search('último iphone', opener=Opener(Response(html)), today=date(2026, 9, 29))
        self.assertEqual([i['url'] for i in result['items']], ['https://www.apple.com/es/iphone/'])
        self.assertEqual(result['today'], '2026-09-29 (martes 29 de septiembre de 2026)')
        self.assertIn('Hoy es 2026-09-29', result['note'])
        self.assertIn('recency', result['note'])

    def test_search_filtra_por_antiguedad_cuando_se_pide(self):
        html = '<div class="result"><a class="result__a" href="https://example.com/a">A</a><a class="result__snippet">x</a></div>'
        opener = Opener(Response(html))
        pedido = []
        abrir = opener.open
        opener.open = lambda request, timeout=0: pedido.append(request.data.decode()) or abrir(request, timeout)
        web.search('novedades', opener=opener, recency='mes')
        self.assertIn('df=m', pedido[0])
        with self.assertRaises(ValueError):
            web.search('novedades', opener=Opener(Response(html)), recency='siglo')

    def test_read_da_la_fecha_de_la_pagina_y_la_de_hoy(self):
        from datetime import date
        casos = {
            '<meta property="article:published_time" content="2024-03-05T10:00:00Z">': '2024-03-05',
            '<script type="application/ld+json">{"datePublished": "2026-09-10"}</script>': '2026-09-10',
            '<time datetime="2025-12-01">1 dic</time>': '2025-12-01',
        }
        for cabecera, esperada in casos.items():
            with self.subTest(esperada=esperada):
                page = '<html><head><title>N</title>' + cabecera + '</head><body><p>Texto.</p></body></html>'
                result = web.read('https://example.com/page', opener=Opener(Response(page)),
                                  resolver=public_resolver, today=date(2026, 9, 29))
                self.assertEqual(result['published'], esperada)
                self.assertTrue(result['today'].startswith('2026-09-29'))
        sin_fecha = web.read('https://example.com/page', opener=Opener(Response('<p>Texto.</p>')),
                             resolver=public_resolver)
        self.assertNotIn('published', sin_fecha)

    def test_lo_ultimo_filtra_solo_y_cada_resultado_dice_su_edad(self):
        from datetime import date
        html = ('<div class="result"><a class="result__a" href="https://www.apple.com/la/newsroom/2025/09/'
                'get-ready/">Presentación</a><a class="result__snippet">x</a></div>')
        opener = Opener(Response(html))
        pedido = []
        abrir = opener.open
        opener.open = lambda request, timeout=0: pedido.append(request.data.decode()) or abrir(request, timeout)
        result = web.search('últimos modelos de iPhone 2024 2025 2026', opener=opener, today=date(2026, 9, 29))
        self.assertIn('df=y', pedido[0])
        self.assertTrue(result['recency_auto'])
        self.assertEqual(result['items'][0]['url_date'], '2025-09')
        self.assertEqual(result['items'][0]['age'], 'hace 12 meses')

    def test_si_el_filtro_automatico_vacia_la_busqueda_se_repite_sin_el(self):
        vacia = Response('<html></html>')
        llena = Response('<div class="result"><a class="result__a" href="https://example.com/a">A</a>'
                         '<a class="result__snippet">x</a></div>')
        respuestas = [vacia, llena]
        opener = Opener(vacia)
        opener.open = lambda request, timeout=0: respuestas.pop(0)
        result = web.search('novedades de algo raro', opener=opener)
        self.assertIsNone(result['recency'])
        self.assertEqual(len(result['items']), 1)

    def test_pagina_vieja_avisa_y_la_modificacion_no_la_disfraza(self):
        from datetime import date
        page = ('<html><head><title>N</title><meta property="article:published_time" content="2025-09-11">'
                '<meta property="article:modified_time" content="2026-08-19"></head><body><p>Texto.</p></body></html>')
        result = web.read('https://example.com/page', opener=Opener(Response(page)),
                          resolver=public_resolver, today=date(2026, 9, 29))
        self.assertEqual(result['published'], '2025-09-11')
        self.assertEqual(result['age'], 'hace 12 meses')
        self.assertIn('No la presentes como lo último', result['age_warning'])
        self.assertNotIn('modified', result)
        self.assertNotIn('updated', result)
        reciente = web.read('https://example.com/page', opener=Opener(Response(page.replace('2025-09-11', '2026-09-09'))),
                            resolver=public_resolver, today=date(2026, 9, 29))
        self.assertNotIn('age_warning', reciente)

    def test_catalogo_admite_recency_opcional(self):
        from hexos.agent import catalog
        catalog.validate('web.search', {'query': 'x', 'recency': 'año'})

    def test_read_extrae_texto_y_elimina_scripts(self):
        page = '<html><head><title>Fuente</title><script>robar()</script></head><body><h1>Dato</h1><p>Contenido verificable.</p></body></html>'
        result = web.read('https://example.com/page', opener=Opener(Response(page)),
                          resolver=public_resolver)
        self.assertEqual(result['title'], 'Fuente')
        self.assertIn('Contenido verificable.', result['text'])
        self.assertNotIn('robar', result['text'])

    def test_read_lee_un_pdf_con_texto_por_el_extractor(self):
        visto = []
        texto = 'Apple-1 Operation Manual. ' + 'The Apple Computer is a complete microprocessor system. ' * 8
        respuesta = Response('%PDF-1.4 binario', url='https://example.com/manual.pdf', content_type='application/pdf')
        salida = web.read('https://example.com/manual.pdf', opener=Opener(respuesta), resolver=public_resolver,
                          pdf=lambda datos: visto.append(datos) or texto)
        self.assertEqual(visto, [b'%PDF-1.4 binario'], 'el extractor recibe los bytes, sin decodificar')
        self.assertEqual((salida['content_type'], salida['text'], salida['truncated']),
                         ('application/pdf', texto, False))

    def test_lo_que_no_se_puede_leer_deja_el_enlace_para_la_persona(self):
        def leer(tipo, pdf=None, cuerpo='x'):
            respuesta = Response(cuerpo, url='https://example.com/planos', content_type=tipo)
            with self.assertRaises(ValueError) as fallo:
                web.read('https://example.com/planos', opener=Opener(respuesta), resolver=public_resolver, pdf=pdf)
            self.assertIn(web.ENLACE_VALIDO, str(fallo.exception))
            return str(fallo.exception)

        self.assertIn('sin texto que leer', leer('application/pdf', pdf=lambda datos: '\n\n 1 \n'))

        def roto(datos):
            raise ValueError('el PDF no se pudo abrir: está dañado o protegido')
        self.assertIn('dañado o protegido', leer('application/pdf', pdf=roto))
        self.assertIn('más de 5 MB', leer('application/pdf', pdf=lambda datos: 'no llega', cuerpo='x' * (web.MAX_DOWNLOAD + 1)))
        self.assertIn('un archivo ZIP', leer('application/zip'))
        self.assertIn('de tipo image/png', leer('image/png'))

    def test_el_pdf_se_abre_en_una_jaula_sin_red_ni_carpeta_personal(self):
        ordenes = []

        class Hecho:
            returncode, stdout = 0, 'página uno\fpágina dos'.encode()

        texto = web._pdf_text(b'%PDF', lanzar=lambda orden, **k: ordenes.append((orden, k)) or Hecho)
        orden, opciones = ordenes[0]
        self.assertEqual(texto, 'página uno\npágina dos')
        self.assertEqual((opciones['input'], opciones['timeout']), (b'%PDF', web.PDF_SEGUNDOS))
        self.assertTrue(orden[0].endswith('bwrap'))
        self.assertIn('--unshare-all', orden)
        self.assertIn('--clearenv', orden)
        self.assertNotIn(str(Path.home()), ' '.join(orden))
        self.assertEqual(orden[orden.index('--ro-bind'):][:3], ['--ro-bind', '/usr', '/usr'])

        Hecho.returncode = 1
        with self.assertRaises(ValueError):
            web._pdf_text(b'no es un pdf', lanzar=lambda orden, **k: Hecho)

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

    def test_una_url_con_el_titulo_no_aborta_el_turno(self):
        url = 'https://example.com/n100'
        runtime = ScriptedRuntime([
            {'tool': 'web.search', 'arguments': {'query': 'N100'}},
            {'tool': 'web.read', 'arguments': {'url': url + ': What is the difference?'}},
            {'reply': 'Falló el enlace.', 'work': None},
            {'tool': 'web.read', 'arguments': {'url': url}},
            {'reply': 'Ya pude leer la ficha.', 'work': None},
        ])
        dependencies = AgentDependencies(
            web_search=lambda *a, **k: {'items': [{'url': url}]},
            web_read=lambda link: web.read(link, resolver=public_resolver, opener=Opener(
                Response('<p>Ficha técnica de prueba.</p>', url=url))))
        with tempfile.TemporaryDirectory() as tmp:
            result = Agent(tmp, runtime, dependencies=dependencies).chat('Consulta la ficha del N100')
        self.assertTrue(result['tools'][1]['failed'])
        self.assertFalse(result['tools'][2]['failed'])
        self.assertIn('Ya pude leer la ficha.', result['reply'])

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
