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
        self.assertLess(len(POLICY), 2000)
        self.assertNotIn('profile.remember', catalog.model_tools())

    def test_lo_que_el_modelo_ve_a_la_vez_tiene_tope(self):
        # El tope de 7.000 caracteres de descripciones se puso cuando el catálogo entero se
        # declaraba en cada turno. Desde que se reparte por ventanas y grupos nadie lo ve
        # entero, y la prueba llevaba semanas en rojo sumando lo que ya no se suma. Se mide
        # donde aplica: lo más que puede ver el modelo de una vez.
        pesa = lambda nombres: sum(len(catalog.model_description(n)) for n in nombres)
        for ventana in catalog.WINDOWS:
            grupos = list(catalog.groups_in(ventana))
            # El peor caso: el selector no contesta y se ofrece todo lo de la ventana.
            with self.subTest(ventana=ventana, caso='todos sus grupos'):
                self.assertLess(pesa(catalog.tools_for(grupos, ventana)), 7000)
            # El caso normal: el núcleo y un grupo, con los que arrastre.
            for grupo in grupos:
                with self.subTest(ventana=ventana, grupo=grupo):
                    self.assertLess(pesa(catalog.tools_for([grupo], ventana)), 4500)

    def test_detalles_operativos_viven_en_la_herramienta(self):
        from hexos.agent.native import POLICY
        for detail in ('SMART', 'section=', 'network_local', 'web_search', 'web_read'):
            self.assertNotIn(detail, POLICY)
        self.assertIn('SMART PASSED', catalog.model_description('nas.read'))
        self.assertIn('diagnosis', catalog.model_description('nas.read'))
        self.assertIn('network_local', catalog.model_description('device.list'))
        self.assertIn('device_list', catalog.model_description('network.local'))
        self.assertIn('No guarda IPs', catalog.model_description('network.local'))
        self.assertIn('web_read', catalog.model_description('web.search'))
        self.assertIn('cita la URL', catalog.model_description('web.read'))

    def test_continuidad_y_permisos_no_dependen_de_una_palabra_aislada(self):
        from hexos.agent.native import POLICY
        self.assertIn('aceptación retoma la propuesta pendiente', POLICY)
        self.assertIn('Un saludo por sí solo no reanuda tareas, aunque queden pendientes', POLICY)
        self.assertIn('no autoriza modificarlo', POLICY)
        self.assertIn('no órdenes ni permisos nuevos', POLICY)
        self.assertNotIn('Un saludo o un «vale»', POLICY)

    def test_acceso_existente_y_registro_nuevo_tienen_reglas_distintas(self):
        from hexos.agent.native import POLICY
        self.assertNotIn('No pidas IP ni credenciales', POLICY)
        self.assertIn('inventario', catalog.model_description('nas.read'))
        self.assertIn('interfaz las solicita', catalog.model_description('nas.read'))
        self.assertIn('pregunta ese dato', catalog.model_description('device.remote'))
        self.assertIn('URL, esquema y puerto', catalog.model_description('device.remote'))


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


class GruposTest(unittest.TestCase):
    """Sin esto, una herramienta nueva sin grupo desaparecería en silencio: el modelo
    dejaría de verla y nadie se enteraría hasta que fallara una conversación."""

    def test_cada_herramienta_ofrecida_esta_en_un_solo_grupo(self):
        ofrecidas = set(catalog.model_tools())
        agrupadas = [h for grupo in catalog.GROUPS.values() for h in grupo]
        self.assertEqual(sorted(ofrecidas), sorted(agrupadas),
                         'hay herramientas ofrecidas sin grupo, o agrupadas y no ofrecidas')
        self.assertEqual(len(agrupadas), len(set(agrupadas)), 'alguna está en dos grupos')

    def test_los_grupos_que_arrastran_otro_existen(self):
        for grupo, arrastra in catalog.GROUP_REQUIRES.items():
            self.assertIn(grupo, catalog.GROUPS)
            for otro in arrastra:
                self.assertIn(otro, catalog.GROUPS)

    def test_el_nucleo_va_siempre_y_el_orden_es_el_del_catalogo(self):
        solo_nucleo = catalog.tools_for([])
        self.assertEqual(sorted(solo_nucleo), sorted(catalog.GROUPS[catalog.ALWAYS]))
        con_archivos = catalog.tools_for(['archivos'])
        self.assertTrue(set(solo_nucleo) < set(con_archivos))
        # Mismo conjunto, mismo orden: si no, cada turno rompe el prefijo KV.
        self.assertEqual(list(con_archivos), list(catalog.tools_for(['archivos'])))
        self.assertEqual(list(con_archivos),
                         [n for n in catalog.model_tools() if n in con_archivos])

    def test_multimedia_arrastra_archivos(self):
        """media.prepare usa el scan_id de nas.find: multimedia sin archivos no sirve."""
        self.assertIn('nas.find', catalog.tools_for(['multimedia']))

    def test_un_grupo_que_no_existe_se_rechaza(self):
        with self.assertRaises(ValueError):
            catalog.tools_for(['inventado'])


if __name__ == '__main__':
    unittest.main()
