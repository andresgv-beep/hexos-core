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
        plan = descargas.mirar(URL, asomar=asomar())
        self.assertEqual((plan['name'], plan['host'], plan['kind'], plan['bytes']),
                         ('apple.applei.1976.102646518.pdf', 's3data.computerhistory.org', 'PDF', 2_018_052))
        self.assertEqual(plan['summary'], 'descargar apple.applei.1976.102646518.pdf (PDF, 2,0 MB) de '
                                          's3data.computerhistory.org')
        self.assertNotIn('plan_id', plan, 'un fichero suelto no es una tarjeta')
        self.assertFalse(self.carpeta.exists())

    def test_la_tarjeta_junta_los_ficheros_y_estrena_identificador_con_cada_uno(self):
        una = descargas.proponer(URL, 'manual.pdf', asomar=asomar())
        dos = descargas.proponer('https://example.com/planos.zip', asomar=asomar('application/zip', 500_000),
                                 pendiente=una)
        self.assertEqual(una['summary'], 'descargar manual.pdf (PDF, 2,0 MB) de s3data.computerhistory.org')
        self.assertEqual([f['name'] for f in dos['items']], ['manual.pdf', 'planos.zip'])
        self.assertEqual(dos['summary'], 'descargar 2 ficheros (2,5 MB en total): manual.pdf, planos.zip')
        self.assertNotEqual(una['plan_id'], dos['plan_id'], 'lo aprobado es la lista que se vio')
        self.assertEqual(len(una['items']), 1, 'la tarjeta anterior no se toca')
        sin_peso = descargas.proponer('https://example.com/foto.png', asomar=asomar('image/png', None), pendiente=dos)
        self.assertIn('3 ficheros (tamaño sin declarar)', sin_peso['summary'])
        self.assertEqual(descargas.mismo(dos, 'https://example.com/planos.zip')['name'], 'planos.zip')
        self.assertIsNone(descargas.mismo(dos, 'https://example.com/otro.zip'))
        llena = una
        for n in range(descargas.MAX_LOTE - 1):
            llena = descargas.proponer(f'https://example.com/{n}.pdf', asomar=asomar(), pendiente=llena)
        with self.assertRaises(ValueError):
            descargas.proponer('https://example.com/de-mas.pdf', asomar=asomar(), pendiente=llena)

    def test_el_nombre_no_lleva_carpetas_ni_rarezas_y_gana_extension(self):
        self.assertEqual(descargas.mirar(URL, '../../.ssh/manual apple;1.pdf', asomar=asomar())['name'],
                         'manual apple_1.pdf')
        self.assertEqual(descargas.mirar('https://example.com/get?id=7', asomar=asomar())['name'], 'get.pdf')
        self.assertEqual(descargas.mirar('https://example.com/', asomar=asomar('image/png', None))['name'],
                         'descarga.png')

    def test_no_se_proponen_paginas_programas_ni_ficheros_enormes(self):
        casos = ((URL, asomar('text/html'), 'web_read'),
                 ('https://example.com/juego.deb', asomar('application/octet-stream'), 'programa o un instalador'),
                 ('https://example.com/x', asomar('application/x-msdownload'), 'programa o un instalador'),
                 (URL, asomar(pesa=descargas.MAX_BYTES + 1), 'el tope es'))
        for url, mira, texto in casos:
            with self.assertRaises(ValueError) as fallo:
                descargas.mirar(url, asomar=mira)
            self.assertIn(texto, str(fallo.exception))
        with self.assertRaises(ValueError):
            descargas.mirar('http://192.168.1.10/planos.pdf')
        with self.assertRaises(ValueError):
            descargas.mirar('   ', asomar=asomar())


class AplicarTest(Base):
    def bajar(self, plan, datos=PDF, tipo='application/pdf', cortado=False, texto=TEXTO):
        with self.agente().store() as store:
            return descargas.aplicar(store, plan, descargar=lambda url, limite: (url, tipo, datos, cortado),
                                     pdf=lambda d, paginas, segundos: texto)

    def test_guarda_comprueba_y_deja_el_texto_como_documento_legible(self):
        hecho = self.bajar(descargas.mirar(URL, 'manual.pdf', asomar=asomar()))
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
        plan = descargas.mirar(URL, 'manual.pdf', asomar=asomar())
        self.bajar(plan)
        self.assertEqual(self.bajar(plan, datos=PDF + b'2')['name'], 'manual (2).pdf')
        self.assertEqual((self.carpeta / 'manual.pdf').read_bytes(), PDF)

    def test_unos_planos_sin_texto_se_guardan_sin_documento(self):
        hecho = self.bajar(descargas.mirar(URL, asomar=asomar()), texto='\n 1 \n')
        self.assertEqual((hecho['executed'], hecho['document']), (True, None))
        self.assertIn('no tiene texto', hecho['check'])

    def test_si_lo_que_llega_no_es_lo_aprobado_no_se_guarda(self):
        plan = descargas.mirar(URL, asomar=asomar())
        for hecho in (self.bajar(plan, tipo='application/x-msdownload'), self.bajar(plan, cortado=True),
                      self.bajar(plan, datos=b'')):
            self.assertEqual((hecho['executed'], bool(hecho['refused'])), (False, True))
        with self.agente().store() as store:
            def caido(url, limite):
                raise ValueError('la fuente respondió HTTP 403')
            self.assertIn('403', descargas.aplicar(store, plan, descargar=caido)['refused'])
        self.assertFalse(self.carpeta.exists())


class TurnoTest(Base):
    def bajada(self, fallan=()):
        def descargar(url, limite):
            if url in fallan:
                raise ValueError('la fuente respondió HTTP 403')
            return url, 'application/pdf', PDF + url.encode(), False
        return lambda store, fichero: descargas.aplicar(store, fichero, descargar=descargar,
                                                         pdf=lambda d, paginas, segundos: TEXTO)

    def test_la_herramienta_solo_propone_y_lo_seguido_va_a_la_misma_tarjeta(self):
        agente = self.agente()
        with mock.patch.object(web, 'asomar', asomar()):
            with agente.store() as store:
                primera = agente.tool(store, 'file.download', {'url': URL})
                una = agente.download_request
                otra_vez = agente.tool(store, 'file.download', {'url': URL})
                segunda = agente.tool(store, 'file.download', {'url': 'https://example.com/otro.pdf', 'name': 'otro'})
        self.assertEqual((primera['status'], primera['size'], primera['source'], primera['in_card']),
                         ('pending_approval', '2,0 MB', 's3data.computerhistory.org', 1))
        self.assertNotIn('plan_id', primera)
        self.assertIn('llama ahora a file_download con el siguiente', primera['note'])
        self.assertEqual((otra_vez['status'], otra_vez['summary']), ('pending_approval', primera['summary']))
        self.assertEqual((segunda['status'], segunda['name'], segunda['in_card']), ('pending_approval', 'otro.pdf', 2))
        self.assertIn('lleva 2 ficheros', segunda['note'])
        tarjeta = agente.download_request
        self.assertEqual([f['url'] for f in tarjeta['items']], [URL, 'https://example.com/otro.pdf'])
        self.assertNotEqual(tarjeta['plan_id'], una['plan_id'])
        self.assertFalse(self.carpeta.exists())
        self.assertIn('descargar 2 ficheros', descargas.bloque_pendiente(tarjeta))

    def test_una_redireccion_al_mismo_fichero_no_lo_pone_dos_veces(self):
        agente = self.agente()
        with mock.patch.object(web, 'asomar', asomar(final=URL)):
            with agente.store() as store:
                agente.tool(store, 'file.download', {'url': URL})
                otra = agente.tool(store, 'file.download', {'url': 'https://example.com/atajo'})
        self.assertIn('ya estaba en la tarjeta', otra['note'])
        self.assertEqual(len(agente.download_request['items']), 1)

    def test_con_la_tarjeta_llena_el_siguiente_espera(self):
        agente = self.agente()
        with mock.patch.object(web, 'asomar', asomar()):
            with agente.store() as store:
                for n in range(descargas.MAX_LOTE):
                    agente.tool(store, 'file.download', {'url': f'https://example.com/{n}.pdf'})
                de_mas = agente.tool(store, 'file.download', {'url': 'https://example.com/de-mas.pdf'})
        self.assertEqual((de_mas['status'], de_mas['planned']), ('waiting_previous_plan', False))
        self.assertEqual(len(agente.download_request['items']), descargas.MAX_LOTE)

    def test_aprobar_baja_una_vez_y_lo_cuenta_en_el_turno_siguiente(self):
        agente = self.agente()
        agente.session.download_request = plan = descargas.proponer(URL, 'manual.pdf', asomar=asomar())
        with self.assertRaises(ValueError):
            agente.decide_download({'plan_id': 'otro', 'approve': True})
        hecho = agente.decide_download({'plan_id': plan['plan_id'], 'approve': True}, apply=self.bajada())
        self.assertTrue(hecho['verified'])
        self.assertEqual([f['name'] for f in hecho['files']], ['manual.pdf'])
        self.assertIn('[La persona aprobó en la interfaz: descargar manual.pdf (PDF, 2,0 MB) de '
                      's3data.computerhistory.org. HexOS: descargado y comprobado (', hecho['note'])
        self.assertIn('document_read', hecho['note'])
        self.assertIsNone(agente.download_request)
        self.assertEqual(agente.session.notas_interfaz, [hecho['note']])
        with self.assertRaises(ValueError):
            agente.decide_download({'plan_id': plan['plan_id'], 'approve': True})

    def test_aprobar_varios_los_baja_todos_y_el_que_falla_no_arrastra_a_los_demas(self):
        agente = self.agente()
        una = descargas.proponer(URL, 'manual.pdf', asomar=asomar())
        dos = descargas.proponer('https://example.com/caido.pdf', asomar=asomar(), pendiente=una)
        agente.session.download_request = tres = descargas.proponer('https://example.com/planos.pdf',
                                                                    asomar=asomar(), pendiente=dos)
        with self.assertRaises(ValueError) as vieja:
            agente.decide_download({'plan_id': una['plan_id'], 'approve': True}, apply=self.bajada())
        self.assertIn('ha cambiado desde que la viste', str(vieja.exception))
        self.assertFalse(self.carpeta.exists(), 'con la tarjeta vieja no se baja nada')
        hecho = agente.decide_download({'plan_id': tres['plan_id'], 'approve': True},
                                       apply=self.bajada(fallan=('https://example.com/caido.pdf',)))
        self.assertEqual([(f['name'], f['executed'], f['verified']) for f in hecho['files']],
                         [('manual.pdf', True, True), ('caido.pdf', False, False), ('planos.pdf', True, True)])
        self.assertEqual((hecho['executed'], hecho['verified']), (True, False), 'no todo quedó bajado')
        self.assertEqual(sorted(p.name for p in self.carpeta.iterdir()), ['manual.pdf', 'planos.pdf'])
        self.assertIn('HexOS: 2 de 3 descargados y comprobados (', hecho['note'])
        self.assertIn('caido.pdf: no se descargó: la fuente respondió HTTP 403 (no se ha guardado nada)', hecho['note'])
        self.assertIn('planos.pdf: descargado y comprobado (', hecho['note'])
        with agente.store() as store:
            self.assertEqual(agente.tool(store, 'file.list', {})['count'], 2)
        self.assertIsNone(agente.download_request)

    def test_un_disco_que_no_deja_guardar_se_cuenta_sin_perder_lo_ya_bajado(self):
        agente = self.agente()
        una = descargas.proponer(URL, 'manual.pdf', asomar=asomar())
        agente.session.download_request = dos = descargas.proponer('https://example.com/lleno.pdf',
                                                                   asomar=asomar(), pendiente=una)
        buena = self.bajada()

        def aplicar(store, fichero):
            if fichero['name'] == 'lleno.pdf':
                raise OSError(28, 'No queda espacio en el dispositivo')
            return buena(store, fichero)
        hecho = agente.decide_download({'plan_id': dos['plan_id'], 'approve': True}, apply=aplicar)
        self.assertIn('1 de 2 descargados y comprobados', hecho['note'])
        self.assertIn('lleno.pdf: no se descargó: no se pudo guardar: No queda espacio', hecho['note'])

    def test_rechazar_no_baja_nada(self):
        agente = self.agente()
        una = descargas.proponer(URL, asomar=asomar())
        agente.session.download_request = plan = descargas.proponer('https://example.com/otro.pdf',
                                                                    asomar=asomar(), pendiente=una)
        hecho = agente.decide_download({'plan_id': plan['plan_id'], 'approve': False})
        self.assertEqual((hecho['cancelled'], hecho['executed']), (True, False))
        self.assertIn('rechazó en la interfaz: descargar 2 ficheros', hecho['note'])
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

    def bruto(self, ruta):
        try:
            with urllib.request.urlopen(self.url + ruta, timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except HTTPError as error:
            with error:
                return error.code, dict(error.headers), error.read()

    def bajar(self, nombre, tipo, datos, texto=''):
        plan = descargas.mirar('https://example.com/' + nombre, asomar=asomar(tipo, len(datos)))
        with self.agente_.store() as store:
            return descargas.aplicar(store, plan, descargar=lambda u, l: (u, tipo, datos, False),
                                     pdf=lambda d, paginas, segundos: texto)

    def test_el_panel_lista_lo_descargado_y_cada_fichero_se_ve_o_se_guarda(self):
        self.assertEqual(self.pedir('/api/downloads')[1]['downloads'], [])
        self.bajar('planos.svg', 'image/svg+xml', b'<svg onload="alert(1)"/>')
        self.bajar('manual.pdf', 'application/pdf', PDF, TEXTO)
        lista = self.pedir('/api/downloads')[1]
        self.assertEqual([(d['name'], d['kind'], d['viewable'], d['readable'], d['on_disk']) for d in lista['downloads']],
                         [('manual.pdf', 'PDF', True, True, True), ('planos.svg', 'imagen SVG', False, False, True)])
        pdf, svg = (d['id'] for d in lista['downloads'])

        codigo, cabeceras, cuerpo = self.bruto('/api/downloads/' + pdf)
        self.assertEqual((codigo, cabeceras['Content-Type'], cuerpo), (200, 'application/pdf', PDF))
        self.assertTrue(cabeceras['Content-Disposition'].startswith('inline'))
        self.assertEqual(cabeceras['X-Content-Type-Options'], 'nosniff')
        codigo, cabeceras, cuerpo = self.bruto('/api/downloads/' + pdf + '/download')
        self.assertEqual((cabeceras['Content-Type'], cuerpo), ('application/octet-stream', PDF))
        self.assertIn("attachment; filename*=UTF-8''manual.pdf", cabeceras['Content-Disposition'])
        # Un SVG abierto en el origen de Helios ejecutaría su script: solo se entrega para guardar.
        codigo, cabeceras, _ = self.bruto('/api/downloads/' + svg)
        self.assertEqual(cabeceras['Content-Type'], 'application/octet-stream')
        self.assertTrue(cabeceras['Content-Disposition'].startswith('attachment'))

    def test_solo_se_sirve_lo_que_sigue_en_la_carpeta_de_descargas(self):
        self.bajar('manual.pdf', 'application/pdf', PDF, TEXTO)
        uno = self.pedir('/api/downloads')[1]['downloads'][0]['id']
        for ruta in ('/api/downloads/no-existe', '/api/downloads/' + uno + '/otra', '/api/downloads/' + uno + '/a/b'):
            self.assertEqual(self.bruto(ruta)[0], 404)
        destino = self.carpeta / 'manual.pdf'
        destino.unlink()
        self.assertEqual(self.bruto('/api/downloads/' + uno)[0], 404)
        self.assertFalse(self.pedir('/api/downloads')[1]['downloads'][0]['on_disk'])
        secreto = self.casa / 'secreto.txt'
        secreto.write_text('clave')
        destino.symlink_to(secreto)
        self.assertEqual(self.bruto('/api/downloads/' + uno)[0], 404, 'un enlace hacia fuera no se sigue')
        with self.agente_.store() as store:
            store.db.execute('UPDATE downloads SET path=? WHERE id=?', (str(secreto), uno))
            store.db.commit()
        self.assertEqual(self.bruto('/api/downloads/' + uno)[0], 404, 'una ruta fuera de la carpeta no se sirve')

    def test_la_tarjeta_sale_en_el_estado_y_se_decide_por_su_ruta(self):
        self.assertIsNone(self.pedir('/api/status')[1]['download_request'])
        self.agente_.session.download_request = plan = descargas.proponer(URL, asomar=asomar())
        visto = self.pedir('/api/status')[1]['download_request']
        fichero = visto['items'][0]
        self.assertEqual((visto['plan_id'], visto['summary'], visto['folder']),
                         (plan['plan_id'], plan['summary'], plan['folder']))
        self.assertEqual((fichero['name'], fichero['host'], fichero['kind'], fichero['bytes'], fichero['url']),
                         ('apple.applei.1976.102646518.pdf', 's3data.computerhistory.org', 'PDF', 2_018_052, URL))
        self.assertEqual(self.pedir('/api/download', {'plan_id': 'otro', 'approve': True})[0], 409)
        codigo, hecho = self.pedir('/api/download', {'plan_id': plan['plan_id'], 'approve': False})
        self.assertEqual((codigo, hecho['cancelled']), (200, True))
        self.assertIsNone(self.pedir('/api/status')[1]['download_request'])


if __name__ == '__main__':
    unittest.main()
