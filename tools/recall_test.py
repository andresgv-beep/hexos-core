"""El portón del recuerdo: HexOS busca en el archivo cuando la pregunta mira atrás."""
from datetime import datetime, timedelta, timezone
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

    def poblar(self, *mensajes, hace=3600):
        """Mensajes de una conversación anterior: de hace una hora, salvo que se diga otra cosa."""
        cuando = (datetime.now(timezone.utc) - timedelta(seconds=hace)).isoformat()
        with self.agent.store() as store:
            for role, texto in mensajes:
                store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                                 (uuid4().hex, cuando, role, texto, texto))
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

    # --- Otras formas de mirar atrás ---

    def test_pasa_lo_que_se_dijeron(self):
        from hexos.agent.chat_backend.memory import mira_al_pasado
        for texto in ['¿qué modelo de vapeador me dijiste que era el de la foto?', '¿en qué zona te dije que estaba?',
                      '¿qué talleres me recomendaste?', '¿cómo dijiste que se llamaba?', 'eso ya me lo contaste']:
            self.assertTrue(mira_al_pasado(texto), texto)
        for texto in ['me cuentas un chiste?', 'te pido que revises el nas', 'me lo pasé el 4 y se quedó aparcado']:
            self.assertFalse(mira_al_pasado(texto), texto)

    def test_pasa_la_pregunta_por_algo_suyo(self):
        from hexos.agent.chat_backend.memory import mira_al_pasado
        for texto in ['que vapeador tengo?', '¿qué pantalla tiene mi esp32?', 'Que tengo en notas?',
                      '¿de cuántas pulgadas es la pantalla de mi Seat León?', '¿qué clase llevaba yo en el WoW?',
                      'hola socio!!! como ha ido la conversacion con mi amigo?']:
            self.assertTrue(mira_al_pasado(texto), texto)
        # Un encargo, una opinión o una frase suelta no son preguntas por lo suyo.
        for texto in ['Puedes revisar procesos de mi equipo Linux?', 'puedes crear una calculadora para mi sistema linux?',
                      'y por que no uso otros programas si ya existen?', 'Que va, tengo que terminar la jornada de 8h',
                      '¿qué le pasa al disco del NAS?', 'revisa mi disco', 'podria contruir el mio propio?']:
            self.assertFalse(mira_al_pasado(texto), texto)

    def test_una_pregunta_corta_hereda_el_tema_de_la_anterior(self):
        self.poblar(('user', 'mi libro se llama Biblia Lumínica'))
        self.assertIsNotNone(self.preguntar('¿recuerdas el libro que estaba escribiendo?'))
        recuerdo = self.preguntar('como se llamaba?')
        self.assertIsNotNone(recuerdo)
        self.assertIn('libro', recuerdo['arguments']['terms'])
        self.assertIn('libro', recuerdo['arguments']['inherited'])
        self.assertIn('mi libro se llama Biblia Lumínica', [m['excerpt'] for m in recuerdo['result']['matches']])

    def test_recuerdas_sin_mas_busca_lo_de_la_pregunta_anterior(self):
        self.poblar(('user', 'mi vapeador es un Ontech mecánico'))
        self.assertEqual(self.preguntar('que vapeador tengo?')['arguments']['terms'], ['vapeador'])
        recuerdo = self.preguntar('no recuerdas nada?')
        self.assertEqual((recuerdo['arguments']['terms'], recuerdo['arguments']['inherited']), (['vapeador'], ['vapeador']))
        self.assertIn('mi vapeador es un Ontech mecánico', [m['excerpt'] for m in recuerdo['result']['matches']])

    def test_una_pregunta_corta_suelta_no_busca(self):
        self.poblar(('user', 'mi libro se llama Biblia Lumínica'))
        self.assertIsNone(self.preguntar('como se llamaba?'))
        # Ni detrás de un mensaje que no miraba atrás, ni si entre medias se habló de otra cosa.
        self.assertIsNone(self.preguntar('revisa el estado del synology'))
        self.assertIsNone(self.preguntar('como se llamaba?'))
        self.assertIsNotNone(self.preguntar('¿te acuerdas del libro?'))
        self.assertIsNone(self.preguntar('vale, ahora arranca el contenedor de plex y dime cómo queda'))
        self.assertIsNone(self.preguntar('como se llamaba?'))

    def test_el_seguimiento_caduca(self):
        self.poblar(('user', 'mi libro se llama Biblia Lumínica'))
        with self.agent.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             (uuid4().hex, '2026-01-01T10:00:00+00:00', 'user', '¿te acuerdas del libro?', ''))
            store.db.commit()
        self.assertIsNone(self.preguntar('como se llamaba?'))

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

    # --- El ruido ---

    def test_el_relleno_no_es_una_palabra_que_buscar(self):
        # La frase real: ganó «okey», y «pasa» trajo un «me he pasado de dramático».
        self.assertEqual(sorted(recall_terms('okey no pasa nada, recuerdas de un libro que estaba escribiendo>?', None)),
                         ['escribiendo', 'libro'])
        self.assertEqual(recall_terms('jajaja vale socio, ¿te acuerdas del nas?'), ['nas'])
        self.poblar(('user', 'Okey'), ('user', 'Okey, aprobado'), ('assistant', 'Me he pasado de dramático con el guion'),
                    ('user', 'mi libro se llama Biblia Lumínica'))
        recuerdo = self.preguntar('okey no pasa nada, recuerdas de un libro que estaba escribiendo>?')
        self.assertEqual([m['excerpt'] for m in recuerdo['result']['matches']], ['mi libro se llama Biblia Lumínica'])

    def test_una_palabra_no_vale_como_principio_de_otra_mas_larga(self):
        self.poblar(('user', 'ese contenedor lo tiré'), ('user', 'los contenedores del synology van bien'),
                    ('user', 'el contenido del disco está contento'))
        recuerdo = self.preguntar('¿te acuerdas del contenedor?')
        self.assertEqual(len(recuerdo['result']['matches']), 2)             # singular y plural; «contenido» no

    def test_lo_de_hace_un_momento_no_es_un_recuerdo(self):
        self.poblar(('user', 'mi vaper es un Ontech mecánico'))
        self.poblar(('user', 'y el vaper de mi primo?'), ('assistant', 'De ese vaper no sé nada.'), hace=60)
        recuerdo = self.preguntar('¿te acuerdas de mi vaper?')
        self.assertEqual([m['excerpt'] for m in recuerdo['result']['matches']], ['mi vaper es un Ontech mecánico'])

    def test_si_solo_casa_lo_recien_dicho_no_se_anuncia_que_no_hay_nada(self):
        self.poblar(('user', 'mi vaper es un Ontech mecánico'), hace=60)
        self.assertIsNone(self.preguntar('¿te acuerdas de mi vaper?'))
        # Sin nada en ningún sitio, sí se dice.
        self.assertEqual(self.preguntar('¿te acuerdas de lo del tractor amarillo?')['result']['matches'], [])

    def test_el_seguimiento_no_trae_la_pregunta_que_hereda(self):
        self.poblar(('user', 'mi vapeador es un Ontech mecánico'))
        self.preguntar('que vapeador tengo?')
        with self.agent.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             (uuid4().hex, now(), 'assistant', 'No hay ni rastro de un vapeador.', ''))
            store.db.commit()
        recuerdo = self.preguntar('no recuerdas nada?')
        self.assertEqual([m['excerpt'] for m in recuerdo['result']['matches']], ['mi vapeador es un Ontech mecánico'])

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
