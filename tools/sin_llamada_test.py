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

    def chat(self, respuesta, traza=()):
        runtime = Runtime(); runtime.native = True
        return self.cierre(ventana='chat', pedidos=('notas',), runtime=runtime,
                           respuesta=respuesta, traza=traza)

    def test_en_el_chat_se_devuelve_lo_que_dice_haber_guardado_sin_guardar(self):
        # Apuntar es escribir, y el arranque forzado solo deja leer: se avisa y elige.
        runtime, turn, devuelto, otra = self.chat('He apuntado que tienes dentista el viernes.')
        self.assertTrue(devuelto)
        self.assertEqual(runtime.checks, 0)
        self.assertIn('no se ha guardado nada', turn.messages[0]['content'])
        turn.messages = []
        self.assertFalse(otra())

    def test_si_repetir_no_hace_nada_se_entrega_la_primera_respuesta(self):
        # «Mil disculpas, lo he anotado mal: tú eres mi creador» se devolvió, y lo que
        # salió fue «Entendido. No he guardado nada en este turno».
        tmp = tempfile.TemporaryDirectory(prefix='hexos-sin-llamada-'); self.addCleanup(tmp.cleanup)
        runtime = Runtime(); runtime.native = True
        llamadas = []
        runtime.call = llamadas.append
        agent = Agent(tmp.name, runtime); agent.ventana = 'chat'
        turn = TurnState(text='soy tu creador', image=None, model_request='soy tu creador', transcript=None)
        salida = dict(reply='Tienes razón, lo he anotado mal: tú eres mi creador.', work=None)
        self.assertTrue(agent.runner.recovery.before_completion(None, turn, salida))
        salida['reply'] = 'Entendido. No he guardado nada en este turno.'
        self.assertFalse(agent.runner.recovery.before_completion(None, turn, salida))
        self.assertEqual(salida['reply'], 'Tienes razón, lo he anotado mal: tú eres mi creador.')
        self.assertIn({'type': 'reset'}, llamadas)      # el aviso no se queda en la conversación

    def test_si_al_repetir_guarda_la_nota_vale_la_segunda(self):
        runtime, turn, devuelto, otra = self.chat('He apuntado que tienes dentista el viernes.')
        self.assertTrue(devuelto)
        turn.trace.append(dict(tool='note.save', arguments={}, result={'id': 'n1'}, failed=False))
        self.assertFalse(otra())
        self.assertIsNotNone(turn.retries.respuesta_devuelta)   # no se restauró la primera

    def test_hablar_de_las_notas_en_el_chat_no_se_devuelve(self):
        # «a okey, y notas tienes verdad?»: el selector pidió notas, la respuesta era
        # buena y la devolución la cambió por una contestación al aviso.
        self.assertFalse(self.chat('Sí, tengo la capacidad de gestionar notas. Puedo crear una si me lo pides.')[2])

    def test_si_la_nota_se_guardo_no_se_devuelve(self):
        traza = [dict(tool='note.save', arguments={}, result={'id': 'n1'}, failed=False)]
        self.assertFalse(self.chat('He apuntado la nota.', traza)[2])

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
