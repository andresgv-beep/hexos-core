"""Fichas de técnica: se eligen por lo que usa el proyecto y se dan una vez por contexto."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hexos.agent import tecnicas


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-tecnicas-')
        self.casa = Path(self.tmp.name)
        parche = mock.patch.dict(os.environ, {'HEXOS_TECNICAS_HOME': str(self.casa / 'mias')})
        parche.start()
        self.addCleanup(parche.stop)
        self.addCleanup(self.tmp.cleanup)
        self.proyecto = self.casa / 'proyecto'
        self.proyecto.mkdir()

    def nombres(self, vistas, ya=()):
        return [f['nombre'] for f in tecnicas.elegir(vistas, ya)]


class DeSerieTest(Base):
    def test_las_de_serie_tienen_forma_y_caben(self):
        fichas = tecnicas.cargar()
        self.assertGreaterEqual(len(fichas), 5)
        for ficha in fichas:
            with self.subTest(ficha=ficha['nombre']):
                self.assertTrue(ficha['titulo'] and ficha['aplica'])
                self.assertLessEqual(len(ficha['cuerpo']), tecnicas.MAX_FICHA + 30)
                self.assertNotIn('recortada', ficha['cuerpo'])

    def test_se_eligen_por_lo_que_importa_el_proyecto(self):
        (self.proyecto / 'main.py').write_text('import tkinter as tk\nfrom tkinter import ttk\nimport sqlite3\n')
        vistas = tecnicas.senales(self.proyecto)
        self.assertLessEqual({'tkinter', 'sqlite3', '.py'}, vistas)
        elegidas = self.nombres(vistas)
        self.assertEqual(elegidas[:2], ['tkinter-reparto', 'sqlite-migrar'])
        self.assertIn('interfaz-jerarquia', elegidas)
        self.assertNotIn('pyqt6-reparto', elegidas)

    def test_un_proyecto_vacio_las_recibe_por_lo_que_se_pide(self):
        vistas = tecnicas.senales(self.proyecto, 'hazme una calculadora con interfaz moderna en PyQt6')
        self.assertEqual(self.nombres(vistas)[0], 'pyqt6-reparto')
        self.assertEqual(self.nombres(tecnicas.senales(self.proyecto, 'ordena esta lista de números')), [])

    def test_pedir_algo_moderno_trae_como_elegir_la_libreria(self):
        # El 15/11, a «una calculadora pro, y que se vea moderna», el 26B eligió Tkinter, que no
        # redondea botones, teniendo PyQt6 instalado, y acabó mandando instalar un paquete con pip.
        vistas = tecnicas.senales(self.proyecto, 'necesito que me creas una calculadora pro, y que se vea moderna')
        self.assertEqual(self.nombres(vistas)[:2], ['interfaz-libreria', 'interfaz-jerarquia'])
        self.assertIn('border-radius', tecnicas.bloque(tecnicas.elegir(vistas)))

    def test_lo_que_no_es_codigo_de_la_persona_no_cuenta(self):
        (self.proyecto / 'node_modules').mkdir()
        (self.proyecto / 'node_modules' / 'x.py').write_text('import tkinter\n')
        self.assertNotIn('tkinter', tecnicas.senales(self.proyecto))

    def test_cada_ficha_se_da_una_vez_y_con_tope(self):
        vistas = {'tkinter', 'pyqt6', 'sqlite3', 'interfaz'}
        primeras = self.nombres(vistas)
        self.assertEqual(len(primeras), tecnicas.MAX_POR_VEZ)
        resto = self.nombres(vistas, ya=primeras)
        self.assertTrue(resto and not set(resto) & set(primeras))
        self.assertEqual(self.nombres(vistas, ya=primeras + resto), [])

    def test_el_bloque_dice_que_son_para_aplicar(self):
        texto = tecnicas.bloque(tecnicas.elegir({'sqlite3'}))
        self.assertIn('TÉCNICAS', texto)
        self.assertIn('PRAGMA user_version', texto)
        self.assertEqual(tecnicas.bloque([]), '')


class DeLaPersonaTest(Base):
    def escribir(self, nombre, texto):
        (self.casa / 'mias').mkdir(exist_ok=True)
        (self.casa / 'mias' / nombre).write_text(texto)

    def test_una_ficha_suya_se_suma_y_otra_sustituye_a_la_de_serie(self):
        self.escribir('cuda-kernels.md', '# Kernels CUDA\naplica: .cu, cuda\n\nUn bloque por SM, no más.\n')
        self.escribir('tkinter-reparto.md', '# Tkinter a mi manera\naplica: tkinter\n\nSiempre tema oscuro.\n')
        self.assertEqual(self.nombres({'.cu'}), ['cuda-kernels'])
        mia = next(f for f in tecnicas.cargar() if f['nombre'] == 'tkinter-reparto')
        self.assertEqual((mia['titulo'], mia['cuerpo']), ('Tkinter a mi manera', 'Siempre tema oscuro.'))

    def test_un_fichero_vacio_apaga_la_de_serie_y_uno_roto_no_rompe_nada(self):
        self.escribir('sqlite-migrar.md', '')
        self.escribir('rota.md', 'esto no es una ficha')
        self.assertNotIn('sqlite-migrar', [f['nombre'] for f in tecnicas.cargar()])
        self.assertNotIn('rota', [f['nombre'] for f in tecnicas.cargar()])

    def test_una_ficha_larguisima_se_corta(self):
        self.escribir('larga.md', '# Larga\naplica: larga\n\n' + 'una línea de relleno\n' * 400)
        larga = next(f for f in tecnicas.cargar() if f['nombre'] == 'larga')
        self.assertLess(len(larga['cuerpo']), tecnicas.MAX_FICHA + 30)
        self.assertIn('recortada', larga['cuerpo'])


class EnElTurnoTest(Base):
    def test_van_con_el_turno_una_vez_y_vuelven_al_reconstruir(self):
        from hexos.agent.chat import Agent
        from hexos.agent.chat_backend.state import TurnState

        class Runtime:
            def call(self, request): pass
            def generate(self, messages): return {'reply': 'Hecho.', 'work': None}
        with mock.patch.dict(os.environ, {'HEXOS_PROJECTS_HOME': str(self.casa / 'proyectos')}), \
                mock.patch.object(Path, 'home', return_value=self.casa):
            agente = Agent(self.casa / 'hexos', Runtime())
            agente.set_window('agente')
            (self.proyecto / 'main.py').write_text('import tkinter as tk\n')
            agente.create_project('Inventario', str(self.proyecto))
            turno = TurnState(text='añade un buscador', image=None, model_request='añade un buscador', transcript=None)
            with agente.store() as store:
                primero = agente.context.tecnicas_del_turno(store, turno, True)
                segundo = agente.context.tecnicas_del_turno(store, turno, False)
                turno.text = 'guárdalo en sqlite'
                tercero = agente.context.tecnicas_del_turno(store, turno, False)
                tras_corte = agente.context.tecnicas_del_turno(store, turno, True)
                agente.set_window('chat')
                en_chat = agente.context.tecnicas_del_turno(store, turno, True)
        self.assertIn('Tkinter: repartir el espacio', primero)
        self.assertEqual(segundo, '')
        self.assertIn('SQLite', tercero)
        self.assertNotIn('Tkinter: repartir', tercero)
        self.assertIn('Tkinter: repartir el espacio', tras_corte)
        self.assertEqual(en_chat, '')


if __name__ == '__main__':
    unittest.main()
