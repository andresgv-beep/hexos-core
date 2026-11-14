#!/usr/bin/python3
"""El registro del mensaje: se reconoce una palabra de la lista o no se hace nada."""
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent import registro


class Runtime:
    class template:
        @staticmethod
        def render(**datos): return datos['messages'][1]['content']
    def __init__(self, salida, fin='eos'): self.salida, self.fin, self.enviado = salida, fin, []
    def send(self, prompt, auxiliar=False): self.enviado.append((prompt, auxiliar))
    def event(self): return (0, 0, 0, 0, self.fin), self.salida


class RegistroTest(unittest.TestCase):
    def test_reconoce_la_palabra_aunque_venga_adornada(self):
        for crudo, esperado in (('broma', 'broma'), (' Broma.\n', 'broma'), ('"técnico"', 'tecnico'),
                                ('**reflexión**', 'reflexion'), ('charla', 'charla')):
            self.assertEqual(registro.interpretar(crudo), esperado, crudo)

    def test_lo_que_no_es_de_la_lista_no_vale(self):
        for crudo in ('', 'es una broma', 'sarcasmo', None, 'broma, charla'):
            self.assertIsNone(registro.interpretar(crudo), crudo)

    def test_se_pregunta_en_la_sesion_auxiliar_y_un_corte_no_se_fia(self):
        runtime = Runtime('broma')
        self.assertEqual(registro.elegir(runtime, 'hola', 'dominaremos el mundo'), 'broma')
        self.assertTrue(runtime.enviado[0][1])
        self.assertIn('dominaremos el mundo', runtime.enviado[0][0])
        self.assertIsNone(registro.elegir(Runtime('broma', fin='max_tokens'), '', 'x'))

    def test_una_broma_pide_seguirla_corta_y_lo_tecnico_baja_la_temperatura(self):
        self.assertIn('dos o tres frases', registro.bloque('broma'))
        self.assertIn('dato de HexOS', registro.bloque('broma'))
        self.assertEqual(registro.bloque(None), '')
        self.assertGreater(registro.temperatura('broma', 0.7), registro.temperatura('tecnico', 0.7))
        self.assertEqual(registro.temperatura(None, 0.7), 0.7)


if __name__ == '__main__':
    unittest.main()
