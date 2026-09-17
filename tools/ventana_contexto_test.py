"""La conversación se acumula desde el corte y se corta entera cuando ya no cabe."""
from pathlib import Path
import sys
import tempfile
import unittest
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent
from hexos.agent import catalog
from hexos.agent.chat_backend.state import AgentDependencies, TurnState
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
        # Con el catálogo real (contrato textual + declaraciones nativas) aún
        # queda una ventana útil, pero ya no fingimos que caben >20k caracteres.
        self.assertGreater(grande, 8000)
        self.agent.runtime.ctx = 8192
        self.assertLess(self.agent.history_budget(), grande)
        # Una ventana diminuta no puede dar un presupuesto negativo.
        self.agent.runtime.ctx = 2000
        self.assertEqual(self.agent.history_budget(), 4000)
        # Y un motor que no declara ventana no rompe el turno.
        self.assertEqual(Agent(self.tmp.name, RuntimeJson()).history_budget(), 6000)

    def test_el_presupuesto_mide_el_catalogo_real(self):
        antes = self.agent.history_budget()
        catalog.TOOLS['prueba.grande'] = catalog.spec('x' * 4000)
        try:
            self.assertLess(self.agent.history_budget(), antes)
        finally:
            del catalog.TOOLS['prueba.grande']

    def test_el_alias_heredado_no_se_ofrece_al_modelo(self):
        self.assertIn('device.refresh', catalog.TOOLS)
        self.assertNotIn('device.refresh', catalog.model_tools())
        self.assertNotIn('device.refresh:', catalog.render())

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


class CorteporKVTest(unittest.TestCase):
    """El corte se decide con el número del motor, no solo con una estimación.

    La conversación cabía de sobra en caracteres y aun así el turno murió: lo que
    llenaba el KV era el resultado de una herramienta, que entra a mitad de turno
    y no cuenta para ese presupuesto.
    """

    class Runtime:
        native = True
        ctx = 16384
        def __init__(self, kv): self.kv_position = kv
        def call(self, request): pass
        def generate(self, messages): return {'reply': 'ok', 'work': None}

    def montar(self, kv):
        tmp = tempfile.TemporaryDirectory(prefix='hexos-kv-')
        self.addCleanup(tmp.cleanup)
        agent = Agent(tmp.name, self.Runtime(kv))
        with agent.store() as store:
            for i in range(4):
                store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                                 ('m%d' % i, '2026-09-15', 'user', 'hola', 'hola'))
            store.db.commit()
            return agent, store, agent.window(store, 'ahora', True, agent.history_budget())

    def test_con_el_kv_holgado_no_corta_nada(self):
        _, _, (_, filas) = self.montar(3000)
        self.assertEqual(len(filas), 4)

    def test_con_el_kv_casi_lleno_corta_aunque_el_texto_sea_corto(self):
        agent, _, (_, filas) = self.montar(12500)
        self.assertEqual(filas, [], 'cuatro «hola» caben de sobra en caracteres')
        self.assertEqual(agent.context_cut['reason'], 'kv')
        self.assertEqual(agent.context_cut['kv_position'], 12500)

    def test_un_motor_sin_ese_número_se_comporta_como_antes(self):
        class Viejo(self.Runtime):
            def __init__(self): pass
            native = True
            ctx = 16384
        tmp = tempfile.TemporaryDirectory(prefix='hexos-kv-viejo-')
        self.addCleanup(tmp.cleanup)
        agent = Agent(tmp.name, Viejo())
        with agent.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('m','t','user','hola','hola'))
            store.db.commit()
            _, filas = agent.window(store, 'ahora', True, agent.history_budget())
        self.assertEqual(len(filas), 1)


class ContinuidadTrasCorteTest(unittest.TestCase):
    """Un corte abandona KV, nunca el encargo que ya estaba en curso."""

    class Runtime:
        native = True
        ctx = 8192
        kv_position = 0
        def __init__(self, messages=None):
            self.messages = [] if messages is None else messages
            self.calls = []
        def call(self, request):
            self.calls.append(request)
            self.messages = []
        def generate(self, messages):
            self.messages.extend(messages)
            return {'reply': 'Sigo con el encargo.', 'work': None}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-handoff-')
        self.runtime = self.Runtime()
        self.agent = Agent(self.tmp.name, self.runtime)

    def tearDown(self):
        self.tmp.cleanup()

    def poblar(self):
        with self.agent.store() as store:
            for role, text in [
                ('user', 'Necesito revisar el servicio Atlas y dejar anotado el resultado.'),
                ('assistant', 'Voy a revisar Atlas y conservaré el resultado.'),
                ('user', 'No pierdas ese trabajo aunque se llene el contexto.'),
                ('assistant', 'El objetivo activo es Atlas.'),
            ]:
                store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                                 (uuid4().hex, now(), role, text, text))
            store.db.commit()

    def test_el_corte_guarda_un_traspaso_literal(self):
        self.poblar()
        with self.agent.store() as store:
            _, rows = self.agent.window(store, 'nuevo', True, 40)
            handoff = self.agent.context.load_handoff(store)
        self.assertEqual(rows, [])
        self.assertIsNotNone(handoff)
        text = '\n'.join(row['text'] for row in handoff['dialogue'])
        self.assertIn('Atlas', text)
        self.assertIn('no pierdas', text.casefold())

    def test_el_primer_turno_nuevo_recibe_el_traspaso_y_luego_lo_confirma(self):
        self.poblar()
        with self.agent.store() as store:
            self.agent.window(store, 'nuevo', True, 40)
            turn = TurnState(text='continúa con ello')
            self.agent.context.prepare(store, turn)
            rendered = str(turn.messages)
            self.assertIn('TRASPASO DE CONTINUIDAD', rendered)
            self.assertIn('Atlas', rendered)
        self.agent.chat('continúa con ello')
        with self.agent.store() as store:
            self.assertIsNone(self.agent.context.load_handoff(store))

    def test_un_turno_normal_reutiliza_el_contexto_nativo(self):
        self.runtime.messages = [dict(role='system', content='prefijo ya procesado')]
        with self.agent.store() as store:
            turn = TurnState(text='siguiente paso')
            self.agent.context.prepare(store, turn)
        self.assertEqual(self.runtime.calls, [])
        self.assertEqual(turn.messages, [dict(role='user', content='siguiente paso')])


class CheckpointDentroDelTurnoTest(unittest.TestCase):
    """Un context_full conserva causalidad y no repite efectos ya ejecutados."""

    class Runtime:
        native = True
        ctx = 8192
        kv_position = 0
        thinking = False

        def __init__(self):
            self.messages = []
            self.decisions = [
                {'tool': 'device.remote', 'arguments': {
                    'name': 'synology home', 'host': 'https://casa.example'}},
                {'tool': 'nas.read', 'arguments': {
                    'device': 'synology home', 'section': 'diagnosis'}},
                RuntimeError('ERROR: context_full el turno no cabe'),
                # Simula exactamente el fallo observado: el modelo intenta
                # registrar otra vez al reconstruir el contexto.
                {'tool': 'device.remote', 'arguments': {
                    'name': 'synology home', 'host': 'https://casa.example'}},
                {'reply': 'Registrado una vez y diagnóstico recuperado.', 'work': None},
            ]
            self.tool_results = []
            self.last_generation = None

        def call(self, request):
            self.messages = []
            return {'ok': True}

        def generate(self, messages):
            self.messages.extend(messages)
            decision = self.decisions.pop(0)
            if isinstance(decision, Exception):
                raise decision
            return decision

        def tool_result(self, result):
            self.tool_results.append(result)

        def extract_facts(self, text):
            return []

        def close(self):
            pass

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-turn-checkpoint-')
        self.runtime = self.Runtime()
        self.reads = 0

        def nas_read(workspace, **kwargs):
            self.reads += 1
            return {'target': kwargs['device'], 'section': kwargs['section'],
                    'headline': 'Diagnóstico obtenido', 'facts': ['sin alertas']}

        self.agent = Agent(self.tmp.name, self.runtime,
                           dependencies=AgentDependencies(nas_read=nas_read))

    def tearDown(self):
        self.tmp.cleanup()

    def test_reconstruye_el_checkpoint_y_no_repite_la_escritura(self):
        result = self.agent.chat(
            'registra synology home con https://casa.example y mira su estado')
        self.assertEqual([step['tool'] for step in result['tools']],
                         ['device.remote', 'nas.read'])
        self.assertEqual(self.reads, 1)
        self.assertEqual(result['diagnostics']['context_retries'], 1)
        self.assertEqual(result['diagnostics']['checkpoint_reuses'], 1)
        # La cuarta generación recibió el checkpoint como llamadas nativas,
        # incluyendo el resultado del diagnóstico, no un resumen ambiguo.
        rendered = repr(self.runtime.messages)
        self.assertIn('device_remote', rendered)
        self.assertIn('nas_read', rendered)
        self.assertIn('Diagnóstico obtenido', rendered)

    def test_una_lectura_anterior_a_una_escritura_no_se_reutiliza(self):
        turn = TurnState(text='comprueba de nuevo', checkpointed_steps=2, trace=[
            dict(tool='nas.read', arguments={'device':'nas','section':'containers'},
                 changes_state=False, failed=False, result={'state':'antes'}),
            dict(tool='nas.container', arguments={'device':'nas','container':'web','action':'restart'},
                 changes_state=True, failed=False, result={'state':'running'}),
        ])
        from hexos.agent.chat_backend.ledger import completed_call
        self.assertIsNone(completed_call(
            turn, 'nas.read', {'device':'nas','section':'containers'}))
