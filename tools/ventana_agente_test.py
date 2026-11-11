"""En la ventana Agente una lectura no espera a que la persona aclare nada."""
import json
import tempfile
import unittest

from hexos.agent import catalog
from hexos.agent.chat import Agent


class Runtime:
    def __init__(self):
        self.vistos = []

    def call(self, request): pass

    def generate(self, messages):
        self.vistos.append(json.dumps(messages, ensure_ascii=False))
        return {'reply': 'Hecho.', 'work': None}


class VentanaAgenteTest(unittest.TestCase):
    def turno(self, ventana, texto='tengo gimp?'):
        with tempfile.TemporaryDirectory(prefix='hexos-ventana-') as tmp:
            runtime = Runtime()
            agente = Agent(tmp, runtime)
            agente.set_window(ventana)
            agente.chat(texto)
            return '\n'.join(runtime.vistos)

    def test_el_agente_recibe_la_regla_de_leer_sin_preguntar(self):
        visto = self.turno('agente')
        self.assertIn('VENTANA AGENTE', visto)
        self.assertIn('en vez de preguntar', visto)

    def test_la_regla_no_se_atribuye_a_la_persona(self):
        # Con «(dato)» a secas el modelo respondió «como mencionaste que…».
        self.assertIn('no la ha dicho la persona', self.turno('agente'))

    def test_el_chat_no_la_recibe(self):
        self.assertNotIn('VENTANA AGENTE', self.turno('chat'))

    def test_el_selector_sabe_que_las_aplicaciones_son_de_este_pc(self):
        # «¿Podrías encontrar la app de ChatGPT?» no pedía el grupo y la terminal ni se ofrecía.
        guia = catalog.GROUP_GUIDANCE['sistema']
        self.assertIn('instalado', guia)
        self.assertIn('aplicaciones', guia)


if __name__ == '__main__':
    unittest.main()
