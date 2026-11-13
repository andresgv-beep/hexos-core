"""El selector de grupos y el estado pegajoso.

Lo que se comprueba aquí es que un selector que se equivoca no puede dejar al modelo sin
herramientas, y que el conjunto no baila en cada turno: cada cambio obliga a reprocesar
el prompt entero, que es el 86% del coste del turno.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent import catalog, tool_groups


class InterpretarTest(unittest.TestCase):
    def test_una_lista_de_grupos_conocidos_vale(self):
        self.assertEqual(tool_groups.interpretar('["archivos", "notas"]'), ['archivos', 'notas'])

    def test_vacio_es_una_respuesta_valida(self):
        """Conversar sin herramientas es legítimo: [] no es lo mismo que no saber."""
        self.assertEqual(tool_groups.interpretar('[]'), [])

    def test_sin_comillas_tambien_se_entiende_y_se_valida_igual(self):
        # El E4B contesta a veces `[sistema]`: correcto, pero no es JSON y se tiraba.
        self.assertEqual(tool_groups.interpretar('[sistema]'), ['sistema'])
        self.assertEqual(tool_groups.interpretar('[ sistema , archivos ]'), ['sistema', 'archivos'])
        self.assertIsNone(tool_groups.interpretar('[inventado]'))
        self.assertIsNone(tool_groups.interpretar('[sistema] y algo más'))
        self.assertIsNone(tool_groups.interpretar('[archivos]', 'chat'))

    def test_lo_que_no_se_entiende_devuelve_none(self):
        for raw in ('no sé', '', None, '{"grupo": "archivos"}', '["archivos"', 42):
            self.assertIsNone(tool_groups.interpretar(raw), raw)

    def test_un_grupo_inventado_invalida_la_respuesta_entera(self):
        """A medias es peor: dejaría fuera lo que el turno necesitaba."""
        self.assertIsNone(tool_groups.interpretar('["archivos", "inventado"]'))

    def test_el_nucleo_no_se_pide_porque_va_siempre(self):
        self.assertIsNone(tool_groups.interpretar('["nucleo"]'))

    def test_acepta_el_bloque_de_codigo_que_a_veces_sale(self):
        self.assertEqual(tool_groups.interpretar('```json\n["notas"]\n```'), ['notas'])

    def test_no_repite_grupos(self):
        self.assertEqual(tool_groups.interpretar('["notas", "notas"]'), ['notas'])


class PegajososTest(unittest.TestCase):
    def setUp(self):
        self.p = tool_groups.Pegajosos(olvido=2)

    def test_al_empezar_solo_esta_el_nucleo(self):
        self.assertEqual(self.p.activos(), [])
        self.assertEqual(sorted(self.p.herramientas()), sorted(catalog.GROUPS[catalog.ALWAYS]))

    def test_lo_pedido_sigue_activo_unos_turnos_y_luego_sale(self):
        self.p.pedir(['archivos'])
        self.assertEqual(self.p.activos(), ['archivos'])
        for _ in range(2):
            self.p.nuevo_turno()
        self.assertEqual(self.p.activos(), ['archivos'], 'sale demasiado pronto')
        self.p.nuevo_turno()
        self.assertEqual(self.p.activos(), [], 'deberia haber caducado')

    def test_usar_una_herramienta_activa_su_grupo(self):
        """Vía de escape: el historial reinyecta llamadas de grupos que ya no están."""
        self.p.usada('note.save')
        self.assertIn('notas', self.p.activos())
        self.assertIn('note.save', self.p.herramientas())

    def test_usar_una_del_nucleo_no_añade_grupos(self):
        self.p.usada('history.recent')
        self.assertEqual(self.p.activos(), [])

    def test_usarla_otra_vez_renueva_el_plazo(self):
        self.p.pedir(['notas'])
        for _ in range(2):
            self.p.nuevo_turno()
        self.p.usada('note.get')
        for _ in range(2):
            self.p.nuevo_turno()
        self.assertEqual(self.p.activos(), ['notas'])

    def test_multimedia_trae_archivos_consigo(self):
        self.p.pedir(['multimedia'])
        self.assertIn('nas.find', self.p.herramientas())

    def test_reset_lo_deja_como_al_principio(self):
        self.p.pedir(['archivos', 'notas'])
        self.p.reset()
        self.assertEqual(self.p.activos(), [])


class SelectorTest(unittest.TestCase):
    class Falso:
        """Un runtime de mentira: no hace falta modelo para probar el contrato."""
        def __init__(self, raw, finish='eos'):
            self.raw, self.finish, self.enviado = raw, finish, None
            self.template = self
        def render(self, **kw):
            return 'prompt'
        def send(self, prompt, image=None, auxiliar=False):
            self.enviado = (prompt, auxiliar)
        def event(self):
            return (None, None, '0', None, self.finish), self.raw

    def test_pregunta_en_la_sesion_auxiliar(self):
        r = self.Falso('["archivos"]')
        self.assertEqual(tool_groups.elegir(r, 'hola', 'busca el pdf', 'agente'), ['archivos'])
        self.assertTrue(r.enviado[1], 'la elección no puede ensuciar la conversación')

    def test_un_grupo_de_la_otra_ventana_no_cuela(self):
        """Por defecto se conversa: pedir el NAS en charla no se da por bueno."""
        self.assertIsNone(tool_groups.elegir(self.Falso('["archivos"]'), '', 'busca el pdf'))

    def test_si_se_corta_la_generacion_no_se_fia(self):
        self.assertIsNone(tool_groups.elegir(self.Falso('["archivos"]', finish='max_tokens'), '', 'x'))

    def test_si_el_runtime_revienta_no_tumba_el_turno(self):
        class Rota(self.Falso):
            def send(self, *a, **k):
                raise RuntimeError('sin modelo')
        self.assertIsNone(tool_groups.elegir(Rota('[]'), '', 'x'))


class VentanasTest(unittest.TestCase):
    """Dos espacios de trabajo. La ventana la elige la persona y acota lo que el selector
    puede pedir: es mecánico y no se equivoca, que es lo que este modelo necesita."""

    def test_los_grupos_se_reparten_entre_las_dos_sin_dejar_ninguno(self):
        en_ventanas = {g for grupos in catalog.WINDOWS.values() for g in grupos}
        self.assertEqual(en_ventanas | {catalog.ALWAYS}, set(catalog.GROUPS))

    def test_ninguna_ventana_repite_grupo_de_la_otra(self):
        chat, agente = set(catalog.WINDOWS['chat']), set(catalog.WINDOWS['agente'])
        self.assertEqual(chat & agente, set())

    def test_en_charla_no_se_puede_pedir_el_nas_ni_inventandolo(self):
        self.assertIsNone(tool_groups.interpretar('["archivos"]', 'chat'))
        self.assertEqual(tool_groups.interpretar('["archivos"]', 'agente'), ['archivos'])

    def test_la_terminal_es_de_la_ventana_de_agente(self):
        self.assertEqual(catalog.group_of('terminal.read'), 'sistema')
        self.assertIn('sistema', catalog.WINDOWS['agente'])
        self.assertNotIn('terminal.read', catalog.tools_for([]))

    def test_la_memoria_esta_en_las_dos(self):
        """Si no, serían dos asistentes que no se conocen."""
        for herramienta in ('history.recent', 'profile.recall'):
            self.assertIn(herramienta, catalog.tools_for([]))

    def test_lo_vivo_de_la_otra_ventana_no_se_declara(self):
        p = tool_groups.Pegajosos()
        p.pedir(['archivos'])
        self.assertIn('nas.find', p.herramientas('agente'))
        self.assertNotIn('nas.find', p.herramientas('chat'))

    def test_una_ventana_inventada_se_rechaza(self):
        with self.assertRaises(ValueError):
            catalog.groups_in('inventada')


class AtributosDelAgenteTest(unittest.TestCase):
    """La ventana se guarda en el agente, y el agente ya tiene nombres ocupados.

    Pasó: `self.window = 'chat'` se comió el método `window()` que recorta el historial,
    y el primer turno moría en `context.prepare` con «'str' object is not callable». El
    estado respondía igual, así que no se notaba hasta escribir un mensaje.
    """

    def test_la_ventana_no_pisa_ningun_metodo_del_agente(self):
        from hexos.agent.chat_backend.agent import Agent
        self.assertTrue(callable(getattr(Agent, 'window', None)),
                        'window() es el recorte de historial y tiene que seguir siendo un método')
        for nombre in ('ventana', 'grupos'):
            self.assertFalse(hasattr(Agent, nombre),
                             f'{nombre} ya existe en Agent: elige otro nombre o lo rompes')


if __name__ == '__main__':
    unittest.main()
