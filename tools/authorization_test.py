"""Quién autoriza parar o levantar un servicio.

Ninguna frase de aquí está en el patrón por casualidad: las que autorizan son
las formas con las que se pide un cambio, y las que NO autorizan son las que
se parecen a una orden sin serlo. Esa segunda mitad es la que importa, porque
un falso positivo aquí tumba un servicio de verdad.
"""
import sqlite3
import unittest

from hexos.agent.chat_backend.authorization import authorize_state_change, _familias


class Store:
    """Almacén mínimo con el esquema real de `conversation`."""

    def __init__(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.execute('CREATE TABLE conversation (id TEXT PRIMARY KEY, ts TEXT NOT NULL, '
                        'role TEXT NOT NULL, text TEXT NOT NULL, model_text TEXT NOT NULL)')

    def dijo(self, quien, texto, ts, uid=None):
        self.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                        (uid or (quien + ts), ts, quien, texto, texto))
        self.db.commit()
        return uid or (quien + ts)


def turno(mensaje, propuesta=None):
    store = Store()
    if propuesta is not None:
        store.dijo('assistant', propuesta, '2026-09-21T10:00:00')
    uid = store.dijo('user', mensaje, '2026-09-21T10:00:01', uid='t1')
    return store, uid


class AutorizacionTest(unittest.TestCase):

    def permite(self, mensaje, accion, container='plex', propuesta=None):
        store, uid = turno(mensaje, propuesta)
        authorize_state_change(store, uid, 'nas.container',
                               dict(container=container, action=accion))

    def bloquea(self, mensaje, accion, container='plex', propuesta=None):
        store, uid = turno(mensaje, propuesta)
        with self.assertRaises(ValueError) as caja:
            authorize_state_change(store, uid, 'nas.container',
                                   dict(container=container, action=accion))
        return str(caja.exception)

    # ---- la orden escrita autoriza -------------------------------------
    def test_orden_directa(self):
        self.permite('reinicia el contenedor plex', 'restart')
        self.permite('párame el plex, que está dando guerra', 'stop')
        self.permite('arranca plex', 'start')
        self.permite('paralo ya', 'stop')
        self.permite('levántalo otra vez', 'start')

    def test_reiniciar_admite_descomponerse(self):
        # Quien pide un reinicio ya ha aceptado la parada, así que si el modelo
        # lo hace en dos pasos no hay nada que denegarle.
        self.permite('reinicia plex', 'stop')
        self.permite('reinicia plex', 'start')

    # ---- lo que se PARECE a una orden y no lo es -----------------------
    def test_para_como_preposicion_no_autoriza(self):
        # La trampa del español que casi se cuela: «para» es preposición mucho
        # más a menudo que imperativo. Autorizarla sería parar servicios que
        # nadie mandó parar.
        self.bloquea('mira el estado para saber si plex sigue vivo', 'stop')
        self.bloquea('¿para qué sirve el contenedor plex?', 'stop')

    def test_pedir_una_accion_no_autoriza_otra(self):
        # Parar y reiniciar acaban en estados opuestos: el reinicio deja el
        # servicio EN MARCHA, que es lo contrario de lo que se pidió.
        aviso = self.bloquea('para el contenedor plex', 'restart')
        self.assertIn('stop', aviso)
        self.bloquea('arranca plex', 'stop')

    def test_preguntar_por_el_estado_no_autoriza(self):
        aviso = self.bloquea('¿cómo está plex?', 'stop')
        self.assertIn('nas_read', aviso)   # le dice la herramienta que sí vale
        self.bloquea('mírame los contenedores del synology', 'restart')

    def test_una_orden_de_turnos_atras_no_vale_hoy(self):
        # El mensaje de ESTE turno es el que manda; que ayer pidiera un reinicio
        # no autoriza el de hoy.
        store, _ = turno('gracias')
        store.dijo('user', 'reinicia plex', '2026-09-20T09:00:00', uid='viejo')
        with self.assertRaises(ValueError):
            authorize_state_change(store, 't1', 'nas.container',
                                   dict(container='plex', action='restart'))

    # ---- decir que sí a una propuesta ----------------------------------
    def test_afirmar_una_propuesta_concreta_autoriza(self):
        self.permite('sí, dale', 'restart',
                     propuesta='Puedo reiniciar el contenedor plex si quieres.')
        self.permite('hazlo', 'stop',
                     propuesta='¿Quieres que pare plex mientras revisas el disco?')

    def test_un_si_suelto_sin_propuesta_no_autoriza(self):
        aviso = self.bloquea('sí', 'restart', propuesta='He mirado el espacio del disco.')
        self.assertIn('no se sabe a qué ha dicho que sí', aviso)

    def test_la_propuesta_tiene_que_nombrar_ESTE_contenedor(self):
        # Decir que sí a reiniciar plex no autoriza a tocar sonarr.
        self.bloquea('sí, adelante', 'restart', container='sonarr',
                     propuesta='Puedo reiniciar el contenedor plex si quieres.')

    def test_una_afirmacion_con_reparo_no_es_permiso(self):
        self.bloquea('sí, pero mira antes el estado', 'restart',
                     propuesta='Puedo reiniciar el contenedor plex.')
        self.bloquea('vale, espera', 'stop',
                     propuesta='¿Paro el contenedor plex?')

    # ---- bordes --------------------------------------------------------
    def test_sin_turno_no_se_adivina(self):
        store = Store()
        with self.assertRaises(ValueError):
            authorize_state_change(store, None, 'nas.container',
                                   dict(container='plex', action='stop'))

    def test_accion_desconocida(self):
        store, uid = turno('reinicia plex')
        with self.assertRaises(ValueError):
            authorize_state_change(store, uid, 'nas.container',
                                   dict(container='plex', action='destroy'))

    def test_inicia_no_se_lee_dentro_de_reinicia(self):
        # Entre la «e» y la «i» no hay frontera de palabra, así que `\binicia`
        # no casa dentro de «reinicia». Si esto se rompe, «reinicia» empezaría a
        # contarse como dos familias y los mensajes de error mentirían.
        self.assertEqual(_familias('reinicia plex'), {'restart'})
        self.assertEqual(_familias('inicia plex'), {'start'})


if __name__ == '__main__':
    unittest.main()
