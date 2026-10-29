"""device.remote con la dirección tal como la escribe una persona, sin red ni GPU.

Reproduce el turno del 29/10: «si https://servidorsrv1,ddns.net guardalo y
llamalo synology 1» falló por la coma, y «intentalo sin protocolo» falló porque
la evidencia solo se buscaba en el mensaje de ese turno. Hubo que reescribirla.
"""
import tempfile
import unittest

from hexos.agent.chat import Agent


DICHO = 'si https://servidorsrv1,ddns.net guardalo y llamalo synology 1'


class DireccionRemotaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.agent = Agent(self.tmp.name, None)

    def tearDown(self):
        self.tmp.cleanup()

    def conversacion(self, store, *mensajes):
        for i, (rol, texto) in enumerate(mensajes):
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             ('m%d' % i, 'now', rol, texto, texto))
        store.db.commit()
        return 'm%d' % (len(mensajes) - 1)

    def registrar(self, host, *mensajes):
        with self.agent.store() as s:
            turno = self.conversacion(s, *mensajes)
            return self.agent.tool(s, 'device.remote', dict(name='synology 1', host=host),
                                   turn_id=turno)

    def test_la_coma_se_lee_como_punto_y_se_dice(self):
        for host in ('https://servidorsrv1,ddns.net', 'servidorsrv1.ddns.net'):
            with self.subTest(host=host):
                r = self.registrar(host, ('user', DICHO))
                self.assertEqual(r['original_address'], 'https://servidorsrv1.ddns.net')
                self.assertEqual(r['scheme'], 'https')
                self.assertEqual(r['ssh_host'], 'servidorsrv1.ddns.net')
                self.assertEqual(r['written_as'], 'https://servidorsrv1,ddns.net')
                self.assertIn('una coma no es válida', r['correction'])
                self.tearDown(); self.setUp()

    def test_inténtalo_sin_protocolo_usa_la_direccion_del_mensaje_anterior(self):
        r = self.registrar('servidorsrv1.ddns.net',
                           ('user', DICHO),
                           ('assistant', 'No pude guardar la conexión con esa dirección.'),
                           ('user', 'intentalo sin protocolo'))
        self.assertEqual(r['original_address'], 'https://servidorsrv1.ddns.net')
        with self.agent.store() as s:
            ficha = self.agent.tool(s, 'device.list', {})['items'][0]
        self.assertEqual(ficha['name'], 'synology 1')

    def test_sin_coma_no_hay_aviso_de_correccion(self):
        r = self.registrar('servidorsrv1.ddns.net', ('user', 'guarda servidorsrv1.ddns.net como synology 1'))
        self.assertNotIn('correction', r)

    def test_sigue_sin_registrar_lo_que_la_persona_no_escribio(self):
        casos = {
            'otro equipo': [('user', DICHO)],
            'solo lo dijo el asistente': [('user', 'guarda mi nas'),
                                          ('assistant', '¿Es servidorsrv1.ddns.net?'),
                                          ('user', 'sí, ese')],
            'demasiado atrás': [('user', DICHO)] + [('user', 'vale %d' % i) for i in range(6)],
        }
        for nombre, mensajes in casos.items():
            host = 'otro.ddns.net' if nombre == 'otro equipo' else 'servidorsrv1.ddns.net'
            with self.subTest(nombre):
                with self.assertRaisesRegex(ValueError, 'no aparece en el mensaje de la persona'):
                    self.registrar(host, *mensajes)
                self.tearDown(); self.setUp()


if __name__ == '__main__':
    unittest.main()
