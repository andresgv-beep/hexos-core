"""La conversación se acumula desde el corte y se corta entera cuando ya no cabe."""
from pathlib import Path
import sys
import tempfile
import unittest
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent
from hexos.agent.work import now


class Runtime:
    native = True
    ctx = 16384
    def call(self, request): pass
    def generate(self, messages): return {'reply': '', 'work': None}


class RuntimeJson:
    def call(self, request): pass
    def generate(self, messages): return {'reply': '', 'work': None}


class VentanaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-ventana-test-')
        self.agent = Agent(self.tmp.name, Runtime())

    def tearDown(self):
        self.tmp.cleanup()

    def poblar(self, cuantos, largo=100):
        with self.agent.store() as store:
            for i in range(cuantos):
                texto = ('m%03d ' % i) + 'x' * largo
                store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                                 (uuid4().hex, now(), 'user' if i % 2 == 0 else 'assistant',
                                  texto, texto))
            store.db.commit()

    def ventana(self, budget=None):
        with self.agent.store() as store:
            return self.agent.window(store, 'turno-actual', True,
                                     self.agent.history_budget() if budget is None else budget)

    def test_el_presupuesto_sale_de_la_ventana_del_motor(self):
        # No es un número a ojo: crece con --ctx y nunca baja de un mínimo usable.
        grande = self.agent.history_budget()
        self.assertGreater(grande, 20000)
        self.agent.runtime.ctx = 8192
        self.assertLess(self.agent.history_budget(), grande)
        # Una ventana diminuta no puede dar un presupuesto negativo.
        self.agent.runtime.ctx = 2000
        self.assertEqual(self.agent.history_budget(), 4000)
        # Y un motor que no declara ventana no rompe el turno.
        self.assertEqual(Agent(self.tmp.name, RuntimeJson()).history_budget(), 6000)

    def test_acumula_en_vez_de_deslizar(self):
        # Con ventana deslizante el mensaje más viejo desaparecía en cada turno y
        # el prompt cambiaba por delante; acumulando, lo de antes es un prefijo fijo.
        self.poblar(12)
        _, primera = self.ventana()
        self.poblar(2)
        _, segunda = self.ventana()
        self.assertEqual(len(primera), 12)
        self.assertEqual(len(segunda), 14)
        # Lo que ya estaba sigue igual y en el mismo sitio: eso es el prefijo.
        self.assertEqual([f['id'] for f in primera], [f['id'] for f in segunda[:12]])

    def test_cuando_no_cabe_corta_entero_y_no_por_el_principio(self):
        self.poblar(40, largo=200)
        corte_previo, _ = self.ventana(budget=100000)
        nuevo, filas = self.ventana(budget=2000)
        self.assertEqual(filas, [], 'un corte deja la ventana vacía, no medio historial')
        self.assertGreater(nuevo, corte_previo)
        # Y el turno siguiente vuelve a acumular desde ahí.
        self.poblar(3)
        _, despues = self.ventana(budget=100000)
        self.assertEqual(len(despues), 3)

    def test_el_corte_queda_anotado_para_poder_avisar(self):
        self.poblar(40, largo=200)
        self.assertIsNone(self.agent.context_cut)
        self.ventana(budget=2000)
        self.assertEqual(self.agent.context_cut['messages'], 40)
        self.assertGreater(self.agent.context_cut['characters'], 2000)

    def test_cortar_no_borra_el_archivo(self):
        self.poblar(40, largo=200)
        self.ventana(budget=2000)
        with self.agent.store() as store:
            quedan = store.db.execute('SELECT COUNT(*) FROM conversation').fetchone()[0]
            hallado = self.agent.tool(store, 'history.search', {'query': 'm000'})
        self.assertEqual(quedan, 40, 'el corte es de contexto, no de datos')
        self.assertTrue(hallado['matches'], 'lo cortado se sigue pudiendo buscar')

    def test_la_ruta_json_conserva_su_ventana_de_ocho(self):
        agente = Agent(self.tmp.name, RuntimeJson())
        self.poblar(20)
        with agente.store() as store:
            _, filas = agente.window(store, 'turno-actual', False, 100000)
        self.assertEqual(len(filas), 8)


if __name__ == '__main__':
    unittest.main()
