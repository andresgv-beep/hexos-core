"""El catálogo declarado al motor: si un tipo no se sabe traducir, el servidor
no arranca. Eso tiene que fallar aquí, no delante de la persona."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent import catalog


class DeclarablesTest(unittest.TestCase):
    """Un tipo que el motor no sabe declarar tumba el servidor al arrancar, no en
    una prueba. Por eso el catálogo entero se comprueba aquí."""

    def test_todo_argumento_del_catalogo_se_puede_declarar(self):
        from hexos.agent.native import NativeRuntime
        for nombre, spec in catalog.TOOLS.items():
            for campo, tipo in (spec['required'] | spec['optional']).items():
                with self.subTest(herramienta=nombre, campo=campo):
                    self.assertIn('type', NativeRuntime.JSON_TYPE(tipo, nombre, campo))

    def test_un_tipo_inventado_se_señala_con_su_herramienta(self):
        from hexos.agent.native import NativeRuntime
        with self.assertRaises(ValueError) as e:
            NativeRuntime.JSON_TYPE('fecha', 'note.save', 'cuando')
        self.assertIn('note.save.cuando', str(e.exception))
        self.assertIn('bool', str(e.exception))

    def test_el_contrato_nativo_cabe_sin_duplicar_el_manual(self):
        from hexos.agent.native import POLICY
        descriptions = [catalog.model_description(name) for name in catalog.model_tools()]
        self.assertLess(len(POLICY), 3500)
        self.assertLess(sum(map(len, descriptions)), 7000)
        self.assertNotIn('profile.remember', catalog.model_tools())


class VerbosDeclaradosTest(unittest.TestCase):
    """Una herramienta que cambia algo y no declara con qué palabras se canta se
    queda fuera de las redes en silencio. Pasó con note.show y note.hide."""

    def test_toda_escritura_declara_sus_formas(self):
        sin = [n for n, s in catalog.TOOLS.items()
               if s['effect'].startswith('write') and not s['announces']]
        self.assertEqual(sin, [], 'declara announces=(infinitivo, participio, presente) en spec')

    def test_note_show_y_note_hide_cuentan_como_acción(self):
        # Son 'read' para el almacén, pero cambian lo que la persona ve: si no
        # estuvieran aquí, «te muestro la nota» no lo comprobaría nadie.
        for herramienta in ('note.show', 'note.hide'):
            with self.subTest(herramienta):
                self.assertTrue(catalog.TOOLS[herramienta]['announces'])

    def test_las_formas_vienen_en_los_tres_tiempos(self):
        for nombre, spec in catalog.TOOLS.items():
            for forma in spec['announces']:
                with self.subTest(nombre):
                    self.assertEqual(len(forma), 3)

    def test_una_forma_mal_declarada_se_rechaza_al_definirla(self):
        with self.assertRaises(ValueError):
            catalog.spec('x', effect='write', announces=(('abrir', 'abiert'),))


if __name__ == '__main__':
    unittest.main()
