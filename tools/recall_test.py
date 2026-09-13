"""El portón del recuerdo: HexOS busca en el archivo cuando la pregunta mira atrás."""
from pathlib import Path
import sys
import tempfile
import unittest
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent, RECUERDO, recall_terms
from hexos.agent.work import now


class Runtime:
    def call(self, request): pass
    def generate(self, messages): return {'reply': '', 'work': None}


class RecallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-recuerdo-test-')
        self.agent = Agent(self.tmp.name, Runtime())

    def tearDown(self):
        self.tmp.cleanup()

    def poblar(self, *mensajes):
        with self.agent.store() as store:
            for role, texto in mensajes:
                store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                                 (uuid4().hex, now(), role, texto, texto))
            store.db.commit()

    def preguntar(self, texto):
        uid = uuid4().hex
        with self.agent.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             (uid, now(), 'user', texto, texto))
            store.db.commit()
            return self.agent.recall_history(store, texto, uid)

    # --- El portón ---

    def test_deja_pasar_las_preguntas_sobre_el_pasado(self):
        for texto in ['¿te acuerdas de qué te pedí sobre los contenedores?',
                      '¿de qué hablamos ayer por la noche?',
                      '¿qué te dije del disco?', 'anoche te pedí algo, ¿qué era?',
                      '¿es la primera vez que te pregunto por sda?']:
            self.assertTrue(RECUERDO.search(texto), texto)

    def test_no_se_dispara_en_conversacion_normal(self):
        for texto in ['revisa el estado del synology', 'arranca el contenedor plex',
                      'vale gracias', 'hola socio', '¿qué le pasa al disco del NAS?']:
            self.assertIsNone(RECUERDO.search(texto), texto)
            self.assertIsNone(self.preguntar(texto), texto)

    # --- Los términos ---

    def test_descarta_las_palabras_que_no_distinguen(self):
        # «acuerdas», «anoche» y «que» salen en toda pregunta del portón.
        self.assertEqual(recall_terms('¿te acuerdas de qué te pedí anoche sobre los '
                                      'contenedores del synology?'),
                         ['contenedores', 'synology'])
        # Tres letras valen si distinguen: «sda» sí, «los» no.
        self.assertIn('sda', recall_terms('¿es la primera vez que te pregunto por el disco sda?'))

    def test_las_tildes_no_duplican_un_termino(self):
        self.assertEqual(len(recall_terms('¿te acuerdas del diagnóstico y del diagnostico?')), 1)

    # --- La búsqueda ---

    def test_encuentra_el_mensaje_de_antes_y_deja_traza(self):
        self.poblar(('user', 'revisa el estado de los contenedores del synology'),
                    ('assistant', 'minecraft-java y n8n están en ejecución'),
                    ('user', 'gracias'))
        recuerdo = self.preguntar('¿te acuerdas de qué te pedí sobre los contenedores?')
        self.assertIsNotNone(recuerdo)
        textos = [m['excerpt'] for m in recuerdo['result']['matches']]
        self.assertIn('revisa el estado de los contenedores del synology', textos)
        # La traza tiene que decir que fue HexOS, no el modelo.
        self.assertEqual(recuerdo['tool'], 'history.recall')
        self.assertEqual(recuerdo['result']['requested_by'], 'hexos')
        self.assertFalse(recuerdo['changes_state'])

    def test_el_singular_rescata_lo_que_el_plural_no_encuentra(self):
        self.poblar(('user', 'apunta que la contraseña va por la ventana, nunca por el chat'))
        recuerdo = self.preguntar('¿qué te dije sobre las contraseñas?')
        self.assertTrue(recuerdo['result']['matches'], 'el singular debía rescatarlo')
        self.assertIn('contraseña', recuerdo['arguments']['queries'])

    def test_no_se_encuentra_a_si_mismo(self):
        recuerdo = self.preguntar('¿te acuerdas de los contenedores?')
        self.assertEqual(recuerdo['result']['matches'], [])

    def test_manda_el_que_casa_con_mas_terminos(self):
        self.poblar(('user', 'los contenedores del synology van bien'),
                    ('user', 'esos contenedores de plástico son del garaje'))
        recuerdo = self.preguntar('¿te acuerdas de los contenedores del synology?')
        primero = recuerdo['result']['matches'][0]['excerpt']
        self.assertIn('synology', primero)

    def test_sin_coincidencias_lo_dice_en_vez_de_callar(self):
        recuerdo = self.preguntar('¿te acuerdas de lo del tractor amarillo?')
        self.assertEqual(recuerdo['result']['matches'], [])
        self.assertIn('no demuestra', recuerdo['result']['note'])

    def test_un_fallo_del_archivo_no_tumba_el_turno(self):
        # Esto corre en cada turno que mire al pasado: si revienta, calla y sigue.
        with self.agent.store() as store:
            store.db.execute('DROP TABLE conversation')
            store.db.commit()
            self.assertIsNone(self.agent.recall_history(store, '¿te acuerdas del synology?', 'x'))


if __name__ == '__main__':
    unittest.main()
