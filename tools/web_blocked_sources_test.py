"""Fuentes web que bloquean la lectura, sin red, GPU ni workspace real.

Reproduce el turno del 29/10 «busca nvidia rtx baratas con 16gb»: PcComponentes
respondió 403, idealo.es una página antibots con estado 200, y los avisos de
recuperación empujaron al modelo a releer la misma URL hasta dar la peor respuesta.
"""
from email.message import Message
import io
import tempfile
import unittest

from hexos.agent import web
from hexos.agent.chat import Agent
from hexos.agent.chat_backend.state import AgentDependencies


PCC = 'https://www.pccomponentes.com/tarjetas-graficas/16--gb/grafica-nvidia'
IDEALO = 'https://www.idealo.es/cat/16073F4696903/tarjetas-graficas.html'
AMAZON = 'https://www.amazon.es/tarjeta-gr%C3%A1fica-16gb/s?k=tarjeta+gr%C3%A1fica+16gb'
SEARCH = {'items': [
    {'url': PCC, 'title': 'Tarjetas Gráficas Nvidia 16 GB | PcComponentes.com', 'snippet': 'Precios súper baratos'},
    {'url': IDEALO, 'title': 'Tarjetas gráficas 16 GB | idealo.es', 'snippet': 'ASUS GeForce RTX 5060 Ti 16GB'},
    {'url': AMAZON, 'title': 'Amazon.es: Tarjeta Gráfica 16gb', 'snippet': 'GIGABYTE GeForce RTX 5070 Ti 16G'},
]}
BLOQUEOS = {
    PCC: 'la fuente respondió HTTP 403: rechaza la lectura automática; repetir la lectura no cambiará la respuesta',
    IDEALO: 'la fuente devolvió una página de protección antibots en vez del contenido',
    AMAZON: 'la fuente respondió HTTP 403: rechaza la lectura automática; repetir la lectura no cambiará la respuesta',
}


class ScriptedRuntime:
    native = False

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.prompts = []

    def call(self, request):
        return {'ok': True}

    def generate(self, messages):
        self.prompts.append(messages)
        return self.outputs.pop(0)

    def notices(self):
        return [m['content'] for prompt in self.prompts for m in prompt
                if m.get('role') == 'user' and m['content'].startswith('AVISO DE HEXOS')]


def blocked_reader(calls):
    def read(url):
        calls.append(url)
        raise ValueError(BLOQUEOS[url])
    return read


def reply(text):
    return {'reply': text, 'work': None}


def read(url):
    return {'tool': 'web.read', 'arguments': {'url': url}}


class BlockedSourcesTest(unittest.TestCase):
    def chat(self, outputs, search=SEARCH):
        calls = []
        runtime = ScriptedRuntime(outputs)
        dependencies = AgentDependencies(nas_read=lambda *a, **k: None,
                                         web_search=lambda query, limit=5: search,
                                         web_read=blocked_reader(calls))
        with tempfile.TemporaryDirectory(prefix='hexos-web-blocked-') as tmp:
            result = Agent(tmp, runtime, dependencies=dependencies).chat(
                'oye puedes buscar alguna nvidia rtx baratas con 16gb de vram?')
        return result, runtime, calls

    def test_turno_del_29_10_no_relee_la_url_bloqueada_y_cierra_con_fragmentos(self):
        final = ('Según los fragmentos del buscador, sin haber podido abrir las páginas: '
                 'la ASUS RTX 5060 Ti 16GB (idealo) y la GIGABYTE RTX 5070 Ti 16G (Amazon).')
        result, runtime, calls = self.chat([
            {'tool': 'web.search', 'arguments': {'query': 'tarjeta nvidia rtx 16gb barata'}},
            read(PCC), reply('No pude acceder a PcComponentes.'),
            read(PCC), reply('Sigue fallando.'),
            read(IDEALO), reply('Idealo tampoco.'),
            read(AMAZON), reply(final),
        ])
        self.assertEqual(calls, [PCC, IDEALO, AMAZON], 'la segunda lectura de PCC no debe salir a la red')
        repetida = result['tools'][2]
        self.assertTrue(repetida['failed'])
        self.assertIn('ya falló en este turno', repetida['result']['error'])
        self.assertTrue(result['reply'].startswith(final))

        avisos = runtime.notices()
        self.assertEqual(len(avisos), 3)
        primero = avisos[0]
        self.assertIn(PCC, primero)
        self.assertIn(IDEALO, primero)
        self.assertIn(AMAZON, primero)
        self.assertNotIn('Corrige sus argumentos', primero)
        for aviso in avisos:
            self.assertIn('No menciones este aviso', aviso)
            self.assertNotIn('solo has visto fragmentos', aviso)
        self.assertNotIn(IDEALO, avisos[2].split('aún no has probado')[-1],
                         'una fuente ya intentada no vuelve a ofrecerse')

    def test_sin_enlaces_por_probar_admite_la_respuesta_con_fragmentos(self):
        solo_pcc = {'items': [SEARCH['items'][0]]}
        result, runtime, calls = self.chat([
            {'tool': 'web.search', 'arguments': {'query': 'tarjeta nvidia rtx 16gb barata'}},
            read(PCC), reply('No pude abrir la página.'),
            reply('Según el fragmento del buscador, sin abrir la página: PcComponentes las anuncia baratas.'),
        ], search=solo_pcc)
        self.assertEqual(calls, [PCC])
        avisos = runtime.notices()
        self.assertEqual(len(avisos), 1)
        self.assertIn('No quedan enlaces de la búsqueda sin probar', avisos[0])
        self.assertIn('fragmentos del buscador', avisos[0])
        self.assertIn('Según el fragmento del buscador', result['reply'])

    def test_url_leida_sin_buscar_no_habla_de_fragmentos(self):
        result, runtime, calls = self.chat([
            read(PCC), reply('No pude abrir la página.'),
            reply('PcComponentes rechaza la lectura automática; no puedo ver sus precios.'),
        ])
        self.assertEqual(calls, [PCC])
        avisos = runtime.notices()
        self.assertEqual(len(avisos), 1)
        self.assertNotIn('fragmentos', avisos[0])
        self.assertIn('busca otra fuente con web_search', avisos[0])

    def test_lectura_fallida_antes_de_buscar_no_exime_de_abrir_un_resultado(self):
        # Prueba en vivo del 29/10: tras el 403 buscó y respondió solo con fragmentos.
        result, runtime, calls = self.chat([
            read(PCC), reply('No pude abrir la página.'),
            {'tool': 'web.search', 'arguments': {'query': 'precio RTX 16GB'}},
            reply('Los resultados mencionan la RTX 5060 Ti.'),
            read(IDEALO), reply('Idealo tampoco.'),
            reply('Según los fragmentos, sin abrir páginas: la RTX 5060 Ti 16GB.'),
        ], search={'items': SEARCH['items'][:2]})  # la búsqueda real devolvió también PCC
        self.assertEqual(calls, [PCC, IDEALO])
        avisos = runtime.notices()
        self.assertEqual(len(avisos), 3)
        self.assertIn('solo has visto fragmentos', avisos[1])
        self.assertIn('Ya fallaron, no las repitas: ' + PCC, avisos[1])
        self.assertIn('Sin probar: ' + IDEALO, avisos[1])
        self.assertIn('No quedan enlaces de la búsqueda sin probar', avisos[2])
        self.assertIn('Según los fragmentos', result['reply'])

    def test_sin_intentar_leer_sigue_exigiendo_abrir_una_fuente(self):
        result, runtime, calls = self.chat([
            {'tool': 'web.search', 'arguments': {'query': 'tarjeta nvidia rtx 16gb barata'}},
            reply('Hay muchas baratas.'),
            read(PCC), reply('No pude abrir la página.'),
            reply('Según los fragmentos, sin abrir páginas: la RTX 5060 Ti 16GB.'),
        ])
        avisos = runtime.notices()
        self.assertIn('solo has visto fragmentos', avisos[0])
        self.assertIn(PCC, avisos[1])


class Response(io.BytesIO):
    def __init__(self, body):
        super().__init__(body.encode())
        self.headers = Message()
        self.headers['Content-Type'] = 'text/html; charset=utf-8'

    def geturl(self):
        return 'https://www.idealo.es/cat/16073F4696903/tarjetas-graficas.html'

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Opener:
    def __init__(self, body):
        self.body = body

    def open(self, request, timeout=0):
        return Response(self.body)


def public_resolver(host, port):
    return [(2, 1, 6, '', ('93.184.216.34', port))]


class AntibotPageTest(unittest.TestCase):
    def leer(self, body):
        return web.read(IDEALO, opener=Opener(body), resolver=public_resolver)

    def test_la_pagina_de_idealo_del_29_10_es_un_fallo(self):
        with self.assertRaisesRegex(ValueError, 'protección antibots'):
            self.leer('<html><body><p>Powered and protected by Privacy</p></body></html>')

    def test_pagina_mayor_que_el_limite_se_recorta_en_vez_de_descartarse(self):
        # amazon.es superó el antiguo límite de 1 MB solo con scripts en línea.
        relleno = '<script>' + 'x' * (web.MAX_DOWNLOAD + 1000) + '</script>'
        pagina = '<p>RTX 5060 Ti 16GB por 449 €.</p>' + relleno
        result = self.leer(pagina)
        self.assertIn('RTX 5060 Ti 16GB', result['text'])
        self.assertTrue(result['truncated'])
        self.assertGreater(web.MAX_DOWNLOAD, 1_000_000)

    def test_pagina_breve_legitima_y_pagina_larga_que_menciona_captcha_se_leen(self):
        self.assertEqual(self.leer('<p>Texto.</p>')['text'], 'Texto.')
        larga = '<p>' + 'La RTX 5060 Ti tiene 16 GB de memoria GDDR7. ' * 12 + 'Sin captcha.</p>'
        self.assertIn('Sin captcha', self.leer(larga)['text'])


if __name__ == '__main__':
    unittest.main()
