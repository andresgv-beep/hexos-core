"""Señalar una nota y hablar de «la última versión» se escriben casi igual.

Distinguirlo no es un detalle: con `ver\\w*` casando «versión» y «la última»
contando como señalador, una búsqueda web sobre iOS abría una nota del NAS en
pantalla y la respuesta acababa con «he abierto Diagnóstico de synology 1».
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat_backend.references import ReferenceResolver as R, PEDIR_VER, PEDIR_CERRAR


class SenaladoresTest(unittest.TestCase):
    def test_el_turno_real_del_17_de_septiembre(self):
        texto = 'busca informacion sobre la ultima version de ios'
        self.assertIsNone(R.senala(texto)[0], 'no señala a ninguna nota')
        self.assertIsNone(PEDIR_VER.search(texto), '«versión» no es «ver»')

    def test_un_señalador_seguido_de_sustantivo_no_señala(self):
        # Ahí «la última» es el determinante de lo que viene detrás, no un dedo.
        for texto in ('cual es la ultima version de android',
                      'la ultima vez que hablamos de esto',
                      'dime la 3 cosas que hay que hacer',
                      'la primera opcion me vale'):
            with self.subTest(texto):
                self.assertIsNone(R.senala(texto)[0], texto)

    def test_los_señaladores_de_verdad_siguen_valiendo(self):
        for texto, ordinal in (('mustrame la 3', '3'), ('abrela', None), ('cierrala', None),
                               ('muestrame la ultima', None), ('ensename la anterior porfa', None),
                               ('quitala', None), ('abre esa nota.', None)):
            with self.subTest(texto):
                hallado, visto = R.senala(texto)
                self.assertIsNotNone(hallado, texto)
                self.assertEqual(visto, ordinal)

    def test_un_pronombre_pegado_al_verbo_vale_aunque_siga_la_frase(self):
        # «Ábrela» solo puede referirse a algo ya nombrado: no necesita cerrar la frase.
        self.assertIsNotNone(R.senala('abrela y dime que dice')[0])

    def test_las_palabras_que_empiezan_por_ver_no_son_ver(self):
        for texto in ('version', 'universo', 'verificalo', 'conversacion', 'verdad'):
            with self.subTest(texto):
                self.assertIsNone(PEDIR_VER.search(texto), texto)

    def test_ver_con_pronombre_sigue_siendo_ver(self):
        for texto in ('quiero verla', 'dejame verlo', 'puedo ver eso'):
            with self.subTest(texto):
                self.assertIsNotNone(PEDIR_VER.search(texto), texto)

    def test_cerrar_no_se_confunde_con_ver(self):
        self.assertIsNotNone(PEDIR_CERRAR.search('cierrala'))
        self.assertIsNone(PEDIR_VER.search('cierrala'))


if __name__ == '__main__':
    unittest.main()
