"""Descargas de la web con aprobación: proponer, la tarjeta, bajar y leer lo bajado.

Sin red ni GPU. Sale del turno del 16/11: el primer resultado era el manual del Apple 1
en PDF y Helios no tenía forma de dejárselo a la persona en el PC.
"""
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent import catalog, descargas, web
from hexos.agent.chat import Agent
from hexos.agent.chat_backend.server import make_handler
from hexos.agent.chat_backend.state import AgentDependencies

URL = 'https://s3data.computerhistory.org/brochures/apple.applei.1976.102646518.pdf'
PDF = b'%PDF-1.4 ' + b'x' * 2000
TEXTO = 'Apple-1 Operation Manual.\n' + 'The Apple Computer is a complete microprocessor system.\n' * 40


def asomar(tipo='application/pdf', pesa=2_018_052, final=None):
    return lambda url: (final or url, tipo, pesa)


class ScriptedRuntime:
    native = False

    def __init__(self, outputs=()):
        self.outputs = list(outputs)

    def call(self, request):
        return {'ok': True}

    def generate(self, messages):
        return self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-descargas-')
        self.casa = Path(self.tmp.name)
        self.carpeta = self.casa / 'bajado'
        entorno = mock.patch.dict(os.environ, {'HEXOS_DOWNLOADS_HOME': str(self.carpeta)})
        entorno.start()
        self.addCleanup(entorno.stop)
        self.addCleanup(self.tmp.cleanup)

    def agente(self, outputs=()):
        return Agent(self.casa / 'ws', ScriptedRuntime(outputs), dependencies=AgentDependencies(
            nas_read=lambda *a, **k: None, web_search=lambda q, limit=5: {'items': []}, web_read=lambda u: {'text': 'x'}))


class ProponerTest(Base):
    def test_el_plan_dice_nombre_origen_tipo_y_tamano_sin_bajar_nada(self):
        plan = descargas.proponer(URL, asomar=asomar())
        self.assertEqual((plan['name'], plan['host'], plan['kind'], plan['bytes']),
                         ('apple.applei.1976.102646518.pdf', 's3data.computerhistory.org', 'PDF', 2_018_052))
        self.assertEqual(plan['summary'], 'descargar apple.applei.1976.102646518.pdf (PDF, 2,0 MB) de '
                                          's3data.computerhistory.org')
        self.assertFalse(self.carpeta.exists())

    def test_el_nombre_no_lleva_carpetas_ni_rarezas_y_gana_extension(self):
        self.assertEqual(descargas.proponer(URL, '../../.ssh/manual apple;1.pdf', asomar=asomar())['name'],
                         'manual apple_1.pdf')
        self.assertEqual(descargas.proponer('https://example.com/get?id=7', asomar=asomar())['name'], 'get.pdf')
        self.assertEqual(descargas.proponer('https://example.com/', asomar=asomar('image/png', None))['name'],
                         'descarga.png')

    def test_no_se_proponen_paginas_programas_ni_ficheros_enormes(self):
        casos = ((URL, asomar('text/html'), 'web_read'),
                 ('https://example.com/juego.deb', asomar('application/octet-stream'), 'programa o un instalador'),
                 ('https://example.com/x', asomar('application/x-msdownload'), 'programa o un instalador'),
                 (URL, asomar(pesa=descargas.MAX_BYTES + 1), 'el tope es'))
        for url, mira, texto in casos:
            with self.assertRaises(ValueError) as fallo:
                descargas.proponer(url, asomar=mira)
            self.assertIn(texto, str(fallo.exception))
        with self.assertRaises(ValueError):
            descargas.proponer('http://192.168.1.10/planos.pdf')
        with self.assertRaises(ValueError):
            descargas.proponer('   ', asomar=asomar())


class AplicarTest(Base):
    def bajar(self, plan, datos=PDF, tipo='application/pdf', cortado=False, texto=TEXTO):
        with self.agente().store() as store:
            return descargas.aplicar(store, plan, descargar=lambda url, limite: (url, tipo, datos, cortado),
                                     pdf=lambda d, paginas, segundos: texto)

    def test_guarda_comprueba_y_deja_el_texto_como_documento_legible(self):
        hecho = self.bajar(descargas.proponer(URL, 'manual.pdf', asomar=asomar()))
        destino = self.carpeta / 'manual.pdf'
        self.assertEqual((hecho['executed'], hecho['verified'], hecho['refused']), (True, True, None))
        self.assertEqual(destino.read_bytes(), PDF)
        self.assertEqual(stat.S_IMODE(destino.stat().st_mode) & 0o111, 0, 'sin permiso de ejecución')
        self.assertEqual([p.name for p in self.carpeta.iterdir()], ['manual.pdf'], 'no queda el fichero parcial')
        self.assertIn('document_read', hecho['check'])
        agente = self.agente()
        with agente.store() as store:
            leido = agente.tool(store, 'document.read', {'id': hecho['document']['id'], 'start': 1, 'count': 2})
            lista = agente.tool(store, 'file.list', {})
        self.assertIn('Apple-1 Operation Manual.', json.dumps(leido))
        self.assertEqual((lista['count'], lista['downloads'][0]['name'], lista['downloads'][0]['document'],
                          lista['downloads'][0]['on_disk']), (1, 'manual.pdf', hecho['document']['id'], True))

    def test_un_nombre_repetido_no_pisa_el_anterior(self):
        plan = descargas.proponer(URL, 'manual.pdf', asomar=asomar())
        self.bajar(plan)
        self.assertEqual(self.bajar(plan, datos=PDF + b'2')['name'], 'manual (2).pdf')
        self.assertEqual((self.carpeta / 'manual.pdf').read_bytes(), PDF)

    def test_unos_planos_sin_texto_se_guardan_sin_documento(self):
        hecho = self.bajar(descargas.proponer(URL, asomar=asomar()), texto='\n 1 \n')
        self.assertEqual((hecho['executed'], hecho['document']), (True, None))
        self.assertIn('no tiene texto', hecho['check'])

    def test_si_lo_que_llega_no_es_lo_aprobado_no_se_guarda(self):
        plan = descargas.proponer(URL, asomar=asomar())
        for hecho in (self.bajar(plan, tipo='application/x-msdownload'), self.bajar(plan, cortado=True),
                      self.bajar(plan, datos=b'')):
            self.assertEqual((hecho['executed'], bool(hecho['refused'])), (False, True))
        with self.agente().store() as store:
            def caido(url, limite):
                raise ValueError('la fuente respondió HTTP 403')
            self.assertIn('403', descargas.aplicar(store, plan, descargar=caido)['refused'])
        self.assertFalse(self.carpeta.exists())


class TurnoTest(Base):
    def test_la_herramienta_solo_propone_y_van_de_una_en_una(self):
        agente = self.agente()
        with mock.patch.object(web, 'asomar', asomar()):
            with agente.store() as store:
                primera = agente.tool(store, 'file.download', {'url': URL})
                otra_vez = agente.tool(store, 'file.download', {'url': URL})
                segunda = agente.tool(store, 'file.download', {'url': 'https://example.com/otro.pdf'})
        self.assertEqual((primera['status'], primera['size'], primera['source']),
                         ('pending_approval', '2,0 MB', 's3data.computerhistory.org'))
        self.assertNotIn('plan_id', primera)
        self.assertEqual((otra_vez['status'], segunda['status']), ('pending_approval', 'waiting_previous_plan'))
        self.assertEqual(agente.download_request['url'], URL)
        self.assertFalse(self.carpeta.exists())
        self.assertIn('DESCARGA PENDIENTE', descargas.bloque_pendiente(agente.download_request))

    def test_aprobar_baja_una_vez_y_lo_cuenta_en_el_turno_siguiente(self):
        agente = self.agente()
        agente.session.download_request = plan = descargas.proponer(URL, 'manual.pdf', asomar=asomar())
        with self.assertRaises(ValueError):
            agente.decide_download({'plan_id': 'otro', 'approve': True})
        hecho = agente.decide_download({'plan_id': plan['plan_id'], 'approve': True},
                                       apply=lambda store, p: descargas.aplicar(
                                           store, p, descargar=lambda u, l: (u, 'application/pdf', PDF, False),
                                           pdf=lambda d, paginas, segundos: TEXTO))
        self.assertTrue(hecho['verified'])
        self.assertIn('descargado y comprobado', hecho['note'])
        self.assertIn('document_read', hecho['note'])
        self.assertIsNone(agente.download_request)
        self.assertEqual(agente.session.notas_interfaz, [hecho['note']])
        with self.assertRaises(ValueError):
            agente.decide_download({'plan_id': plan['plan_id'], 'approve': True})

    def test_rechazar_no_baja_nada(self):
        agente = self.agente()
        agente.session.download_request = plan = descargas.proponer(URL, asomar=asomar())
        hecho = agente.decide_download({'plan_id': plan['plan_id'], 'approve': False})
        self.assertEqual((hecho['cancelled'], hecho['executed']), (True, False))
        self.assertIn('No se ha descargado nada', hecho['note'])
        self.assertFalse(self.carpeta.exists())


class CatalogoTest(unittest.TestCase):
    def test_el_cajon_esta_en_el_chat_y_trae_con_que_leer_lo_bajado(self):
        self.assertIn('descargas', catalog.groups_in('chat'))
        self.assertNotIn('descargas', catalog.groups_in('agente'))
        visibles = catalog.tools_for(['descargas'], 'chat')
        for herramienta in ('file.download', 'file.list', 'document.read', 'web.search', 'web.read'):
            self.assertIn(herramienta, visibles)


class ServidorTest(Base):
    ORIGEN = 'http://127.0.0.1:3000'

    def setUp(self):
        super().setUp()
        self.agente_ = self.agente()
        ui = self.casa / 'ui.html'
        ui.write_text('x')
        self.servidor = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.agente_, lambda: {}, {self.ORIGEN}, ui))
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)
        self.url = 'http://127.0.0.1:%d' % self.servidor.server_address[1]

    def pedir(self, ruta, cuerpo=None):
        cabeceras = {'Content-Type': 'application/json', 'Origin': self.ORIGEN} if cuerpo is not None else {}
        pedido = urllib.request.Request(self.url + ruta, headers=cabeceras,
                                        data=None if cuerpo is None else json.dumps(cuerpo).encode())
        try:
            with urllib.request.urlopen(pedido, timeout=10) as r:
                return r.status, json.loads(r.read())
        except HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def test_la_tarjeta_sale_en_el_estado_y_se_decide_por_su_ruta(self):
        self.assertIsNone(self.pedir('/api/status')[1]['download_request'])
        self.agente_.session.download_request = plan = descargas.proponer(URL, asomar=asomar())
        visto = self.pedir('/api/status')[1]['download_request']
        self.assertEqual((visto['plan_id'], visto['name'], visto['host'], visto['kind'], visto['bytes']),
                         (plan['plan_id'], plan['name'], 's3data.computerhistory.org', 'PDF', 2_018_052))
        self.assertEqual(self.pedir('/api/download', {'plan_id': 'otro', 'approve': True})[0], 409)
        codigo, hecho = self.pedir('/api/download', {'plan_id': plan['plan_id'], 'approve': False})
        self.assertEqual((codigo, hecho['cancelled']), (200, True))
        self.assertIsNone(self.pedir('/api/status')[1]['download_request'])


if __name__ == '__main__':
    unittest.main()
