"""Extracción de hechos tras el turno: tres filtros antes de que nada llegue a HERA."""
from pathlib import Path
import sys
import tempfile
import unittest
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent, AFIRMACION
from hexos.agent.work import now


class Runtime:
    """Runtime simulado que devuelve los hechos que se le indiquen."""

    def __init__(self, hechos=None):
        self.hechos = hechos if hechos is not None else []
        self.llamadas = 0

    def call(self, request): pass
    def generate(self, messages): return {'reply': '', 'work': None}

    def extract_facts(self, text):
        self.llamadas += 1
        return list(self.hechos)


class SinExtraccion:
    """El adaptador JSON antiguo no tiene extract_facts: no debe romper el turno."""
    def call(self, request): pass
    def generate(self, messages): return {'reply': '', 'work': None}


class Perfil:
    def __init__(self, confirmados=None):
        self.confirmados = dict(confirmados or {})
        self.guardados, self.corregidos = [], []
    def read(self): return ''
    def keys(self): return dict(self.confirmados)
    def remember(self, key, value, text, evidence):
        self.guardados.append((key, value)); self.confirmados[key] = value
    def correct(self, key, value, text, evidence):
        self.corregidos.append((key, value)); self.confirmados[key] = value


class FactExtractionTest(unittest.TestCase):
    def test_real_preference_is_not_overwritten_by_referentless_fragment(self):
        value = 'no hace falta que me llames andres en cada turno'
        aviso, perfil, _ = self.cosechar(value + ', no me gusta', [
            dict(key='yo/preferencia', value=value),
            dict(key='yo/preferencia', value='no me gusta')])
        self.assertEqual(perfil.confirmados['yo/preferencia'], value)
        self.assertEqual(len(perfil.guardados), 1)
        self.assertEqual(perfil.corregidos, [])

    def test_conflicting_candidates_do_not_choose_last_value(self):
        _, perfil, _ = self.cosechar('prefiero té y café', [
            dict(key='preferencia', value='té'), dict(key='yo/preferencia', value='café')])
        self.assertEqual(perfil.guardados, [])

    def test_invalid_same_key_candidate_does_not_displace_supported_value(self):
        for invalid in ('Andrés García', 'otra persona', 'Andrés ' + 'x'*201):
            with self.subTest(invalid=invalid):
                _, perfil, _ = self.cosechar('me llamo Andrés', [
                    dict(key='nombre', value='Andrés'),
                    dict(key='yo/nombre', value=invalid)])
                self.assertEqual(perfil.guardados, [('yo/nombre', 'Andrés')])

    def test_longest_supported_value_is_kept_once(self):
        _, perfil, _ = self.cosechar('me llamo Andrés García', [
            dict(key='nombre', value='Andrés'),
            dict(key='yo/nombre', value='Andrés García')])
        self.assertEqual(perfil.guardados, [('yo/nombre', 'Andrés García')])
        self.assertEqual(perfil.corregidos, [])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-extraccion-test-')

    def tearDown(self):
        self.tmp.cleanup()

    def cosechar(self, mensaje, hechos, confirmados=None, runtime=None):
        perfil = Perfil(confirmados)
        runtime = runtime or Runtime(hechos)
        agente = Agent(self.tmp.name, runtime, perfil)
        uid = uuid4().hex
        with agente.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             (uid, now(), 'user', mensaje, mensaje))
            store.db.commit()
            aviso = agente.harvest_facts(store, mensaje, uid)
        return aviso, perfil, runtime

    # --- Filtro 1: el portón ---

    def test_el_porton_deja_pasar_afirmaciones_sobre_uno_mismo(self):
        for mensaje in ['me llamo Andrés', 'vivo en Bilbao', 'mi gato se llama Turbo',
                        'recuerda que prefiero respuestas cortas', 'trabajo de electricista',
                        'en realidad me llamo Andrés García']:
            self.assertTrue(AFIRMACION.search(mensaje), mensaje)

    def test_el_porton_no_gasta_una_generacion_en_conversacion_normal(self):
        for mensaje in ['vale', 'hola qué tal', 'revisa el estado del synology',
                        'arranca el contenedor plex', 'gracias socio']:
            self.assertIsNone(AFIRMACION.search(mensaje), mensaje)
            aviso, perfil, runtime = self.cosechar(mensaje, [('yo/nombre', 'Andrés')])
            self.assertEqual(runtime.llamadas, 0, 'no debe generar nada: ' + mensaje)
            self.assertEqual(aviso, '')

    # --- Filtro 3: la verificación (el 2 lo cubre native.py) ---

    def test_no_guarda_lo_que_no_esta_en_el_mensaje(self):
        # El modelo "recuerda" un apellido que la persona no dijo en este turno.
        aviso, perfil, _ = self.cosechar('me llamo Andrés',
                                         [dict(key='yo/nombre', value='Andrés García')])
        self.assertEqual(perfil.guardados, [])
        self.assertEqual(aviso, '')

    def test_guarda_lo_que_si_esta_y_lo_dice_en_voz_alta(self):
        aviso, perfil, _ = self.cosechar('me llamo Andrés y vivo en Bilbao',
                                         [dict(key='yo/nombre', value='Andrés'),
                                          dict(key='yo/ciudad', value='Bilbao')])
        self.assertEqual(perfil.guardados, [('yo/nombre', 'Andrés'), ('yo/ciudad', 'Bilbao')])
        self.assertIn('nombre: Andrés', aviso)
        self.assertIn('ciudad: Bilbao', aviso)

    def test_un_candidato_malo_no_arrastra_a_los_buenos(self):
        aviso, perfil, _ = self.cosechar('me llamo Andrés',
                                         [dict(key='yo/oficio', value='veterinario'),
                                          dict(key='yo/nombre', value='Andrés')])
        self.assertEqual(perfil.guardados, [('yo/nombre', 'Andrés')])
        self.assertIn('Andrés', aviso)

    # --- Corrección ---

    def test_el_aviso_nombra_al_sujeto_cuando_no_eres_tu(self):
        # hermana/nombre y ordenador/nombre no pueden leerse los dos como «nombre».
        aviso, _, _ = self.cosechar('mi hermana se llama Lucía',
                                    [dict(key='hermana/nombre', value='Lucía')])
        self.assertIn('hermana', aviso)
        aviso, _, _ = self.cosechar('me llamo Andrés',
                                    [dict(key='yo/nombre', value='Andrés')])
        self.assertIn('nombre: Andrés', aviso)
        self.assertNotIn('yo', aviso)

    def test_una_contradiccion_corrige_y_lo_avisa(self):
        aviso, perfil, _ = self.cosechar(
            'en realidad me llamo Andrés García',
            [dict(key='yo/nombre', value='Andrés García')],
            confirmados={'yo/nombre': 'Andrés'})
        self.assertEqual(perfil.corregidos, [('yo/nombre', 'Andrés García')])
        self.assertEqual(perfil.guardados, [])
        self.assertIn('He corregido', aviso)
        self.assertIn('antes Andrés', aviso)

    def test_repetir_el_mismo_dato_no_dice_nada(self):
        aviso, perfil, _ = self.cosechar('me llamo Andrés',
                                         [dict(key='yo/nombre', value='Andrés')],
                                         confirmados={'yo/nombre': 'Andrés'})
        self.assertEqual((perfil.guardados, perfil.corregidos), ([], []))
        self.assertEqual(aviso, '')

    # --- Robustez: esto corre en cada turno y no puede tumbarlo ---

    def test_un_fallo_de_la_extraccion_no_rompe_el_turno(self):
        class Explota(Runtime):
            def extract_facts(self, text): raise RuntimeError('el motor se cayó')
        aviso, perfil, _ = self.cosechar('me llamo Andrés', [], runtime=Explota())
        self.assertEqual(aviso, '')
        self.assertEqual(perfil.guardados, [])

    def test_un_runtime_sin_extraccion_se_ignora(self):
        aviso, perfil, _ = self.cosechar('me llamo Andrés', [], runtime=SinExtraccion())
        self.assertEqual(aviso, '')

    def test_sin_perfil_no_intenta_nada(self):
        runtime = Runtime([dict(key='yo/nombre', value='Andrés')])
        agente = Agent(self.tmp.name, runtime)
        uid = uuid4().hex
        with agente.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             (uid, now(), 'user', 'me llamo Andrés', 'me llamo Andrés'))
            store.db.commit()
            self.assertEqual(agente.harvest_facts(store, 'me llamo Andrés', uid), '')
        self.assertEqual(runtime.llamadas, 0)


if __name__ == '__main__':
    unittest.main()
