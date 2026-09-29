"""«Me has pillado»: un reproche hace que HexOS pida comprobar antes de contestar."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent import reproche
from hexos.agent.chat import Agent
from hexos.agent.chat_backend.state import TurnState
from hexos.agent.native import NativeRuntime
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock


class Runtime:
    def __init__(self): self.checks = 0
    def call(self, request): pass
    def require_check(self): self.checks += 1; return True
    def generate(self, messages): return {'reply': 'Te dije 2.1 TB.', 'work': None}


class ReprocheTest(unittest.TestCase):
    def test_reconoce_los_reproches(self):
        for texto in ['esque no se quedan y tu me dijiste que si',
                      'pero no me habías dicho que se quedaba el original?',
                      'antes me dijiste que tenía 5 TB libres, no?',
                      'eso no puede ser, revísalo', 'eso no es verdad',
                      'te has equivocado con la ruta', 'te contradices', '¿estás seguro?',
                      'me has mentido', 'no cuadra lo que dices']:
            self.assertTrue(reproche.bloque(texto), texto)

    def test_no_salta_en_conversacion_normal(self):
        for texto in ['hola socio', 'perfecto', 'comprime venom', 'apúntame que mañana llame al técnico',
                      '¿qué te dije del disco?', 'revisa el estado del synology', 'dime qué contenedores hay',
                      'no puedo verlo bien', 'es cierto que va más rápido']:
            self.assertEqual(reproche.bloque(texto), '', texto)

    def test_la_indicacion_llega_al_modelo_como_dato_del_turno(self):
        with tempfile.TemporaryDirectory(prefix='hexos-reproche-test-') as tmp:
            agent = Agent(tmp, Runtime())
            for texto, esperado in (('pero no me habías dicho que se quedaba?', True), ('perfecto', False)):
                turn = TurnState(text=texto, image=None, model_request=texto, transcript=None)
                with agent.store() as store:
                    agent.context.prepare(store, turn)
                enviado = json.dumps(turn.messages, ensure_ascii=False)
                self.assertEqual('REPROCHE DE LA PERSONA' in enviado, esperado, texto)
                # Es una indicación preventiva, no una corrección: no cuenta como aviso en muletas.py.
                self.assertNotIn('AVISO DE HEXOS', enviado)

    def test_el_turno_de_un_reproche_arranca_en_una_lectura(self):
        with tempfile.TemporaryDirectory(prefix='hexos-reproche-test-') as tmp:
            runtime = Runtime()
            agent = Agent(tmp, runtime)
            agent.chat('perfecto')
            self.assertEqual(runtime.checks, 0)
            agent.chat('pero no me habías dicho que quedaban 5 TB?')
            self.assertEqual(runtime.checks, 1)

    def test_require_check_ofrece_solo_lecturas_y_abre_la_llamada(self):
        runtime = NativeRuntime.__new__(NativeRuntime)
        runtime.names = {'nas_read': 'nas.read', 'note_save': 'note.save'}
        runtime.tools = [{'function': {'name': n}} for n in runtime.names]
        runtime.pending, runtime.messages, runtime.current = deque(), [], None
        runtime.template = SimpleNamespace(render=Mock(return_value='prompt '))
        enviados = []
        runtime.send = lambda prompt, image: enviados.append(prompt)
        runtime.event = lambda: (['0', '1', '1', '1', 'stop'],
                                 'nas_read{device:<|"|>Faro<|"|>,section:<|"|>space<|"|>}<tool_call|>')
        runtime.notify = Mock()
        self.assertTrue(runtime.require_check())
        decision = runtime.generate([{'role': 'user', 'content': 'pero no me dijiste 5 TB?'}])
        self.assertEqual(decision, {'tool': 'nas.read', 'arguments': {'device': 'Faro', 'section': 'space'}})
        self.assertTrue(enviados[0].endswith('<|tool_call>call:'))
        ofrecidas = [t['function']['name'] for t in runtime.template.render.call_args.kwargs['tools']]
        self.assertEqual(ofrecidas, ['nas_read'])
        self.assertFalse(runtime.repair_call)  # solo la primera generación


if __name__ == '__main__':
    unittest.main()
