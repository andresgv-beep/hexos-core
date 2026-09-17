"""La traza que consume una interfaz: qué se ejecutó, cuánto tardó y si cambió algo."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent


class ScriptedRuntime:
    """Devuelve una secuencia fija de decisiones, como haría el modelo."""

    def __init__(self, *decisions):
        self.decisions = list(decisions)

    def call(self, request):
        pass

    def generate(self, messages):
        return self.decisions.pop(0)


class TraceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-trace-test-')

    def tearDown(self):
        self.tmp.cleanup()

    def run_turn(self, *decisions):
        agent = Agent(self.tmp.name, ScriptedRuntime(*decisions))
        return agent, agent.chat('haz algo')

    def test_each_call_says_whether_it_changed_state(self):
        agent, result = self.run_turn(
            {'tool': 'device.list', 'arguments': {}},
            {'reply': 'Listo.', 'work': None})
        entry = result['tools'][0]
        self.assertEqual(entry['tool'], 'device.list')
        self.assertEqual(entry['effect'], 'read')
        self.assertFalse(entry['changes_state'])
        self.assertFalse(entry['failed'])
        self.assertIsInstance(entry['seconds'], float)
        self.assertTrue(entry['ts'])

    def test_a_write_is_marked_as_such_for_the_interface(self):
        agent, result = self.run_turn(
            {'tool': 'nas.container', 'arguments': {'container': 'plex', 'action': 'stop'}},
            {'reply': 'Hecho.', 'work': None})
        entry = result['tools'][0]
        self.assertEqual(entry['effect'], 'write_container')
        self.assertTrue(entry['changes_state'], 'parar un contenedor no puede figurar como lectura')

    def test_a_failed_call_is_flagged_and_still_timed(self):
        # Falla antes de ejecutarse: la traza debe existir igual, sin romper el turno.
        agent, result = self.run_turn(
            {'tool': 'nas.container', 'arguments': {'container': 'plex'}},
            {'reply': 'No pude.', 'work': None})
        entry = result['tools'][0]
        self.assertTrue(entry['failed'])
        self.assertIn('error', entry['result'])
        self.assertIsInstance(entry['seconds'], float)

    def test_history_returns_what_was_executed_after_a_reload(self):
        agent, _ = self.run_turn(
            {'tool': 'device.list', 'arguments': {}},
            {'reply': 'Listo.', 'work': None})
        with agent.store() as store:
            rows = [dict(r) for r in store.db.execute("SELECT id, role FROM conversation WHERE role='user'")]
            saved = [json.loads(e['body']) for e in store.db.execute(
                'SELECT body FROM tool_events WHERE turn_id=? ORDER BY seq', (rows[0]['id'],))]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]['tool'], 'device.list')
        # Lo persistido lleva los mismos campos que la respuesta en vivo.
        for field in ('effect', 'changes_state', 'ts', 'seconds', 'failed'):
            self.assertIn(field, saved[0])

    def test_un_registro_remoto_no_se_convierte_en_identificacion_fallida(self):
        runtime = ScriptedRuntime(
            {'tool': 'device.remote', 'arguments': {
                'name': 'synology 1', 'host': 'servidorsrv1.ddns.net'}},
            {'tool': 'device.identify', 'arguments': {
                'name': 'synology 1', 'target': 'servidorsrv1.ddns.net'}},
            {'reply': 'Registrado.', 'work': None})
        agent = Agent(self.tmp.name, runtime)
        result = agent.chat(
            'registra https://servidorsrv1.ddns.net como synology 1 socio')
        self.assertEqual([step['tool'] for step in result['tools']], ['device.remote'])
        self.assertEqual(result['tools'][0]['result']['original_address'],
                         'https://servidorsrv1.ddns.net')
        self.assertEqual(result['tools'][0]['arguments']['host'],
                         'https://servidorsrv1.ddns.net')
        self.assertEqual(result['diagnostics']['checkpoint_reuses'], 1)


class AvancePorPasoTest(unittest.TestCase):
    """Un turno con varias herramientas tiene que verse entero, no solo su primer paso."""

    class ConPreambulo(ScriptedRuntime):
        """Como el modelo nativo: a veces antecede la llamada con una frase suya."""

        def __init__(self, *decisions, preambulos=()):
            super().__init__(*decisions)
            self.preambulos = list(preambulos)
            self.last_preamble = None
            self.anuncios = 0

        def generate(self, messages):
            self.last_preamble = self.preambulos.pop(0) if self.preambulos else None
            return super().generate(messages)

        def announce(self, tool, arguments, request):
            self.anuncios += 1
            return 'Voy a mirarlo.'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-avance-test-')

    def tearDown(self):
        self.tmp.cleanup()

    def turno(self, runtime):
        agent = Agent(self.tmp.name, runtime)
        return agent, agent.chat('revisa y luego mira los equipos')

    def test_cada_llamada_deja_su_aviso(self):
        runtime = self.ConPreambulo(
            {'tool': 'device.list', 'arguments': {}},
            {'tool': 'device.list', 'arguments': {'query': 'nas'}},
            {'reply': 'Listo.', 'work': None},
            preambulos=['Primero miro el inventario.', 'Ahora filtro por nas.', None])
        agent, resultado = self.turno(runtime)
        textos = [m['text'] for m in resultado['progress']['messages']]
        self.assertEqual(textos, ['Primero miro el inventario.', 'Ahora filtro por nas.'])
        # Y quedan guardados en orden, no solo en la respuesta.
        with agent.store() as store:
            filas = [r['text'] for r in store.db.execute(
                'SELECT text FROM progress_events ORDER BY rowid')]
        self.assertEqual(filas, textos)

    def test_la_inferencia_de_respaldo_solo_se_paga_una_vez(self):
        # Una generación entera por paso solo para redactar «voy a mirarlo» costaría
        # más que el paso; sin preámbulo propio, la herramienta ya se ve en la traza.
        runtime = self.ConPreambulo(
            {'tool': 'device.list', 'arguments': {}},
            {'tool': 'device.list', 'arguments': {'query': 'nas'}},
            {'reply': 'Listo.', 'work': None},
            preambulos=[None, None, None])
        agent, resultado = self.turno(runtime)
        self.assertEqual(runtime.anuncios, 1)
        self.assertEqual([m['text'] for m in resultado['progress']['messages']],
                         ['Voy a mirarlo.'])

    def test_el_estado_final_no_borra_los_avances(self):
        runtime = self.ConPreambulo(
            {'tool': 'device.list', 'arguments': {}},
            {'reply': 'Ya está.', 'work': None},
            preambulos=['Miro el inventario.', None])
        agent, resultado = self.turno(runtime)
        self.assertEqual(resultado['reply'], 'Ya está.')
        self.assertEqual(len(resultado['progress']['messages']), 1)


class VerificacionTest(unittest.TestCase):
    """«Se ejecutó» y «logró lo que pretendía» no son lo mismo."""

    class Perfil:
        def __init__(self, confirmados=None, rompe=False):
            self.confirmados = dict(confirmados or {})
            self.rompe = rompe
        def read(self): return ''
        def keys(self):
            if self.rompe: raise RuntimeError('HERA no contesta')
            return dict(self.confirmados)
        def remember(self, key, value, text, evidence): self.confirmados[key] = value
        def correct(self, key, value, text, evidence): self.confirmados[key] = value

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-verif-')

    def tearDown(self):
        self.tmp.cleanup()

    def agente(self, perfil=None, *decisions):
        return Agent(self.tmp.name, ScriptedRuntime(*decisions), perfil)

    def test_una_lectura_no_tiene_nada_que_comprobar(self):
        agent = self.agente(None,
            {'tool': 'device.list', 'arguments': {}}, {'reply': 'Ya.', 'work': None})
        entrada = agent.chat('mira')['tools'][0]
        self.assertEqual(entrada['verification'], 'no_requerida')

    def test_refrescar_la_red_ya_no_finge_ser_una_escritura(self):
        agent = self.agente(None,
            {'tool': 'device.refresh', 'arguments': {}}, {'reply': 'Ya.', 'work': None})
        entrada = agent.chat('actualiza')['tools'][0]
        self.assertEqual(entrada['verification'], 'no_requerida')
        self.assertFalse(entrada['changes_state'])

    def test_un_error_nunca_es_confirmacion(self):
        agent = self.agente(None,
            {'tool': 'device.identify', 'arguments': {'target': 'no existe', 'name': 'x'}},
            {'reply': 'Ya.', 'work': None})
        entrada = agent.chat('identifica')['tools'][0]
        self.assertEqual(entrada['verification'], 'no_cumplida')

    def test_el_perfil_se_relee_para_poder_decir_guardado(self):
        # HERA rechaza con código 0, así que «lo guardé» no vale como prueba.
        perfil = self.Perfil()
        agent = self.agente(perfil,
            {'tool': 'profile.remember', 'arguments': {'key': 'nombre', 'value': 'Andrés'}},
            {'reply': 'Ya.', 'work': None})
        entrada = agent.chat('me llamo Andrés')['tools'][0]
        self.assertEqual(entrada['verification'], 'confirmada')
        self.assertIn('yo/nombre = Andrés', entrada['evidence'])

    def test_si_el_perfil_no_lo_tiene_no_se_dice_hecho(self):
        class Traidor(self.Perfil):
            def remember(self, key, value, text, evidence): pass   # como el rechazo de HERA
        perfil = Traidor()
        agent = self.agente(perfil,
            {'tool': 'profile.remember', 'arguments': {'key': 'nombre', 'value': 'Andrés'}},
            {'reply': 'Ya.', 'work': None})
        entrada = agent.chat('me llamo Andrés')['tools'][0]
        self.assertEqual(entrada['verification'], 'no_cumplida')
        self.assertIn('Andrés', entrada['evidence'])

    def test_no_poder_comprobar_no_es_ni_exito_ni_fallo(self):
        # HERA contesta al mirar si el dato existía y se cae al ir a comprobarlo.
        # Si fallara antes, el turno entero falla y eso ya es otro caso.
        class SeCaeAlComprobar(self.Perfil):
            def __init__(self): super().__init__(); self.veces = 0
            def keys(self):
                self.veces += 1
                if self.veces > 1: raise RuntimeError('HERA no contesta')
                return dict(self.confirmados)
        perfil = SeCaeAlComprobar()
        agent = self.agente(perfil,
            {'tool': 'profile.remember', 'arguments': {'key': 'nombre', 'value': 'Andrés'}},
            {'reply': 'Ya.', 'work': None})
        entrada = agent.chat('me llamo Andrés')['tools'][0]
        self.assertEqual(entrada['verification'], 'desconocida')
        self.assertIn('no se pudo releer', entrada['evidence'])


class CierreTest(unittest.TestCase):
    """El cierre sale de lo comprobado, no de que el modelo decidiera responder."""

    def cierre(self, *estados, acceso=False):
        traza = [dict(tool='t%d' % i, verification=e, evidence='por qué',
                      result=dict(access_required=True) if acceso and i == 0 else {})
                 for i, e in enumerate(estados)]
        return Agent.closure(traza)

    def test_todo_comprobado(self):
        r = self.cierre('confirmada', 'no_requerida')
        self.assertEqual(r['reason'], 'comprobado')
        self.assertEqual(r['unverified'], [])

    def test_una_que_no_llego_deja_el_turno_parcial(self):
        r = self.cierre('confirmada', 'no_cumplida')
        self.assertEqual(r['reason'], 'parcial')
        self.assertEqual([p['tool'] for p in r['unverified']], ['t1'])

    def test_no_poder_comprobar_deja_el_turno_incierto(self):
        r = self.cierre('confirmada', 'desconocida')
        self.assertEqual(r['reason'], 'incierto')
        self.assertIn('No saber no es haberlo hecho', r['note'])

    def test_lo_que_no_llego_pesa_mas_que_lo_que_no_se_sabe(self):
        # Con las dos, lo que falló es la noticia; lo incierto viene detrás.
        r = self.cierre('desconocida', 'no_cumplida')
        self.assertEqual(r['reason'], 'parcial')
        self.assertEqual(len(r['unverified']), 2)

    def test_faltar_acceso_manda_sobre_todo_lo_demas(self):
        r = self.cierre('no_cumplida', acceso=True)
        self.assertEqual(r['reason'], 'bloqueado')

    def test_responder_sin_ejecutar_nada_se_dice_tal_cual(self):
        r = Agent.closure([])
        self.assertEqual(r['reason'], 'sin_operaciones')
        self.assertEqual(r['unverified'], [])

    def test_el_cierre_viaja_con_la_respuesta(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, ScriptedRuntime(
                {'tool': 'device.identify', 'arguments': {'target': 'no existe', 'name': 'x'}},
                {'reply': 'Hecho.', 'work': None}))
            resultado = agent.chat('identifica algo')
        # El modelo dice «Hecho.»; la traza dice que no.
        self.assertEqual(resultado['reply'], 'Hecho.')
        self.assertEqual(resultado['closure']['reason'], 'parcial')
        self.assertEqual(resultado['closure']['unverified'][0]['tool'], 'device.identify')


if __name__ == '__main__':
    unittest.main()
