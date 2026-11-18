"""La puerta de Helios: usuarios, sesiones, intentos y su servidor HTTP.

Sin red ni GPU. Sale del 18/11: Andrés quiere entrar desde fuera de Tailscale, y gente que
no es de informática quiere probar Helios con una dirección y un usuario.
"""
from http.server import ThreadingHTTPServer
from pathlib import Path
import http.client
import json
import os
import stat
import sys
import tempfile
import threading
import time
import unittest
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos import puerta

CLAVE = 'una clave bien larga'


class Reloj:
    def __init__(self):
        self.ahora = time.time()      # la terminal apunta con la hora de verdad

    def __call__(self):
        return self.ahora


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.config = Path(self.dir.name) / 'config'
        self.estado = Path(self.dir.name) / 'estado'
        puerta.nuevo('andres', CLAVE, config=self.config)
        self.reloj = Reloj()          # después: una sesión anterior al usuario no vale
        self.puerta = puerta.Puerta(self.config, self.estado, reloj=self.reloj)

    def tearDown(self):
        self.dir.cleanup()


class Usuarios(Base):
    def test_la_clave_no_se_guarda_y_el_fichero_es_privado(self):
        ruta = self.config / 'usuarios.json'
        self.assertNotIn(CLAVE, ruta.read_text())
        self.assertTrue(json.loads(ruta.read_text())['usuarios']['andres']['clave'].startswith('scrypt$'))
        self.assertEqual(stat.S_IMODE(ruta.stat().st_mode), 0o600)

    def test_nombres_y_claves_validos(self):
        for malo in ('', 'Con Espacio', '../x', 'a' * 33, '-guion'):
            with self.assertRaises(ValueError):
                puerta.nuevo(malo, CLAVE, config=self.config)
        with self.assertRaises(ValueError):
            puerta.nuevo('corta', 'corta', config=self.config)
        with self.assertRaises(ValueError):
            puerta.nuevo('andres', CLAVE, config=self.config)          # ya existe
        puerta.nuevo('Ana', CLAVE, config=self.config)
        self.assertEqual(puerta.lista(config=self.config), ['ana', 'andres'])

    def test_un_fichero_legible_por_otros_cierra_la_puerta(self):
        os.chmod(self.config / 'usuarios.json', 0o644)
        with self.assertRaises(PermissionError):
            puerta.Puerta(self.config, self.estado, reloj=self.reloj).usuarios()


class Sesiones(Base):
    def test_entrar_y_comprobar(self):
        token = self.puerta.entrar('Andres ', CLAVE)
        self.assertEqual(self.puerta.comprobar(token), 'andres')
        self.assertIsNone(self.puerta.comprobar(token + 'x'))
        self.assertIsNone(self.puerta.comprobar(None))
        # En disco solo la huella, y en un fichero privado.
        ruta = self.estado / 'sesiones.json'
        self.assertNotIn(token, ruta.read_text())
        self.assertEqual(stat.S_IMODE(ruta.stat().st_mode), 0o600)
        # Sobrevive a reiniciar el servicio.
        otra = puerta.Puerta(self.config, self.estado, reloj=self.reloj)
        self.assertEqual(otra.comprobar(token), 'andres')

    def test_el_error_no_dice_si_el_usuario_existe(self):
        with self.assertRaises(puerta.Rechazo) as uno:
            self.puerta.entrar('andres', 'otra clave cualquiera')
        with self.assertRaises(puerta.Rechazo) as otro:
            self.puerta.entrar('nadie', CLAVE)
        self.assertEqual(uno.exception.aviso, otro.exception.aviso)

    def test_caduca_sin_uso_y_a_los_noventa_dias(self):
        token = self.puerta.entrar('andres', CLAVE)
        self.reloj.ahora += puerta.SIN_USO + 10
        self.assertIsNone(self.puerta.comprobar(token))
        token = self.puerta.entrar('andres', CLAVE)
        for _ in range(3):                          # usándola cada 25 días: 75 días
            self.reloj.ahora += 25 * 86400
            self.assertEqual(self.puerta.comprobar(token), 'andres')
        self.reloj.ahora += 25 * 86400               # 100 días desde que se abrió
        self.assertIsNone(self.puerta.comprobar(token))

    def test_salir_cambiar_clave_y_quitar_cierran_sesiones(self):
        token = self.puerta.entrar('andres', CLAVE)
        self.puerta.salir(token)
        self.assertIsNone(self.puerta.comprobar(token))
        token = self.puerta.entrar('andres', CLAVE)
        self.reloj.ahora += 1
        puerta.nuevo('andres', 'la clave nueva de ahora', config=self.config, cambiar=True)
        self.assertIsNone(self.puerta.comprobar(token))
        with self.assertRaises(puerta.Rechazo):
            self.puerta.entrar('andres', CLAVE)
        token = self.puerta.entrar('andres', 'la clave nueva de ahora')
        puerta.quitar('andres', config=self.config)
        self.assertIsNone(self.puerta.comprobar(token))

    def test_cerrar_sesiones_de_un_usuario(self):
        token = self.puerta.entrar('andres', CLAVE)
        self.reloj.ahora += 1
        puerta.cerrar('andres', config=self.config)
        self.assertIsNone(self.puerta.comprobar(token))


class Intentos(Base):
    def test_cinco_fallos_bloquean_ese_usuario(self):
        for _ in range(puerta.FALLOS_USUARIO):
            with self.assertRaises(puerta.Rechazo):
                self.puerta.entrar('andres', 'no es esta clave')
        with self.assertRaises(puerta.Rechazo) as bloqueo:
            self.puerta.entrar('andres', CLAVE)              # ni con la buena
        self.assertTrue(bloqueo.exception.bloqueo)
        self.assertIn('15 minutos', bloqueo.exception.aviso)
        puerta.nuevo('ana', CLAVE, config=self.config)
        self.assertTrue(self.puerta.entrar('ana', CLAVE))     # los demás siguen entrando
        self.reloj.ahora += puerta.BLOQUEO_USUARIO + 1
        self.assertTrue(self.puerta.entrar('andres', CLAVE))

    def test_muchos_fallos_repartidos_bloquean_a_todos(self):
        for numero in range(puerta.FALLOS_TODOS):
            with self.assertRaises(puerta.Rechazo):
                self.puerta.entrar('prueba%d' % numero, 'no es esta clave')
        with self.assertRaises(puerta.Rechazo) as bloqueo:
            self.puerta.entrar('andres', CLAVE)
        self.assertTrue(bloqueo.exception.bloqueo)
        self.reloj.ahora += puerta.BLOQUEO_TODOS + 1
        self.assertTrue(self.puerta.entrar('andres', CLAVE))


class Destino(unittest.TestCase):
    def test_solo_rutas_de_este_sitio(self):
        self.assertEqual(puerta.destino('/?ventana=chat'), '/?ventana=chat')
        for malo in ('//evil.com', 'https://evil.com', '/\\evil.com', '/_puerta/salir', '/a\r\nSet-Cookie: x', None, ''):
            self.assertEqual(puerta.destino(malo), '/')


class Servidor(Base):
    def setUp(self):
        super().setUp()
        self.registro = open(os.devnull, 'w')
        self.servidor = ThreadingHTTPServer(('127.0.0.1', 0), puerta.make_handler(self.puerta, self.registro))
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.host = 'helios.ejemplo.ts.net:8443'

    def tearDown(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.registro.close()
        super().tearDown()

    def pedir(self, metodo, ruta, cuerpo=None, cabeceras=None):
        conexion = http.client.HTTPConnection('127.0.0.1', self.servidor.server_address[1], timeout=10)
        todas = {'Host': self.host, **(cabeceras or {})}
        if cuerpo is not None:
            cuerpo = urlencode(cuerpo).encode()
            todas['Content-Type'] = 'application/x-www-form-urlencoded'
        conexion.request(metodo, ruta, cuerpo, todas)
        respuesta = conexion.getresponse()
        datos = respuesta.read()
        conexion.close()
        return respuesta.status, respuesta.headers, datos

    def entrar(self, clave=CLAVE, origen='https://helios.ejemplo.ts.net:8443', volver='/?ventana=chat', cabeceras=None):
        return self.pedir('POST', '/_puerta/entrar', dict(usuario='andres', clave=clave, volver=volver),
                          {**({'Origin': origen} if origen else {}), **(cabeceras or {})})

    def test_entrar_da_una_cookie_segura_y_vuelve(self):
        codigo, cabeceras, _ = self.entrar()
        self.assertEqual(codigo, 303)
        self.assertEqual(cabeceras['Location'], '/?ventana=chat')
        cookie = cabeceras['Set-Cookie']
        for parte in ('__Host-helios=', 'HttpOnly', 'Secure', 'SameSite=Lax', 'Path=/'):
            self.assertIn(parte, cookie)
        token = cookie.split(';')[0].split('=', 1)[1]
        codigo, cabeceras, _ = self.pedir('GET', '/_puerta/comprobar', cabeceras={'Cookie': 'otra=1; __Host-helios=' + token})
        self.assertEqual((codigo, cabeceras['X-Puerta-Usuario']), (204, 'andres'))
        # Ya dentro, la página de entrar manda de vuelta.
        codigo, cabeceras, _ = self.pedir('GET', '/_puerta/entrar?volver=%2Fnotas', cabeceras={'Cookie': '__Host-helios=' + token})
        self.assertEqual((codigo, cabeceras['Location']), (303, '/notas'))
        # Salir la cierra.
        codigo, cabeceras, _ = self.pedir('POST', '/_puerta/salir', {}, {'Cookie': '__Host-helios=' + token,
                                                                        'Origin': 'https://helios.ejemplo.ts.net:8443'})
        self.assertEqual(codigo, 303)
        self.assertIn('Max-Age=0', cabeceras['Set-Cookie'])
        self.assertEqual(self.pedir('GET', '/_puerta/comprobar', cabeceras={'Cookie': '__Host-helios=' + token})[0], 401)

    def test_clave_mala_y_bloqueo(self):
        codigo, cabeceras, cuerpo = self.entrar('no es esta clave')
        self.assertEqual(codigo, 401)
        self.assertNotIn('Set-Cookie', cabeceras)
        self.assertIn('Usuario o contraseña incorrectos', cuerpo.decode())
        self.assertIn("frame-ancestors 'none'", cabeceras['Content-Security-Policy'])
        for _ in range(puerta.FALLOS_USUARIO - 1):
            self.entrar('no es esta clave')
        self.assertEqual(self.entrar()[0], 429)

    def test_otro_sitio_no_puede_mandar_el_formulario(self):
        self.assertEqual(self.entrar(origen='https://evil.example')[0], 403)
        self.assertEqual(self.pedir('POST', '/_puerta/entrar', dict(usuario='andres', clave=CLAVE),
                                    {'Sec-Fetch-Site': 'cross-site'})[0], 403)
        self.assertEqual(self.entrar(origen=None)[0], 303)       # sin Origin (algún navegador viejo)
        # Chrome en iPhone, 18/11: «Origin: null» con Sec-Fetch-Site same-origin. Es la propia página.
        self.assertEqual(self.entrar(origen='null', cabeceras={'Sec-Fetch-Site': 'same-origin'})[0], 303)
        # Y el rechazo es una página, no un cuerpo vacío que el móvil baja como fichero.
        codigo, cabeceras, cuerpo = self.entrar(origen='https://evil.example')
        self.assertEqual((codigo, cabeceras['Content-Type']), (403, 'text/html; charset=utf-8'))
        self.assertIn('Volver a entrar', cuerpo.decode())

    def test_volver_no_saca_del_sitio(self):
        self.assertEqual(self.entrar(volver='//evil.com/x')[1]['Location'], '/')
        _, _, cuerpo = self.pedir('GET', '/_puerta/entrar?volver=https%3A%2F%2Fevil.com')
        self.assertIn('name="volver" value="/"', cuerpo.decode())

    def test_sin_sesion_pagina_o_401(self):
        codigo, cabeceras, _ = self.pedir('GET', '/_puerta/sin-sesion', cabeceras={'X-Original-URI': '/?a=1&b=2'})
        self.assertEqual((codigo, cabeceras['Location']), (302, '/_puerta/entrar?volver=%2F%3Fa%3D1%26b%3D2'))
        codigo, _, cuerpo = self.pedir('GET', '/_puerta/sin-sesion', cabeceras={'X-Original-URI': '/api/helios/status'})
        self.assertEqual((codigo, json.loads(cuerpo)['error']), (401, 'Sin sesión: vuelve a entrar en Helios.'))
        self.assertEqual(self.pedir('POST', '/_puerta/sin-sesion', {}, {'X-Original-URI': '/'})[0], 401)

    def test_sin_cookie_o_con_cookie_inventada(self):
        self.assertEqual(self.pedir('GET', '/_puerta/comprobar')[0], 401)
        self.assertEqual(self.pedir('GET', '/_puerta/comprobar', cabeceras={'Cookie': '__Host-helios=inventada'})[0], 401)

    def test_un_fallo_interno_no_deja_pasar(self):
        token = self.puerta.entrar('andres', CLAVE)
        os.chmod(self.config / 'usuarios.json', 0o644)
        os.utime(self.config / 'usuarios.json', ns=(1, 1))   # que se relea
        self.assertEqual(self.pedir('GET', '/_puerta/comprobar', cabeceras={'Cookie': '__Host-helios=' + token})[0], 500)

    def test_el_emblema_se_ve_sin_sesion(self):
        codigo, cabeceras, cuerpo = self.pedir('GET', '/_puerta/emblema.png')
        self.assertEqual((codigo, cabeceras['Content-Type']), (200, 'image/png'))
        self.assertTrue(cuerpo.startswith(b'\x89PNG'))
        self.assertIn('/_puerta/emblema.png', self.pedir('GET', '/_puerta/entrar')[2].decode())

    def test_cuerpo_demasiado_grande(self):
        codigo = self.pedir('POST', '/_puerta/entrar', dict(usuario='andres', clave='x' * (puerta.MAX_CUERPO + 1)),
                            {'Origin': 'https://helios.ejemplo.ts.net:8443'})[0]
        self.assertEqual(codigo, 413)


if __name__ == '__main__':
    unittest.main()
