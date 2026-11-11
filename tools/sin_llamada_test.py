"""Ventana Agente: si el selector pidió herramientas y el turno acaba sin llamar, se devuelve."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent
from hexos.agent.chat_backend.state import TurnState
from hexos.agent import native


class Runtime:
    def __init__(self, acepta=True): self.checks, self.acepta = 0, acepta
    def call(self, request): pass
    def require_check(self): self.checks += 1; return self.acepta


class SinLlamadaTest(unittest.TestCase):
    def cierre(self, *, ventana='agente', pedidos=('sistema',), traza=(), runtime=None,
               respuesta='Para revisar el registro usaré journalctl.'):
        tmp = tempfile.TemporaryDirectory(prefix='hexos-sin-llamada-')
        self.addCleanup(tmp.cleanup)
        runtime = runtime or Runtime()
        agent = Agent(tmp.name, runtime)
        agent.ventana = ventana
        turn = TurnState(text='mira el registro', image=None, model_request='mira el registro', transcript=None)
        turn.grupos_pedidos, turn.trace = list(pedidos), list(traza)
        salida = dict(reply=respuesta, work=None)
        primera = agent.runner.recovery.before_completion(None, turn, salida)
        return runtime, turn, primera, lambda: agent.runner.recovery.before_completion(None, turn, salida)

    def test_se_devuelve_una_vez_y_arranca_en_una_lectura(self):
        # Con el historial real delante: «usaré journalctl. Voy a buscar…» y fin del turno.
        runtime, turn, devuelto, otra = self.cierre()
        self.assertTrue(devuelto)
        self.assertEqual(runtime.checks, 1)
        self.assertIn('AVISO DE HEXOS', turn.messages[0]['content'])
        turn.messages = []
        self.assertFalse(otra())                      # si insiste, no se le vuelve a pedir
        self.assertEqual(runtime.checks, 1)

    def test_no_depende_de_lo_que_diga_la_respuesta(self):
        # Las frases no cuentan, ni para bien ni para mal: es una señal de estructura.
        for respuesta in ('Claro.', '¿De qué equipo hablas?', 'Voy a mirarlo ahora mismo.'):
            self.assertTrue(self.cierre(respuesta=respuesta)[2], respuesta)

    def test_si_el_selector_no_pidio_nada_es_una_charla(self):
        runtime, _, devuelto, _ = self.cierre(pedidos=(), respuesta='Voy a revisar el NAS.')
        self.assertFalse(devuelto)
        self.assertEqual(runtime.checks, 0)

    def test_en_el_chat_se_devuelve_sin_forzar_una_lectura(self):
        # «He apuntado que tienes dentista» sin una sola llamada. Apuntar es escribir,
        # y el arranque forzado solo deja leer: se avisa y el modelo elige.
        runtime = Runtime(); runtime.native = True
        runtime, turn, devuelto, otra = self.cierre(ventana='chat', pedidos=('notas',), runtime=runtime)
        self.assertTrue(devuelto)
        self.assertEqual(runtime.checks, 0)
        self.assertIn('no se ha guardado', turn.messages[0]['content'])
        turn.messages = []
        self.assertFalse(otra())

    def test_una_charla_en_el_chat_no_se_devuelve(self):
        runtime = Runtime(); runtime.native = True
        self.assertFalse(self.cierre(ventana='chat', pedidos=(), runtime=runtime)[2])

    def test_con_alguna_llamada_hecha_no_se_toca(self):
        traza = [dict(tool='system.status', arguments={}, result={'cpu': {}}, failed=False)]
        self.assertFalse(self.cierre(traza=traza, respuesta='Va bien.')[2])

    def test_si_el_motor_no_puede_abrir_la_llamada_no_se_insiste(self):
        runtime, turn, devuelto, _ = self.cierre(runtime=Runtime(acepta=False))
        self.assertFalse(devuelto)
        self.assertEqual(turn.messages, [])

    def test_la_instruccion_ya_no_pide_anunciar(self):
        self.assertNotIn('anuncia brevemente', native.POLICY)
        self.assertIn('No anuncies una consulta sin hacerla', native.POLICY)


if __name__ == '__main__':
    unittest.main()
