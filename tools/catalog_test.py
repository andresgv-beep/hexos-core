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


if __name__ == '__main__':
    unittest.main()
