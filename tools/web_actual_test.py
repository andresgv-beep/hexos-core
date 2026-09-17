"""Buscar en la web cuando la pregunta pide un dato de ahora.

La puerta de recovery cubre «buscó y no abrió fuente». Esta cubre lo de antes: no
buscar. «¿Qué versión de Ubuntu es la más actual?» se contestó de memoria, con la
web delante y sin tocarla. Misma figura que la búsqueda en el archivo: lo consulta
HexOS y entra como dato.
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat_backend.memory import ACTUALIDAD, ES_LOCAL, MemoryService


def salta(texto):
    return bool(ACTUALIDAD.search(texto)) and not ES_LOCAL.search(texto)


class PuertaTest(unittest.TestCase):
    def test_la_pregunta_real_que_lo_destapó(self):
        self.assertTrue(salta('pero que version de ubuntu es la mas actual?'))

    def test_preguntas_de_ahora(self):
        for texto in ('cuanto cuesta el iphone 18 pro', 'novedades de python',
                      'que hay de nuevo en linux', 'cual es la ultima version de firefox',
                      'ya salio la 26.04?', 'ultimas noticias de nvidia'):
            with self.subTest(texto):
                self.assertTrue(salta(texto), texto)

    def test_lo_suyo_no_está_en_internet(self):
        # Sus equipos y sus notas no se buscan fuera, por muy «última versión» que digan.
        for texto in ('que version de dsm tiene mi synology', 'revisa los contenedores',
                      'muestrame la ultima nota', 'abre la nota 2',
                      'cual es el ultimo informe del raid', 'estado del disco sda'):
            with self.subTest(texto):
                self.assertFalse(salta(texto), texto)

    def test_una_conversación_normal_no_dispara_una_búsqueda(self):
        for texto in ('hola', 'vale', 'gracias socio', 'que tal va todo'):
            with self.subTest(texto):
                self.assertFalse(salta(texto), texto)


class ServicioTest(unittest.TestCase):
    def servicio(self):
        return MemoryService.__new__(MemoryService)

    def test_entrega_los_resultados_como_dato_y_dice_quién_buscó(self):
        with patch('hexos.agent.chat_backend.memory.web.search',
                   return_value=dict(query='ubuntu', count=1, note='x',
                                     items=[dict(title='Ubuntu 26.04', url='https://ubuntu.com/',
                                                 snippet='…')])):
            paso = self.servicio().recall_web('cual es la ultima version de ubuntu')
        self.assertEqual(paso['tool'], 'web.search')
        self.assertEqual(paso['result']['requested_by'], 'hexos')
        self.assertFalse(paso['failed'])
        # Se conserva la forma que devuelve web.search, sin reinventarla.
        self.assertEqual(paso['result']['items'][0]['url'], 'https://ubuntu.com/')
        # Y deja claro que un titular no es una fuente leída.
        self.assertIn('web_read', paso['result']['note'])

    def test_sin_red_no_tumba_el_turno_y_se_dice(self):
        with patch('hexos.agent.chat_backend.memory.web.search',
                   side_effect=OSError('sin salida a internet')):
            paso = self.servicio().recall_web('cual es la ultima version de ubuntu')
        self.assertTrue(paso['failed'])
        self.assertIn('sin salida a internet', paso['result']['error'])

    def test_si_no_aplica_no_se_llama_a_la_web(self):
        with patch('hexos.agent.chat_backend.memory.web.search') as buscar:
            self.assertIsNone(self.servicio().recall_web('revisa los contenedores del nas'))
            buscar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
