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

    # --- El orden: por rareza, no por fecha ---

    def test_lo_antiguo_no_queda_enterrado_por_lo_reciente(self):
        # «¿Te acuerdas del libro?» funcionó una semana y dejó de traer el libro: la
        # palabra había vuelto a salir en más de veinte mensajes nuevos, y la búsqueda
        # solo miraba los veinte más recientes.
        self.poblar(('user', 'mi libro se llama Biblia Lumínica'))
        self.poblar(*[('assistant', 'Seguimos con lo de hoy, que es largo y va de muchas cosas distintas a la vez; '
                                    'ya retomaremos el libro cuando toque, ahora vamos con el punto %d.' % n)
                      for n in range(25)])
        recuerdo = self.preguntar('¿te acuerdas del libro?')
        self.assertIn('mi libro se llama Biblia Lumínica', [m['excerpt'] for m in recuerdo['result']['matches']])
        self.assertEqual(recuerdo['result']['search_type'], 'full_text_bm25')
        self.assertEqual(len(recuerdo['result']['matches']), 6)

    def test_cuentan_todas_las_palabras_y_no_solo_las_tres_mas_largas(self):
        # «nas» es la más corta y la única que distingue el mensaje.
        self.poblar(('user', 'el nas hace un ruido raro por las noches'))
        recuerdo = self.preguntar('¿recuerdas aquella conversación larguísima sobre el dichoso nas?')
        self.assertEqual(len(recuerdo['arguments']['terms']), 4)
        self.assertEqual([m['excerpt'] for m in recuerdo['result']['matches']], ['el nas hace un ruido raro por las noches'])

    def test_ni_las_tildes_ni_el_plural_esconden_el_mensaje(self):
        self.poblar(('user', 'el diagnóstico del taller fue la bomba de agua'))
        for pregunta in ('¿te acuerdas de los diagnosticos?', '¿te acuerdas de los talleres?'):
            self.assertEqual(len(self.preguntar(pregunta)['result']['matches']), 1, pregunta)

    def test_la_palabra_rara_pesa_mas_que_la_que_sale_en_todas_partes(self):
        self.poblar(*[('assistant', 'el coche esto, el coche lo otro, punto %d' % n) for n in range(10)])
        self.poblar(('user', 'al coche le hace falta pasar por la floresta'))
        self.poblar(*[('assistant', 'más cosas del coche, punto %d' % n) for n in range(10)])
        recuerdo = self.preguntar('¿te acuerdas de lo del coche y la floresta?')
        self.assertIn('al coche le hace falta pasar por la floresta', [m['excerpt'] for m in recuerdo['result']['matches']])

    def test_sin_fts5_busca_como_antes(self):
        import sqlite3
        from hexos.agent.chat_backend import memory
        self.poblar(('user', 'revisa el estado de los contenedores del synology'))
        original = memory.por_rareza

        def sin_fts5(*_, **__):
            raise sqlite3.OperationalError('no such module: fts5')
        memory.por_rareza = sin_fts5
        try:
            recuerdo = self.preguntar('¿te acuerdas de qué te pedí sobre los contenedores?')
        finally:
            memory.por_rareza = original
        self.assertEqual(recuerdo['result']['search_type'], 'literal_substring')
        self.assertEqual(len(recuerdo['result']['matches']), 1)

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
