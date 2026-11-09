"""Mensajes largos: el modelo ve el principio y el final, sin GPU ni red.

El 29/10 se pegó un texto de 165.000 caracteres con la pregunta debajo. El
modelo solo veía los primeros 1.200 y una nota que le decía preguntar si no
había tarea: contestó «¿quieres que haga algo con este texto?».
"""
import tempfile
import unittest

from hexos.agent.chat import Agent
from hexos.agent.chat_backend.context import VISTA_FINAL, VISTA_PRINCIPIO, vista_parcial


PEGADO = 'El río baja frío entre piedras grises y la niebla cubre el valle. ' * 2500
PREGUNTA = '¿De qué color era la figura? Y resume el texto en una frase.'


class Runtime:
    native = False

    def __init__(self):
        self.prompts = []

    def call(self, request):
        return {'ok': True}

    def generate(self, messages):
        self.prompts.append(messages)
        return {'reply': 'Respuesta.', 'work': None}


class VistaParcialTest(unittest.TestCase):
    def test_la_pregunta_debajo_de_lo_pegado_llega_al_modelo(self):
        runtime = Runtime()
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, runtime)
            agent.chat(PEGADO + '\n\n' + PREGUNTA)
            with agent.store() as store:
                guardado = store.db.execute('SELECT content FROM documents').fetchone()[0]
        visto = '\n'.join(m['content'] for m in runtime.prompts[0] if isinstance(m.get('content'), str))
        self.assertIn(PREGUNTA, visto)
        self.assertIn('El río baja frío', visto)
        self.assertIn('guardado como documento', visto)
        self.assertEqual(guardado, PEGADO + '\n\n' + PREGUNTA, 'el documento conserva el mensaje entero')

    def test_el_final_no_empieza_a_mitad_de_palabra_y_cuenta_lo_omitido(self):
        texto = PEGADO + '\n\n' + PREGUNTA
        vista = vista_parcial(texto, {'id': 'd'})
        final = vista.split(']\n', 1)[1]
        self.assertTrue(texto.endswith(final))
        self.assertIn(texto[len(texto) - len(final) - 1], ' \n', 'el corte cae en un espacio o salto de línea')
        self.assertTrue(final.endswith(PREGUNTA))
        omitidos = int(vista.split('[… ')[1].split(' ')[0])
        self.assertEqual(VISTA_PRINCIPIO + omitidos + len(final), len(PEGADO + '\n\n' + PREGUNTA))
        self.assertLessEqual(len(final), VISTA_FINAL)

    def test_el_extractor_de_hechos_ve_lo_escrito_debajo_de_lo_pegado(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from hexos.agent.native import NativeRuntime
        enviados = []
        rt = NativeRuntime.__new__(NativeRuntime)
        rt.template = SimpleNamespace(render=lambda messages, **_: messages[-1]['content'])
        rt.send = lambda prompt, auxiliar=False: enviados.append(prompt)
        rt.event = Mock(return_value=(['0', '1', '1', '0', 'eos'], '[]'))
        dato = 'Por cierto, soy ingeniero y vivo en Bilbao.'
        rt.extract_facts(PEGADO + '\n\n' + dato)
        self.assertIn(dato, enviados[0])
        self.assertIn('El río baja frío', enviados[0])
        self.assertLess(len(enviados[0]), 3100)
        rt.extract_facts('Me llamo Ana.')
        self.assertEqual(enviados[1], 'Me llamo Ana.', 'un mensaje corto llega entero')

    def test_un_mensaje_corto_llega_entero_sin_documento(self):
        runtime = Runtime()
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, runtime)
            agent.chat('Resume esto: ' + 'texto ' * 100)
            with agent.store() as store:
                self.assertIsNone(store.db.execute('SELECT id FROM documents').fetchone())
        visto = '\n'.join(m['content'] for m in runtime.prompts[0] if isinstance(m.get('content'), str))
        self.assertNotIn('guardado como documento', visto)


class VentanaRuntime(Runtime):
    """Un motor con ventana real: lo que decide si un mensaje cabe entero."""
    native = False

    def __init__(self, ctx, kv_position=0):
        super().__init__()
        self.ctx = ctx
        self.kv_position = kv_position


ADJUNTO = 'Lee esto.\n\n[{"name":"a.md","content":"' + 'S_e/n es segundo momento.\\n' * 500 + '"}]'


class MensajeEnteroTest(unittest.TestCase):
    def enviar(self, runtime, texto):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, runtime)
            agent.chat(texto)
            with agent.store() as store:
                archivado = store.db.execute(
                    "SELECT model_text FROM conversation WHERE role='user'").fetchone()[0]
                documento = store.db.execute('SELECT content FROM documents').fetchone()[0]
        visto = '\n'.join(m['content'] for m in runtime.prompts[0] if isinstance(m.get('content'), str))
        return visto, archivado, documento

    def test_un_adjunto_que_cabe_llega_entero_y_el_historial_no_lo_arrastra(self):
        visto, archivado, documento = self.enviar(VentanaRuntime(16384), ADJUNTO)
        self.assertIn(ADJUNTO, visto)
        self.assertNotIn('caracteres omitidos', visto)
        self.assertIn('caracteres omitidos', archivado, 'el historial guarda el extracto')
        self.assertLess(len(archivado), 3500)
        self.assertEqual(documento, ADJUNTO)

    def test_si_la_ventana_esta_ocupada_ve_el_extracto_y_la_orden_de_leerlo(self):
        visto, _, documento = self.enviar(VentanaRuntime(16384, kv_position=13000), ADJUNTO)
        self.assertNotIn(ADJUNTO, visto)
        self.assertIn('léelo antes con document.read', visto)
        self.assertEqual(documento, ADJUNTO)

    def test_una_sola_linea_gigante_se_puede_leer_entera(self):
        from hexos.agent.chat_backend.document_reading import DOCUMENT_LINE_CHARS, document_lines
        lineas = document_lines(ADJUNTO)
        self.assertEqual('\n'.join(lineas).replace('\n', ''), ADJUNTO.replace('\n', ''))
        self.assertLessEqual(max(map(len, lineas)), DOCUMENT_LINE_CHARS)


if __name__ == '__main__':
    unittest.main()
