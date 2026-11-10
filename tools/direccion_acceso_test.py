"""Corregir la dirección de un equipo que ya tiene acceso guardado.

El 10/11 se registró un NAS con una errata en el nombre de dominio, se guardó su
acceso y después se corrigió la dirección con device_remote. El inventario quedó
bien, pero la ficha de acceso conservó la errata y mandaba sobre él: cada lectura
siguió saliendo hacia la dirección mala mientras device_remote decía «guardado».
"""
import json
import tempfile
import unittest
from unittest.mock import patch

from hexos.agent import hosts, nas_session
from hexos.agent.chat import Agent
from hexos.agent.work import now

MALA = 'servisor.example.net'
BUENA = 'servidor.example.net'


class Runtime:
    def call(self, request): pass
    def generate(self, messages): return {'reply': '', 'work': None}


def sin_conexion(*args, **kwargs):
    raise AssertionError('No debía abrirse ninguna conexión SSH')


class DireccionCorregidaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-direccion-')
        self.ws = self.tmp.name
        self.agente = Agent(self.ws, Runtime())
        self.turnos = 0

    def tearDown(self):
        self.tmp.cleanup()

    def decir(self, store, texto):
        self.turnos += 1
        turno = 'u' + str(self.turnos)
        store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                         (turno, now(), 'user', texto, texto))
        store.db.commit()
        return turno

    def registrar(self, direccion, nombre='nas'):
        with self.agente.store() as store:
            turno = self.decir(store, direccion)
            return self.agente.tool(store, 'device.remote',
                                    dict(name=nombre, host=direccion, kind='NAS'), turn_id=turno)

    def leer(self, nombre='nas'):
        with self.agente.store() as store:
            turno = self.decir(store, 'lee el estado')
            with patch('pexpect.spawn', side_effect=sin_conexion):
                return self.agente.tool(store, 'nas.read',
                                        dict(device=nombre, section='system'), turn_id=turno)

    def con_errata_y_corregido(self):
        self.registrar(MALA)
        self.agente.save_access(dict(device='nas', user='helios', password='secreta',
                                     host=MALA, port=23))
        return self.registrar(BUENA)

    def test_corregir_avisa_de_que_el_acceso_era_para_la_anterior(self):
        salida = self.con_errata_y_corregido()
        self.assertTrue(salida['saved'])
        self.assertEqual(salida['access_conflict']['saved_for'], MALA)
        self.assertEqual(salida['access_conflict']['registered_now'], BUENA)

    def test_registrar_sin_acceso_previo_no_avisa_de_nada(self):
        self.assertNotIn('access_conflict', self.registrar(MALA))
        self.assertNotIn('access_conflict', self.registrar(BUENA))

    def test_la_ruta_pasa_a_ser_la_registrada_y_va_marcada(self):
        self.con_errata_y_corregido()
        ruta = hosts.resolve(self.ws, 'nas')
        self.assertEqual(ruta['host'], BUENA)
        self.assertEqual(ruta['access_stale'], MALA)

    def test_no_se_conecta_a_ninguna_de_las_dos_con_el_acceso_viejo(self):
        self.con_errata_y_corregido()
        with patch('pexpect.spawn', side_effect=sin_conexion):
            with self.assertRaises(hosts.AccessNeeded) as caught:
                nas_session.execute_remote(self.ws, 'nas', 'true', 'system')
        self.assertEqual(caught.exception.reason, 'address_changed')
        self.assertEqual(caught.exception.located['host'], BUENA)
        self.assertIn(MALA, str(caught.exception))
        self.assertIn('no pidas la contraseña por el chat', str(caught.exception))

    def test_la_lectura_abre_la_ventana_para_la_direccion_nueva(self):
        self.con_errata_y_corregido()
        salida = self.leer()
        self.assertTrue(salida['access_required'])
        self.assertEqual(salida['reason'], 'address_changed')
        self.assertIn('dirección nueva', salida['instruction'])
        peticion = self.agente.credential_request
        self.assertEqual(peticion['host'], BUENA)
        self.assertEqual(peticion['access_stale'], MALA)
        self.assertEqual(peticion['reason'], 'address_changed')
        # El puerto y el usuario guardados se enseñan para poder corregirlos.
        self.assertEqual(peticion['port'], 23)
        self.assertEqual(peticion['user'], 'helios')

    def test_confirmar_en_la_ventana_mueve_el_acceso_y_cierra_el_conflicto(self):
        self.con_errata_y_corregido()
        self.leer()
        # Sin dirección escrita: la ventana no puede dejar el acceso en la anterior.
        guardado = self.agente.save_access(dict(device='nas', user='helios',
                                                password='secreta', port=30))
        self.assertEqual(guardado['host'], BUENA)
        ficha = hosts.card(self.ws, 'nas')
        self.assertEqual(ficha['host'], BUENA)
        self.assertEqual(ficha['port'], 30)
        self.assertIsNone(hosts.stale_access(self.ws, 'nas'))
        ruta = hosts.resolve(self.ws, 'nas')
        self.assertEqual(ruta['host'], BUENA)
        self.assertNotIn('access_stale', ruta)

    def test_confirmar_escribiendo_la_direccion_tambien_lo_cierra(self):
        self.con_errata_y_corregido()
        self.leer()
        self.agente.save_access(dict(device='nas', user='helios', password='secreta',
                                     host=BUENA, port=30))
        self.assertEqual(hosts.card(self.ws, 'nas')['host'], BUENA)
        self.assertIsNone(hosts.stale_access(self.ws, 'nas'))

    def test_la_contrasena_no_aparece_en_ninguna_salida(self):
        salida = self.con_errata_y_corregido()
        self.assertNotIn('secreta', json.dumps(salida))
        self.assertNotIn('secreta', json.dumps(self.leer()))
        self.assertNotIn('secreta', json.dumps(self.agente.credential_request))


class SinFalsosConflictosTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-direccion-')
        self.ws = self.tmp.name
        self.agente = Agent(self.ws, Runtime())

    def tearDown(self):
        self.tmp.cleanup()

    def registrar(self, direccion):
        with self.agente.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             ('u' + direccion, now(), 'user', direccion, direccion))
            store.db.commit()
            return self.agente.tool(store, 'device.remote', dict(name='nas', host=direccion),
                                    turn_id='u' + direccion)

    def test_acceso_y_registro_iguales_siguen_como_antes(self):
        self.registrar(BUENA)
        self.agente.save_access(dict(device='nas', user='helios', password='x', host=BUENA))
        self.assertIsNone(hosts.stale_access(self.ws, 'nas'))
        ruta = hosts.resolve(self.ws, 'nas')
        self.assertEqual(ruta['host'], BUENA)
        self.assertNotIn('access_stale', ruta)

    def test_una_direccion_distinta_escrita_en_la_ventana_no_es_un_conflicto(self):
        # Quien escribe en la ventana otra dirección lo ha decidido así: manda la
        # del acceso, como siempre, y no se le vuelve a preguntar en cada lectura.
        self.registrar(BUENA)
        self.agente.save_access(dict(device='nas', user='helios', password='x',
                                     host='192.168.1.50'))
        self.assertIsNone(hosts.stale_access(self.ws, 'nas'))
        self.assertEqual(hosts.resolve(self.ws, 'nas')['host'], '192.168.1.50')

    def test_pero_si_despues_cambia_el_registro_si_lo_es(self):
        self.registrar(BUENA)
        self.agente.save_access(dict(device='nas', user='helios', password='x',
                                     host='192.168.1.50'))
        self.registrar('otro.example.net')
        self.assertEqual(hosts.stale_access(self.ws, 'nas')['saved_for'], '192.168.1.50')
        self.assertEqual(hosts.resolve(self.ws, 'nas')['host'], 'otro.example.net')

    def test_acceso_sin_registro_en_el_inventario_no_cambia(self):
        hosts.save(self.ws, 'suelto', 'helios', 'x', 22, BUENA)
        self.assertIsNone(hosts.stale_access(self.ws, 'suelto'))
        self.assertEqual(hosts.resolve(self.ws, 'suelto')['host'], BUENA)

    def test_ficha_antigua_sin_el_campo_nuevo_se_compara_por_su_direccion(self):
        # Las fichas guardadas antes de este cambio no llevan registered_host.
        self.registrar(MALA)
        self.agente.save_access(dict(device='nas', user='helios', password='x', host=MALA))
        fichas = hosts.cards(self.ws)
        del fichas['nas']['registered_host']
        hosts._write_private(hosts.devices_path(self.ws), fichas)
        self.assertIsNone(hosts.stale_access(self.ws, 'nas'))
        self.registrar(BUENA)
        self.assertEqual(hosts.stale_access(self.ws, 'nas')['saved_for'], MALA)


if __name__ == '__main__':
    unittest.main()
