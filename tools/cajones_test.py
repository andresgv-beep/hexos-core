"""Cajones de herramientas: el modelo ve el núcleo y abre el resto cuando lo necesita.

Con las 51 herramientas a la vista, el 03/11 usó media_start con el plan de una
desinstalación. Aquí se comprueba que un cajón cerrado no se ejecuta a ciegas, que
abrirlo no cambia el prompt con la conversación viva y que se cierra al empezar de cero.
"""
from collections import deque
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent import catalog, tool_digest
from hexos.agent.native import DrawerClosed, NativeRuntime


def llamada(alias, **argumentos):
    cuerpo = ','.join(k + ':<|"|>' + v + '<|"|>' for k, v in argumentos.items())
    return '<|tool_call>call:' + alias + '{' + cuerpo + '}<tool_call|>'


class CatalogoTest(unittest.TestCase):
    def test_cada_herramienta_esta_en_el_nucleo_o_en_un_solo_cajon(self):
        en_cajones = [t for cajon in catalog.DRAWERS.values() for t in cajon['tools']]
        self.assertEqual(len(en_cajones), len(set(en_cajones)))
        for herramienta in en_cajones:
            with self.subTest(herramienta):
                self.assertIn(herramienta, catalog.model_tools())
        self.assertEqual(set(catalog.core_tools()) | set(en_cajones), set(catalog.model_tools()))

    def test_el_nucleo_es_corto_y_tiene_lo_del_incidente(self):
        nucleo = catalog.core_tools()
        self.assertLessEqual(len(nucleo), 14)
        for herramienta in ('tools.open', 'terminal.read', 'system.package_plan', 'history.search'):
            self.assertIn(herramienta, nucleo)
        self.assertNotIn('media.start', nucleo)

    def test_tools_open_nombra_todos_los_cajones(self):
        descripcion = catalog.model_description('tools.open')
        for cajon in catalog.DRAWERS:
            self.assertIn(cajon + ' (', descripcion)

    def test_el_contenido_usa_los_nombres_que_ve_el_modelo(self):
        contenido = catalog.drawer_contents('video')
        self.assertIn('media_start', [t['name'] for t in contenido['tools']])
        self.assertIn('media_options', contenido['guide'])

    def test_la_ruta_json_antigua_lleva_el_catalogo_entero_sin_cajones(self):
        texto = catalog.render()
        self.assertIn('media.start:', texto)
        self.assertNotIn('tools.open:', texto)


class MotorTest(unittest.TestCase):
    def runtime(self, *completions):
        runtime = NativeRuntime.__new__(NativeRuntime)
        runtime.names = {n.replace('.', '_'): n for n in catalog.model_tools()}
        runtime.tools = [{'type': 'function', 'function': {'name': alias, 'description': '',
                          'parameters': {}}} for alias in runtime.names]
        runtime.open_drawers = set()
        runtime.declared_drawers = frozenset()
        runtime.pending = deque()
        runtime.messages = []
        runtime.current = None
        runtime.template = SimpleNamespace(render=Mock(return_value='prompt'))
        runtime.send = lambda prompt, image: prompt.encode()
        salidas = iter(completions)
        def event():
            salida = next(salidas)
            # Una llamada para en la respuesta de herramienta; una respuesta, en eos.
            return ['0', '1', '1', '1', 'stop' if '<|tool_call>' in salida else 'eos'], salida
        runtime.event = event
        runtime.notify = Mock()
        return runtime

    def test_al_empezar_solo_se_declara_el_nucleo(self):
        runtime = self.runtime('Hola.')
        runtime.generate([{'role': 'user', 'content': 'hola'}])
        tools = runtime.template.render.call_args.kwargs['tools']
        declaradas = {runtime.names[t['function']['name']] for t in tools}
        self.assertEqual(declaradas, set(catalog.core_tools()))

    def test_un_cajon_cerrado_no_se_ejecuta_y_se_abre_con_sus_herramientas(self):
        runtime = self.runtime(llamada('media_start', plan_id='abc'))
        with self.assertRaises(DrawerClosed) as error:
            runtime.generate([{'role': 'user', 'content': 'ya está confirmado'}])
        self.assertFalse(runtime.pending)
        self.assertIsNone(runtime.current)
        self.assertIn('no se ha ejecutado nada', error.exception.repair)
        self.assertIn('media_start', error.exception.repair)
        self.assertIn('media_options', error.exception.repair)
        self.assertIn('video', runtime.open_drawers)
        # Ni la llamada rechazada ni el aviso entran como turno del asistente.
        self.assertNotIn('tool_calls', runtime.messages[-1])

    def test_abierto_se_llama_sin_cambiar_lo_declarado(self):
        runtime = self.runtime('Lo miro.', llamada('media_jobs'))
        runtime.generate([{'role': 'user', 'content': 'hola'}])
        self.assertEqual(runtime.open_drawer('video')['drawer'], 'video')
        decision = runtime.generate([{'role': 'user', 'content': '¿cómo van los lotes?'}])
        self.assertEqual(decision, {'tool': 'media.jobs', 'arguments': {}})
        tools = runtime.template.render.call_args.kwargs['tools']
        # Con la conversación viva el bloque de sistema no cambia: el KV se aprovecha.
        self.assertNotIn('media_jobs', [t['function']['name'] for t in tools])

    def test_al_reconstruir_se_declaran_los_abiertos(self):
        runtime = self.runtime('Hola.', 'Vale.')
        runtime.generate([{'role': 'user', 'content': 'hola'}])
        runtime.open_drawer('notas')
        runtime.messages = []
        runtime.generate([{'role': 'user', 'content': 'sigue'}])
        tools = runtime.template.render.call_args.kwargs['tools']
        self.assertIn('note_save', [t['function']['name'] for t in tools])
        self.assertTrue(runtime.open_drawer('notas')['already_open'])

    def test_cerrar_vuelve_al_nucleo(self):
        runtime = self.runtime('Hola.')
        runtime.open_drawer('equipos')
        runtime.close_drawers()
        runtime.generate([{'role': 'user', 'content': 'hola'}])
        tools = runtime.template.render.call_args.kwargs['tools']
        self.assertNotIn('device_list', [t['function']['name'] for t in tools])

    def test_una_lectura_elegida_por_hexos_abre_su_cajon(self):
        runtime = self.runtime()
        runtime.begin_tool([{'role': 'user', 'content': 'diagnostica el nas'}],
                           {'tool': 'nas.read', 'arguments': {'section': 'diagnosis'}})
        self.assertIn('equipos', runtime.open_drawers)

    def test_cajon_desconocido(self):
        with self.assertRaises(ValueError) as error:
            self.runtime().open_drawer('cocina')
        self.assertIn('video', str(error.exception))

    def test_el_resumen_de_resultados_viejos_respeta_tools_open(self):
        viejo = time.time() - 3600
        contenido = dict(catalog.drawer_contents('video'), opened=True)
        lectura = {'texto': 'x' * 5000}
        messages = [{'role': 'user', 'content': 'abre'},
                    {'role': 'assistant', 'tool_calls': [], 'tool_responses': [
                        {'name': 'tools_open', 'response': contenido, 'ts': viejo},
                        {'name': 'web_read', 'response': lectura, 'ts': viejo}]},
                    {'role': 'user', 'content': 'otra cosa'},
                    {'role': 'assistant', 'tool_calls': [], 'tool_responses': [
                        {'name': 'web_search', 'response': {'a': 1}, 'ts': time.time()}]}]
        tool_digest.compact_live(messages, {}, {})
        self.assertEqual(messages[1]['tool_responses'][0]['response'], contenido)
        self.assertNotEqual(messages[1]['tool_responses'][1]['response'], lectura)


class RecuperacionTest(unittest.TestCase):
    def test_abrir_un_cajon_no_gasta_el_reintento_de_formato(self):
        from hexos.agent.chat_backend.recovery import RETRY, RecoveryController
        from hexos.agent.chat_backend.state import TurnState
        error = DrawerClosed('cajón cerrado')
        error.repair = 'AVISO'
        agent = SimpleNamespace(runtime=SimpleNamespace(generate=Mock(side_effect=error)))
        turn = TurnState(text='quita nomachine')
        turn.messages = []
        recovery = RecoveryController.__new__(RecoveryController)
        recovery.agent = agent
        self.assertIs(recovery.generate(None, turn), RETRY)
        self.assertEqual(turn.retries.format_retries, 0)
        self.assertEqual(turn.retries.drawer_retries, 1)
        self.assertEqual(turn.messages, [{'role': 'user', 'content': 'AVISO'}])


if __name__ == '__main__':
    unittest.main()
