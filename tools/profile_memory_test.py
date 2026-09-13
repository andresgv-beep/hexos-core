"""Guardar en el perfil solo lo que la persona acaba de decir, con su mensaje como evidencia."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent
from hexos.agent.work import now


class FakeRuntime:
    def call(self, request): pass
    def generate(self, messages): return {'reply': '', 'work': None}


class FakeProfile:
    def __init__(self, confirmados=None):
        self.guardados = []
        self.corregidos = []
        self.confirmados = dict(confirmados or {})
    def read(self): return ''
    def keys(self): return dict(self.confirmados)
    def remember(self, key, value, text, evidence):
        self.guardados.append(dict(key=key, value=value, text=text, evidence=evidence))
        self.confirmados[key] = value
        return 'ok'
    def correct(self, key, value, text, evidence):
        self.corregidos.append(dict(key=key, value=value, text=text, evidence=evidence))
        self.confirmados[key] = value
        return 'ok'


class ProfileMemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-perfil-test-')
        self.perfil = FakeProfile()
        self.agent = Agent(self.tmp.name, FakeRuntime(), self.perfil)

    def tearDown(self):
        self.tmp.cleanup()

    def turno(self, texto):
        uid = uuid4().hex
        with self.agent.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             (uid, now(), 'user', texto, texto))
            store.db.commit()
        return uid

    def recordar(self, texto, key, value):
        uid = self.turno(texto)
        with self.agent.store() as store:
            return self.agent.remember_fact(store, dict(key=key, value=value), uid)

    def test_guarda_lo_que_la_persona_acaba_de_decir(self):
        resultado = self.recordar('hola, me llamo Andrés', 'nombre', 'Andrés')
        self.assertTrue(resultado['saved'])
        guardado = self.perfil.guardados[0]
        # HERA deriva el sujeto de la clave: sin «yo/» rechaza por sujeto_ajeno.
        self.assertEqual((guardado['key'], guardado['value']), ('yo/nombre', 'Andrés'))
        self.assertEqual(resultado['key'], 'yo/nombre')
        # La evidencia es su mensaje literal, no una cita que aporte el modelo.
        self.assertEqual(guardado['evidence'], 'hola, me llamo Andrés')
        self.assertEqual(resultado['source'], 'user_statement')

    def test_no_puede_confirmar_lo_que_deduce(self):
        with self.assertRaises(ValueError) as caught:
            self.recordar('¿te acuerdas de cómo me llamo?', 'nombre', 'Andrés')
        self.assertIn('no aparece en el mensaje', str(caught.exception))
        self.assertEqual(self.perfil.guardados, [])

    def test_sin_perfil_configurado_lo_dice_en_vez_de_fingir(self):
        agente = Agent(self.tmp.name, FakeRuntime())
        uid = self.turno('me llamo Andrés')
        with agente.store() as store:
            with self.assertRaises(ValueError) as caught:
                agente.remember_fact(store, dict(key='nombre', value='Andrés'), uid)
        self.assertIn('no se ha guardado', str(caught.exception))

    def test_sin_turno_no_hay_evidencia(self):
        with self.agent.store() as store:
            with self.assertRaises(ValueError):
                self.agent.remember_fact(store, dict(key='nombre', value='Andrés'), None)

    def test_la_etiqueta_no_admite_cualquier_cosa(self):
        for key in ('nombre; rm -rf /', '../../etc', 'a' * 61, ''):
            with self.assertRaises(ValueError):
                self.recordar('me llamo Andrés', key, 'Andrés')
        self.assertEqual(self.perfil.guardados, [])

    def test_la_etiqueta_se_normaliza_para_no_duplicar(self):
        self.recordar('me llamo Andrés', 'Nombre', 'Andrés')
        self.assertEqual(self.perfil.guardados[0]['key'], 'yo/nombre')

    def test_una_clave_con_sujeto_propio_se_respeta(self):
        self.recordar('mi gato se llama Turbo', 'gato/nombre', 'Turbo')
        self.assertEqual(self.perfil.guardados[0]['key'], 'gato/nombre')

    def test_un_dato_nuevo_se_guarda_y_uno_existente_se_corrige(self):
        self.recordar('me llamo Andrés', 'nombre', 'Andrés')
        self.assertEqual(len(self.perfil.guardados), 1)
        self.assertEqual(self.perfil.corregidos, [])
        # El mismo valor otra vez no toca nada.
        repetido = self.recordar('sigo siendo Andrés', 'nombre', 'Andrés')
        self.assertTrue(repetido['unchanged'])
        self.assertEqual(len(self.perfil.guardados), 1)
        # Un valor distinto corrige en vez de duplicar.
        cambio = self.recordar('en realidad me llamo Andrés García', 'nombre', 'Andrés García')
        self.assertTrue(cambio['corrected'])
        self.assertEqual(cambio['previous'], 'Andrés')
        self.assertEqual(self.perfil.corregidos[0]['key'], 'yo/nombre')
        self.assertEqual(len(self.perfil.guardados), 1, 'corregir no debe crear un segundo hecho')

    def test_un_rechazo_de_hera_no_se_reporta_como_guardado(self):
        # HERA rechaza con código 0 y "rechazado: <motivo>" en stdout.
        import subprocess
        from hexos.agent.continuity import HeraProfile
        perfil = HeraProfile('/bin/true', '/tmp')
        salida = subprocess.CompletedProcess([], 0, stdout='rechazado: sin_confirmacion\n', stderr='')
        with patch('hexos.agent.continuity.subprocess.run', return_value=salida):
            with self.assertRaises(ValueError) as caught:
                perfil.remember('nombre', 'Andrés', 'nombre: Andrés', 'me llamo Andrés')
        self.assertIn('sin_confirmacion', str(caught.exception))

    def test_el_catalogo_lo_declara_como_escritura(self):
        from hexos.agent import catalog
        spec = catalog.TOOLS['profile.remember']
        self.assertEqual(spec['effect'], 'write_profile')
        self.assertEqual(set(spec['required']), {'key', 'value'})
        # Sin esto el modelo pediría una cita en vez de dejar que HexOS la tome.
        self.assertIn('no aportes citas', spec['description'])

    def test_hera_lista_se_parsea_con_sus_columnas(self):
        import subprocess
        from hexos.agent.continuity import HeraProfile
        salida = ('f3    confirmado  yo/nombre                    Andrés   [u71]\n'
                  'f4    confirmado  yo/gato                      Turbo  -> f9   [u80]\n'
                  'f1    candidato   legacy/algo suelto           x   [sin cita: legacy]\n')
        perfil = HeraProfile('/bin/true', '/tmp')
        with patch('hexos.agent.continuity.subprocess.run',
                   return_value=subprocess.CompletedProcess([], 0, stdout=salida, stderr='')):
            claves = perfil.keys()
        # Solo confirmados, y el valor sin arrastrar la sustitución ni la cita.
        self.assertEqual(claves, {'yo/nombre': 'Andrés', 'yo/gato': 'Turbo'})

    def test_el_modelo_sabe_que_existe(self):
        from hexos.agent.native import POLICY
        self.assertIn('profile_remember', POLICY)
        self.assertIn('No pidas permiso', POLICY)
        # Un ejemplo con los argumentos exactos es lo que sí sigue este modelo.
        self.assertIn('key="nombre", value="Andrés"', POLICY)
        # Fase 3: consultar el perfil antes de preguntar un dato que ya consta.
        self.assertIn('Antes de preguntar un dato de la persona', POLICY)


if __name__ == '__main__':
    unittest.main()
