#!/usr/bin/python3
"""La temperatura se decide por lo que toca escribir; las herramientas, siempre sin azar."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.native import REVISION_DE_CODIGO, temperatura_del_turno


class TemperaturaTest(unittest.TestCase):
    def test_un_turno_que_pide_herramientas_va_sin_azar(self):
        self.assertEqual(temperatura_del_turno('agente', ['sistema']), 0)
        self.assertEqual(temperatura_del_turno('chat', ['notas']), 0)

    def test_si_el_selector_no_supo_tampoco_hay_azar(self):
        self.assertEqual(temperatura_del_turno('chat', None), 0)

    def test_charlar_lleva_mas_que_el_agente(self):
        self.assertGreater(temperatura_del_turno('chat', []), temperatura_del_turno('agente', []))
        self.assertGreater(temperatura_del_turno('agente', []), 0)

    def test_retocar_codigo_lleva_la_suya_aunque_el_selector_pida_grupos(self):
        peticion = REVISION_DE_CODIGO + ' en la ventana de código. Aplica esta petición…'
        self.assertGreater(temperatura_del_turno('agente', ['proyecto'], peticion), 0)

    def test_se_ajusta_por_entorno_y_con_tope(self):
        with mock.patch.dict(os.environ, HEXOS_TEMP_CHAT='0'):
            self.assertEqual(temperatura_del_turno('chat', []), 0)
        with mock.patch.dict(os.environ, HEXOS_TEMP_CHAT='9'):
            self.assertEqual(temperatura_del_turno('chat', []), 1.5)
        with mock.patch.dict(os.environ, HEXOS_TEMP_CHAT='mucho'):
            self.assertEqual(temperatura_del_turno('chat', []), 0.7)

    def test_el_envoltorio_de_la_interfaz_sigue_empezando_igual(self):
        fuente = (Path(__file__).resolve().parents[1] / 'interfaz/lib/helios/preview.ts').read_text()
        self.assertIn(REVISION_DE_CODIGO, fuente)


if __name__ == '__main__':
    unittest.main()
