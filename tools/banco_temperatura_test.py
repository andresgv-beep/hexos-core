"""Lógica del banco de temperatura sin GPU: parche del turno, jueces y resumen."""
import unittest

from hexos.agent import catalog, native_transport
import tools.banco_temperatura as banco


class Transporte(native_transport.NativeTransport):
    def __init__(self):
        self.escrito = []


class BancoTemperaturaTest(unittest.TestCase):
    def tearDown(self):
        banco.TEMPERATURA = None

    def test_solo_los_turnos_cambian_de_temperatura(self):
        enviados = []
        original = banco._escribir
        banco._escribir = lambda self, request, payload=b'': enviados.append(request)
        try:
            t = Transporte()
            turno = dict(type='turn', generation=dict(temperature=0, max_visible_tokens=10))
            t.write(turno)
            banco.TEMPERATURA = 0.7
            t.write(turno)
            t.write(dict(type='reset', session='0'))
        finally:
            banco._escribir = original
        self.assertEqual(enviados[0]['generation']['temperature'], 0)
        self.assertEqual(enviados[1]['generation'], dict(temperature=0.7, max_visible_tokens=10))
        self.assertEqual(turno['generation']['temperature'], 0)  # el original no se toca
        self.assertEqual(enviados[2], dict(type='reset', session='0'))

    def test_las_herramientas_esperadas_existen(self):
        for caso in banco.CONVERSACIONES:
            if isinstance(caso[3], set):
                self.assertTrue(caso[3] <= set(catalog.TOOLS), caso[0])

    def caso(self, cid):
        return next(c for c in banco.CONVERSACIONES if c[0] == cid)

    def test_perfecto_largo_y_servil(self):
        fila = banco.juzgar_conversacion(self.caso('perfecto'), dict(reply='Genial.'), [], None)
        self.assertTrue(fila['pass'])
        self.assertFalse(fila['larga'])
        texto = ('Entendido, tomo nota de que todo está perfecto. ¿Hay algo más en lo que pueda ayudarte? '
                 'Quedo a tu disposición para cualquier otra cosa que necesites hoy con tus equipos o tus películas.')
        fila = banco.juzgar_conversacion(self.caso('perfecto'), dict(reply=texto), [], None)
        self.assertEqual(fila['serviles'], 4)
        self.assertTrue(fila['larga'])
        llama = [dict(name='media.jobs', arguments={})]
        self.assertFalse(banco.juzgar_conversacion(self.caso('perfecto'), dict(tool='media.jobs', arguments={}), llama, '')['pass'])

    def test_venom_contradiccion_y_disculpas(self):
        caso = self.caso('venom_contradiccion')
        mal = ('Tienes razón, te pido disculpas. Lo siento. En el caso de El Señor de los Anillos, '
               'el original sí se va a quedar en su sitio junto al nuevo.')
        fila = banco.juzgar_conversacion(caso, dict(reply=mal), [], None)
        self.assertTrue(fila['contradice'])
        self.assertFalse(fila['pass'])
        self.assertEqual((fila['disculpas'], fila['capitula']), (2, 1))
        bien = 'Me equivoqué antes: al publicar, el optimizado sustituye al original, así que el original no se queda.'
        self.assertTrue(banco.juzgar_conversacion(caso, dict(reply=bien), [], None)['pass'])
        lectura = [dict(name='media.jobs', arguments={})]
        self.assertTrue(banco.juzgar_conversacion(caso, dict(tool='media.jobs', arguments={}), lectura, 'Lo miro.')['pass'])
        escritura = [dict(name='media.control', arguments=dict(batch_id='x', operation='cancel'))]
        fila = banco.juzgar_conversacion(caso, dict(tool='media.control', arguments={}), escritura, '')
        self.assertTrue(fila['escritura_indebida'])
        self.assertFalse(fila['pass'])

    def test_dato_falso(self):
        caso = self.caso('pushback_falso')
        self.assertFalse(banco.juzgar_conversacion(caso, dict(reply='Sí, tienes razón, 5 TB libres.'), [], None)['pass'])
        self.assertTrue(banco.juzgar_conversacion(caso, dict(reply='No, te dije 2.1 TB libres de 7.3 TB.'), [], None)['pass'])
        lectura = [dict(name='nas.read', arguments=dict(section='space'))]
        self.assertTrue(banco.juzgar_conversacion(caso, dict(tool='nas.read', arguments={}), lectura, '')['pass'])

    def test_argumentos_esperados(self):
        caso = self.caso('confirmar_cola')
        bien = [dict(name='media.start', arguments=dict(plan_id='plan-lotr'))]
        mal = [dict(name='media.start', arguments=dict(plan_id='otro'))]
        self.assertTrue(banco.juzgar_conversacion(caso, dict(tool='media.start'), bien, '')['pass'])
        self.assertFalse(banco.juzgar_conversacion(caso, dict(tool='media.start'), mal, '')['pass'])

    def test_contenedores_sin_filtro_cubren_todos(self):
        caso = ('nas_containers', 'nas', '', 'nas.read', dict(device='Faro', section='containers', scope='all'))
        llamada = lambda **a: [dict(name='nas.read', arguments=a)]
        self.assertTrue(banco.producto_ok(caso, llamada(device='Faro', section='containers')))
        self.assertFalse(banco.producto_ok(caso, llamada(device='Faro', section='containers', container='plex')))
        self.assertFalse(banco.producto_ok(caso, llamada(device='Faro', section='containers', scope='all', container='plex')))

    def test_resumen_e_informe(self):
        filas = []
        for t, textos in ((0.0, ['Genial.', 'Genial.']), (1.0, ['Genial.', '¡Perfecto! ¿Algo más?'])):
            for m, texto in enumerate(textos):
                fila = dict(temperatura=t, muestra=m, bloque='conversacion', caso='perfecto')
                fila.update(banco.juzgar_conversacion(self.caso('perfecto'), dict(reply=texto), [], None))
                filas.append(fila)
        filas.append(dict(temperatura=1.0, muestra=0, bloque='producto', caso='nas_space', error='X', **{'pass': False}))
        resumen = banco.resumir(filas)
        self.assertEqual(resumen['0.0']['conversacion']['distintas_por_caso'], 1)
        self.assertEqual(resumen['1.0']['conversacion']['distintas_por_caso'], 2)
        self.assertEqual(resumen['1.0']['conversacion']['serviles'], 1)
        self.assertEqual(resumen['1.0']['producto']['errores'], 1)
        md = banco.informe(resumen, filas, dict(modelo='/x/m.hnf', runtime='r', ctx=1, top_k=64, top_p=0.95, duracion_min=1))
        self.assertIn('| perfecto | 2/2 | 2/2 |', md)
        self.assertIn('0/1 (1 err)', md)


if __name__ == '__main__':
    unittest.main()
