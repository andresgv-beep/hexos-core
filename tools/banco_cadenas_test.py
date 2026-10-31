"""El NAS simulado del banco de cadenas habla el mismo formato que el real, sin GPU."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hexos.agent.chat import Agent
from tools import banco_cadenas as banco

BUENA = '/volume4/multimedia 3/multimedia/marvel/Capitana Marvel [1080p].mkv'
LISTADO = {'synology 1': [[BUENA, 8 * banco.GB], ['/volume4/multimedia 3/multimedia/peliculas/Interstellar.mkv', 12 * banco.GB],
                          ['/volume1/multimedia 1/Multimedia/peliculas/Avatar.mkv', 20 * banco.GB]],
           'synology home': [['/volume1/multimedia/peliculas/Otra.mkv', 3 * banco.GB]]}


class Runtime:
    def __init__(self, respuestas=()):
        self.respuestas = list(respuestas)
        self.tools = [dict(function=dict(name='nas_find')), dict(function=dict(name='note_save'))]
        self.vistas = []

    def call(self, request):
        pass

    def generate(self, messages):
        self.vistas.append([t['function']['name'] for t in self.tools])
        return dict(reply=self.respuestas.pop(0) if self.respuestas else 'Hecho.', work=None)


class NasSimuladoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.nas = banco.NAS(LISTADO)
        self.media = self.root / 'media.json'
        self.media.write_text(json.dumps(dict(enabled=True, device='synology 1', profiles=[], files={})))

    def herramienta(self, operacion, **kw):
        return banco.dependencias(self.root, self.nas).nas_files(self.root, operation=operacion, **kw)

    def test_ruta_inexistente_es_error_de_cobertura_como_en_el_nas(self):
        r = self.herramienta('find', device='synology 1', roots=['/volume1/multimedia', '/volume4/multimedia 3/multimedia'],
                             extensions=['mkv'])
        self.assertEqual(r['coverage']['errors'][0]['reason'], 'invalid_or_unreadable_root')
        self.assertIn(BUENA, [i['path'] for i in r['items']])

    def test_descubrimiento_incluye_carpetas_sin_permiso_y_no_mezcla_equipos(self):
        r = self.herramienta('find', device='synology 1', extensions=['mkv'])
        self.assertFalse(r['complete'])
        self.assertIn('/volume1/garage', [e['path'] for e in r['coverage']['errors']])
        self.assertNotIn('Otra.mkv', [i['name'] for i in r['items']])

    def test_navegar_compartidas_y_carpetas(self):
        self.assertIn('/volume4/multimedia 3/multimedia/marvel',
                      [i['path'] for i in self.herramienta('browse', device='synology 1',
                                                           path='/volume4/multimedia 3/multimedia')['items']])
        self.assertIn('/volume1/Compartido', [i['path'] for i in self.herramienta('shares', device='synology 1')['items']])
        carpetas = self.herramienta('directories', device='synology 1', query='marvel')
        self.assertIn('/volume4/multimedia 3/multimedia/marvel', [i['path'] for i in carpetas['items']])

    def test_query_encuentra_la_carpeta_y_no_solo_el_nombre(self):
        rutas = [i['path'] for i in self.herramienta('find', device='synology 1', query='marvel', extensions=['mkv'])['items']]
        self.assertEqual(rutas, [BUENA])
        rutas = [i['path'] for i in self.herramienta('find', device='synology 1', query='multimedia/peliculas',
                                                     extensions=['mkv'])['items']]
        self.assertEqual(len(rutas), 2)

    def test_busqueda_vacia_senala_la_carpeta_de_otra_raiz(self):
        self.herramienta('find', device='synology 1', extensions=['mkv'], roots=['/volume4/multimedia 3/multimedia'])
        r = self.herramienta('find', device='synology 1', extensions=['mkv'], query='marvel',
                             roots=['/volume1/multimedia 1/Multimedia'])
        self.assertEqual(r['total_matches'], 0)
        self.assertEqual(r['falta_por_mirar'], ['/volume4/multimedia 3/multimedia/marvel'])
        r = self.herramienta('find', device='synology 1', extensions=['mkv'], query='spider-man',
                             roots=['/volume4/multimedia 3/multimedia/marvel'])
        self.assertIn('sin roots', r['falta_por_mirar'])
        r = self.herramienta('find', device='synology 1', extensions=['mkv'], query='spider-man')
        self.assertNotIn('falta_por_mirar', r)

    def test_roots_vacio_es_buscar_en_todo(self):
        self.assertIn(BUENA, [i['path'] for i in self.herramienta('find', device='synology 1', roots=[], extensions=['mkv'])['items']])

    def test_max_bytes_cero_avisa_y_no_manda_a_otra_parte(self):
        r = self.herramienta('find', device='synology 1', extensions=['mkv'], max_bytes=0,
                             roots=['/volume4/multimedia 3/multimedia/marvel'])
        self.assertIn('vacíos', r['aviso'])
        self.assertNotIn('falta_por_mirar', r)

    def test_abrir_y_leer_documento(self):
        hallado = self.herramienta('find', device='synology 1', query='notas-raid')
        abierto = self.herramienta('file_open', scan_id=hallado['scan_id'], path=banco.DOCUMENTO['path'])
        self.assertIn('sdc', self.herramienta('file_read', file_id=abierto['file_id'])['text'])

    def test_la_web_bloquea_una_fuente_y_deja_la_otra(self):
        with self.assertRaises(ValueError):
            banco.leer_web(banco.WEB['mala'])
        self.assertIn('2026.10.3', banco.leer_web(banco.WEB['buena'])['text'])

    def test_empuja_hasta_cumplir_y_el_catalogo_vuelve_entero(self):
        estado = []
        caso = banco.Caso('x', ['Hazlo'], ('nas.find',), lambda root, reply: (len(estado) == 2 or bool(estado.append(1)), ''))
        runtime = Runtime()
        with mock.patch.object(banco, 'preparar', lambda root, media: root.mkdir(parents=True, exist_ok=True)):
            fila = banco.ejecutar(caso, self.root / 'caso', runtime, self.nas, self.media, solo_grupo=True)
        self.assertTrue(fila['ok'])
        self.assertEqual(fila['empujones'], 2)
        self.assertEqual(runtime.vistas[0], ['nas_find'])
        self.assertEqual(len(runtime.tools), 2)

    def test_resumen_cuenta_sin_ayuda(self):
        filas = [dict(caso='a', ok=True, empujones=0, llamadas=2, fallos=0, repetidas=0, segundos=1, detalle='', herramientas=[], charla=[]),
                 dict(caso='b', ok=True, empujones=1, llamadas=3, fallos=1, repetidas=1, segundos=3, detalle='', herramientas=[], charla=[])]
        resumen, texto = banco.resumir(filas, 'catalogo-entero')
        self.assertEqual((resumen['cumplidos'], resumen['sin_ayuda'], resumen['fallos']), (2, 1, 1))
        self.assertIn('| b | sí | 1 |', texto)


if __name__ == '__main__':
    unittest.main()
