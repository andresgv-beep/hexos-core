"""El canal de pensamiento se enciende y se apaga en caliente, y se recuerda."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent


class RuntimeConPensamiento:
    def __init__(self, thinking=False):
        self.thinking = thinking
        self.durante = []
    def call(self, request): pass
    def generate(self, messages):
        self.durante.append(self.thinking)
        return {'reply': 'Listo.', 'work': None}


class RuntimeSinPensamiento:
    def call(self, request): pass
    def generate(self, messages): return {'reply': '', 'work': None}


class ThinkingToggleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-pensar-test-')

    def tearDown(self):
        self.tmp.cleanup()

    def test_se_enciende_y_se_apaga_en_caliente(self):
        runtime = RuntimeConPensamiento(False)
        agente = Agent(self.tmp.name, runtime)
        self.assertFalse(agente.thinking())
        self.assertTrue(agente.set_thinking(True)['thinking'])
        # El render lee este atributo en cada turno: no hace falta reiniciar nada.
        self.assertTrue(runtime.thinking)
        agente.set_thinking(False)
        self.assertFalse(runtime.thinking)

    def test_la_preferencia_sobrevive_al_reinicio_del_proceso(self):
        Agent(self.tmp.name, RuntimeConPensamiento(False)).set_thinking(True)
        # Proceso nuevo, arrancado sin el flag: manda lo que dejó la persona.
        otro = RuntimeConPensamiento(False)
        self.assertTrue(Agent(self.tmp.name, otro).restore_thinking())
        self.assertTrue(otro.thinking)

    def test_sin_preferencia_guardada_manda_el_flag_de_arranque(self):
        runtime = RuntimeConPensamiento(True)
        self.assertTrue(Agent(self.tmp.name, runtime).restore_thinking())
        self.assertTrue(runtime.thinking)

    def test_un_motor_sin_pensamiento_lo_dice_en_vez_de_fingir(self):
        agente = Agent(self.tmp.name, RuntimeSinPensamiento())
        self.assertIsNone(agente.thinking())
        self.assertIsNone(agente.restore_thinking())
        with self.assertRaises(ValueError):
            agente.set_thinking(True)

    def test_solo_admite_un_booleano(self):
        agente = Agent(self.tmp.name, RuntimeConPensamiento())
        for malo in ('true', 1, None, [], {'enabled': True}):
            with self.assertRaises(ValueError):
                agente.set_thinking(malo)

    def test_un_turno_puede_pensar_sin_cambiar_la_preferencia(self):
        runtime = RuntimeConPensamiento(False)
        agente = Agent(self.tmp.name, runtime)
        agente.chat('Revisa este código.', thinking=True)
        self.assertEqual(runtime.durante, [True])
        self.assertFalse(runtime.thinking)
        self.assertFalse(agente.thinking())


if __name__ == '__main__':
    unittest.main()
