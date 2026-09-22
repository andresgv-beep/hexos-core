"""Lo que falla sin decirlo.

«No hay» y «no pude mirar» son dos respuestas distintas, y confundirlas es la
peor forma de mentir que tiene un guardián: negar con aplomo algo que ni
siquiera llegó a buscar. Estas pruebas fijan que se distingan.
"""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent
from hexos.agent.work import now


class Runtime:
    def __init__(self, revienta=False):
        self.revienta = revienta
    def call(self, request): pass
    def generate(self, messages): return {'reply': '', 'work': None}
    def extract_facts(self, text):
        if self.revienta:
            raise RuntimeError('el extractor se cayó')
        return []


class Perfil:
    def read(self): return ''
    def keys(self): return {}
    def remember(self, key, value, text, evidence): pass
    def correct(self, key, value, text, evidence): pass


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-silencios-')

    def tearDown(self):
        self.tmp.cleanup()

    def agente(self, runtime=None, perfil=None):
        return Agent(self.tmp.name, runtime or Runtime(), perfil)

    def con_turno(self, agente, mensaje):
        uid = uuid4().hex
        with agente.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             (uid, now(), 'user', mensaje, mensaje))
            store.db.commit()
        return uid


class BuscarEnElArchivoTest(Base):
    PREGUNTA = '¿te acuerdas de lo que hablamos del synology?'

    def buscar(self, agente, uid, revienta):
        objetivo = 'hexos.agent.chat_backend.memory.history_tool'
        with agente.store() as store:
            if revienta:
                with patch(objetivo, side_effect=RuntimeError('la base se cayó')):
                    return agente.recall_history(store, self.PREGUNTA, uid)
            with patch(objetivo, return_value=dict(matches=[])):
                return agente.recall_history(store, self.PREGUNTA, uid)

    def test_un_fallo_al_buscar_no_se_cuenta_como_ausencia(self):
        agente = self.agente()
        uid = self.con_turno(agente, self.PREGUNTA)
        paso = self.buscar(agente, uid, revienta=True)
        self.assertIsNotNone(paso, 'antes devolvía None y el turno se quedaba sin traza')
        self.assertIs(paso['result']['searched'], False)
        self.assertTrue(paso['failed'])
        self.assertEqual(paso['verification'], 'desconocida')
        self.assertIn('la base se cayó', paso['result']['error'])
        # Y lo que lee el modelo le prohíbe explícitamente concluir ausencia.
        self.assertIn('FALLÓ', paso['result']['note'])
        self.assertIn('No digas que no hay registro', paso['result']['note'])

    def test_el_turno_se_cierra_como_incierto_y_no_como_comprobado(self):
        agente = self.agente()
        uid = self.con_turno(agente, self.PREGUNTA)
        paso = self.buscar(agente, uid, revienta=True)
        cierre = agente.closure([paso], 'No he podido consultar el archivo.')
        self.assertEqual(cierre['reason'], 'incierto')
        self.assertTrue(cierre['unverified'], 'el paso sin comprobar tiene que salir en la lista')

    def test_buscar_bien_y_no_encontrar_nada_sigue_siendo_otra_cosa(self):
        # La distinción entera depende de esto: cero resultados de una búsqueda
        # que SÍ ocurrió es una ausencia de verdad, y no debe marcarse igual.
        agente = self.agente()
        uid = self.con_turno(agente, self.PREGUNTA)
        paso = self.buscar(agente, uid, revienta=False)
        self.assertIsNot(paso['result'].get('searched'), False)
        self.assertFalse(paso['failed'])
        self.assertEqual(paso['result']['matches'], [])
        self.assertEqual(agente.closure([paso], 'No encontré nada.')['reason'], 'comprobado')


class ExtraerHechosTest(Base):
    def test_si_la_extraccion_revienta_queda_dicho(self):
        agente = self.agente(Runtime(revienta=True), Perfil())
        uid = self.con_turno(agente, 'me llamo Andrés')
        traza = []
        with agente.store() as store:
            aviso = agente.harvest_facts(store, 'me llamo Andrés', uid, traza)
        self.assertEqual(aviso, '', 'no se anuncia nada porque nada se guardó')
        self.assertEqual(len(traza), 1, 'antes la traza se quedaba vacía')
        self.assertIs(traza[0]['result']['extracted'], False)
        self.assertEqual(traza[0]['verification'], 'desconocida')
        self.assertEqual(agente.closure(traza, 'Hecho.')['reason'], 'incierto')


class PortonDeHechosTest(Base):
    """El descarte es correcto; lo que estaba mal era que no dejara rastro."""

    def descartados(self, agente):
        with agente.store() as store:
            return [fila[0] for fila in
                    store.db.execute('SELECT text FROM fact_gate_skips ORDER BY ts').fetchall()]

    def cosechar(self, agente, mensaje):
        uid = self.con_turno(agente, mensaje)
        with agente.store() as store:
            return agente.harvest_facts(store, mensaje, uid, [])

    def test_un_hueco_del_patron_deja_muestra_para_poder_ensancharlo(self):
        # «mi cumpleaños es en marzo» no casa con AFIRMACION y nunca se guarda.
        # Sin esta muestra nadie se entera jamás de que ese dato se perdió.
        agente = self.agente(Runtime(), Perfil())
        self.assertEqual(self.cosechar(agente, 'mi cumpleaños es en marzo'), '')
        self.assertEqual(self.descartados(agente), ['mi cumpleaños es en marzo'])

    def test_la_conversacion_normal_no_ensucia_la_muestra(self):
        agente = self.agente(Runtime(), Perfil())
        for mensaje in ['vale', 'gracias socio', 'revisa el estado del synology',
                        'arranca el contenedor plex']:
            self.cosechar(agente, mensaje)
        self.assertEqual(self.descartados(agente), [])

    def test_la_muestra_esta_acotada(self):
        from hexos.agent.chat_backend.memory import SKIPS_QUE_SE_GUARDAN
        agente = self.agente(Runtime(), Perfil())
        for i in range(SKIPS_QUE_SE_GUARDAN + 25):
            self.cosechar(agente, 'mi dato numero ' + str(i))
        self.assertEqual(len(self.descartados(agente)), SKIPS_QUE_SE_GUARDAN,
                         'es una muestra, no un archivo que crece sin fin')

    def test_auditar_no_puede_tumbar_un_turno(self):
        agente = self.agente(Runtime(), Perfil())
        uid = self.con_turno(agente, 'mi cumpleaños es en marzo')
        with agente.store() as store:
            store.db.execute('DROP TABLE fact_gate_skips')
            store.db.commit()
            self.assertEqual(agente.harvest_facts(store, 'mi cumpleaños es en marzo', uid, []), '')


if __name__ == '__main__':
    unittest.main()
