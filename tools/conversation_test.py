"""Regresiones del contrato y continuidad. Sin GPU ni efectos fuera de temporales."""
from collections import deque
import io
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent
from hexos.agent.context import native_messages
from hexos.agent.decisions import InvalidDecision, validate_reply
from hexos.agent.native import NativeRuntime, NativeSyntax, split_thinking


def referencias(messages):
    """El bloque de datos, esté donde esté. Va al final para no invalidar el
    prefijo del KV, así que buscarlo por índice sería fijar justo lo que cambió."""
    for m in messages:
        if isinstance(m.get('content'), str) and m['content'].startswith('REFERENCIAS DE CONTEXTO'):
            return m['content']
    return ''


def runtime_with_outputs(*outputs):
    runtime = object.__new__(NativeRuntime)
    runtime.messages = []
    runtime.pending = deque()
    runtime.current = None
    runtime.names = {'history_recent':'history.recent'}
    runtime.tools = []
    runtime.template = SimpleNamespace(render=lambda **kw: repr(kw))
    runtime.proc = SimpleNamespace(stdin=io.BytesIO())
    events = iter([(['0','1','1','0','eos'], text) for text in outputs])
    runtime.event = lambda: next(events)
    runtime.announce = lambda *args: None
    return runtime


class Tests(unittest.TestCase):
    def test_reanudacion_nativa_repone_la_llamada_antes_del_resultado(self):
        runtime = object.__new__(NativeRuntime)
        runtime.messages = [{'role':'system', 'content':'contexto'}]
        runtime.pending = deque()
        runtime.current = None
        runtime.names = {'nas_read':'nas.read'}
        runtime.last_preamble = 'no debe heredarse'
        operacion = {'tool':'nas.read',
                     'arguments':{'device':'synology 2', 'section':'diagnosis'}}
        runtime.begin_tool([{'role':'user', 'content':'diagnostica synology 2'}], operacion)
        runtime.tool_result({'headline':'lectura actual'})
        llamada = runtime.messages[-1]
        self.assertEqual(llamada['tool_calls'][0]['function']['name'], 'nas_read')
        self.assertEqual(llamada['tool_responses'][0]['response']['headline'], 'lectura actual')
        self.assertIsNone(runtime.current)
        self.assertIsNone(runtime.last_preamble)

    def test_missing_preamble_is_generated_without_replacing_pending_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=runtime_with_outputs('<|tool_call>call:history_recent{}<tool_call|>',
                                         'Revisaré lo que hemos hablado.', 'Historial consultado.')
            del runtime.announce
            result=Agent(tmp,runtime).chat('Consulta el historial.')
            self.assertEqual(result['progress']['messages'][0]['text'],'Revisaré lo que hemos hablado.')
            self.assertEqual([t['tool'] for t in result['tools']],['history.recent'])
            self.assertEqual(result['reply'],'Historial consultado.')
            self.assertNotIn('Revisaré lo que hemos hablado.',repr(runtime.messages))
    def test_progress_is_published_before_execution_and_kept_out_of_model_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=runtime_with_outputs('<|tool_call>call:history_recent{}<tool_call|>', 'Consultado.')
            agent=Agent(tmp,runtime)
            original=agent.tool
            def checked(store,name,args,**kwargs):
                self.assertTrue(agent.progress['messages'])
                self.assertEqual(store.db.execute('SELECT COUNT(*) FROM progress_events').fetchone()[0],1)
                return original(store,name,args,**kwargs)
            agent.tool=checked
            result=agent.chat('Consulta el historial.')
            self.assertEqual(len(result['progress']['messages']),1)
            with agent.store() as s:
                self.assertEqual(s.db.execute("SELECT COUNT(*) FROM conversation WHERE role='assistant'").fetchone()[0],1)
            self.assertNotIn('Voy a buscarlo',repr(runtime.messages))

    def test_native_call_after_preamble_executes_only_delimited_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=runtime_with_outputs('Voy a consultar.\n<|tool_call>call:history_recent{}<tool_call|>', 'Consultado.')
            result=Agent(tmp,runtime).chat('Consulta el historial.')
            self.assertEqual([t['tool'] for t in result['tools']],['history.recent'])
            self.assertEqual(result['reply'],'Consultado.')
            self.assertEqual(result['progress']['messages'][0]['text'],'Voy a consultar.')

    def test_preamble_is_not_reused_or_taken_from_thinking(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=runtime_with_outputs('<|channel>thought\nTexto privado\n<channel|>Reviso lo que hablamos.\n<|tool_call>call:history_recent{}<tool_call|>',
                                         'Listo.', '<|tool_call>call:history_recent{}<tool_call|>', 'Listo otra vez.')
            agent=Agent(tmp,runtime)
            first=agent.chat('Busca en el historial.')
            second=agent.chat('Vuelve a consultar.')
            self.assertEqual(first['progress']['messages'][0]['text'],'Reviso lo que hablamos.')
            self.assertEqual(second['progress']['messages'][0]['text'],'Me pongo con ello y te cuento el resultado.')

    def test_acceptance_keeps_original_proposal_in_dialogue(self):
        with tempfile.TemporaryDirectory() as tmp:
            proposal = 'Puedo consultar los vecinos de la red. ¿Quieres que lo haga?'
            runtime = runtime_with_outputs(proposal, 'Vale.', 'Consultando.')
            agent = Agent(tmp, runtime)
            agent.chat('socio busca ip en toda la red')
            agent.chat('eso te queria decir')
            agent.chat('pues hazlo')
            dialogue = [m.get('content') for m in runtime.messages if m['role'] != 'system']
            self.assertIn(proposal, dialogue)
            self.assertLess(dialogue.index(proposal), dialogue.index('pues hazlo'))

    def test_thinking_is_not_a_response_or_an_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = runtime_with_outputs('<|channel>thought\nConsidero history_recent().\n<channel|>Hola.')
            result = Agent(tmp, runtime).chat('Hola.')
            self.assertEqual(result['reply'], 'Hola.')
            self.assertEqual(result['tools'], [])
            self.assertNotIn('Considero', runtime.messages[-1]['content'])

    def test_open_thinking_continuation_and_truncation(self):
        visible, reasoning = split_thinking('Dato recuperado.\n<channel|>Te llamas Elena.', True)
        self.assertEqual(visible, 'Te llamas Elena.')
        self.assertEqual(reasoning, 'Dato recuperado.\n')
        with self.assertRaises(NativeSyntax):
            split_thinking('Pensamiento cortado.', True)

    def test_protocol_failure_never_becomes_execution_or_history(self):
        for invalid in ('', '<|tool_call>call:unknown{}<tool_call|>'):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as tmp:
                runtime = runtime_with_outputs(invalid, 'Hola.')
                agent = Agent(tmp, runtime)
                result = agent.chat('Hola')
                self.assertEqual(result['reply'], 'Hola.')
                self.assertEqual(result['tools'], [])
                self.assertEqual(result['diagnostics']['format_retries'], 1)
                self.assertFalse(any(m.get('content') == invalid for m in runtime.messages))
                with agent.store() as store:
                    self.assertEqual(store.db.execute("SELECT text FROM conversation WHERE role='assistant'").fetchall()[0][0], 'Hola.')
                    self.assertEqual(store.db.execute('SELECT COUNT(*) FROM generation_events').fetchone()[0], 2)
                    self.assertEqual(store.db.execute('SELECT COUNT(*) FROM tool_events').fetchone()[0], 0)

    def test_pseudocode_is_not_executed_retry_generates_a_fresh_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = runtime_with_outputs('report_save(result_id="fabricado")',
                                           'history_recent{}<tool_call|>', 'Historial consultado.')
            agent = Agent(tmp, runtime)
            result = agent.chat('Consulta el historial.')
            self.assertEqual([t['tool'] for t in result['tools']], ['history.recent'])
            self.assertEqual(result['diagnostics']['format_retries'], 1)
            with agent.store() as store:
                self.assertEqual(store.db.execute('SELECT COUNT(*) FROM agent_reports').fetchone()[0], 0)

    def test_persistent_protocol_failure_is_explicit_and_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, runtime_with_outputs('history_recent()', 'history_recent()'))
            with self.assertRaisesRegex(InvalidDecision, 'tras un reintento'):
                agent.chat('¿Quién soy?')
            self.assertEqual(agent.state, 'idle')
            with agent.store() as store:
                self.assertEqual(store.db.execute("SELECT COUNT(*) FROM conversation WHERE role='assistant'").fetchone()[0], 0)

    def test_forced_repair_cannot_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = runtime_with_outputs('report_save(result_id="x")',
                'report_save{result_id:<|"|>x<|"|>}<tool_call|>')
            runtime.names['report_save'] = 'report.save'
            agent = Agent(tmp, runtime)
            with self.assertRaisesRegex(InvalidDecision, 'sin escritura'):
                agent.chat('Dame ideas.')
            with agent.store() as store:
                self.assertEqual(store.db.execute('SELECT COUNT(*) FROM tool_events').fetchone()[0], 0)

    def test_truncated_repair_never_executes_even_a_complete_looking_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = runtime_with_outputs()
            events = iter([(['0','1','1','0','eos'], 'history_recent()'),
                           (['0','1','1','0','max_tokens'], 'history_recent{}<tool_call|>'),
                           (['0','1','0','0','context_full'], '')])
            runtime.event = lambda: next(events)
            agent = Agent(tmp, runtime)
            result = agent.chat('Consulta el historial.')
            self.assertTrue(result['incomplete'])
            self.assertNotIn('history_recent', result['reply'])
            with agent.store() as store:
                self.assertEqual(store.db.execute('SELECT COUNT(*) FROM tool_events').fetchone()[0], 0)

    def test_code_explanation_is_allowed(self):
        self.assertEqual(validate_reply('history_recent() consulta el historial.'),
                         'history_recent() consulta el historial.')

    def test_six_native_calls_leave_room_for_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = '<|tool_call>call:history_recent{}<tool_call|>' * 6
            agent = Agent(tmp, runtime_with_outputs(calls, 'Consultas terminadas.'))
            result = agent.chat('Consulta seis veces el historial.')
            self.assertEqual(len(result['tools']), 6)
            self.assertEqual(result['reply'], 'Consultas terminadas.')

    def test_seventh_call_is_not_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = '<|tool_call>call:history_recent{}<tool_call|>'
            agent = Agent(tmp, runtime_with_outputs(calls * 6, calls))
            with self.assertRaisesRegex(RuntimeError, 'no se ejecutó'):
                agent.chat('Consulta siete veces el historial.')
            with agent.store() as store:
                self.assertEqual(store.db.execute('SELECT COUNT(*) FROM tool_events').fetchone()[0], 6)

    def test_context_preserves_roles_and_attributes_user_evidence(self):
        rows = [dict(id='u1',role='user',text='Soy Marta.'),
                dict(id='a1',role='assistant',text='No sé tu nombre.'),
                dict(id='u2',role='user',text='Corrijo: soy Elena.'),
                dict(id='a2',role='assistant',text='history_recent()')]
        messages = native_messages(rows, 'PERFIL: vacío', '¿Cómo me llamo?')
        # Los turnos van primero y el bloque volátil al final, delante de la petición.
        self.assertEqual([m['role'] for m in messages], ['user','assistant','user','user','user'])
        self.assertEqual(messages[0]['content'], 'Soy Marta.')
        self.assertIn('Elena', referencias(messages))
        self.assertNotIn('No sé tu nombre', referencias(messages))
        self.assertFalse(any('history_recent()' in m['content'] for m in messages))
        self.assertTrue(messages[-1]['content'].startswith('¿Cómo me llamo?'))
        self.assertIn('Corrijo: soy Elena.', messages[-1]['content'])
        self.assertEqual(rows[-1]['text'], 'history_recent()')

    def test_retrieval_puts_latest_correction_last_without_losing_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(tmp, runtime_with_outputs('Recibido.', 'Corregido.'))
            agent.chat('Mi nombre es Marta.')
            agent.chat('Corrijo mi nombre: Elena.')
            agent.clear_context()
            with agent.store() as store:
                for name, args, key in [('history.recent', {}, 'messages'),
                                        ('history.search', {'query':'nombre'}, 'matches')]:
                    result = agent.tool(store, name, args)
                    users = [m['excerpt'] for m in result[key] if m['role']=='user']
                    self.assertEqual(users, ['Mi nombre es Marta.', 'Corrijo mi nombre: Elena.'])
                    self.assertEqual(result['order'], 'oldest_to_newest')

    def test_tool_history_belongs_to_its_original_turn(self):
        rows = [dict(id='u1',role='user',text='Resume pendientes.'),
                dict(id='a1',role='assistant',text='Resumen preparado.'),
                dict(id='u2',role='user',text='Hola.')]
        events = {'u1':[dict(tool='procedure.run',arguments={'id':'pending_report'},
                             result={'id':'r1','text':'Revisar copias'})]}
        messages = native_messages(rows, 'Perfil vacío', '¿Qué tal?', events)
        self.assertEqual(messages[1]['tool_calls'][0]['function']['name'], 'procedure_run')
        self.assertEqual(messages[1]['tool_responses'][0]['response']['id'], 'r1')
        self.assertEqual(messages[2]['content'], 'Resumen preparado.')
        self.assertNotIn('r1', messages[-1]['content'])

    def test_una_lectura_recortada_dice_como_completarse(self):
        # Con solo `truncated: True` el modelo remataba la lista con «y otros 12»
        # en vez de volver a leer: la vista parcial tiene que decir qué hacer.
        # Por encima del recorte: una lectura de red normal (3.209 caracteres) cabe entera.
        vecinos = [dict(ip='192.168.1.%d' % n, mac='aa:bb:cc:dd:ee:%02x' % n) for n in range(200)]
        rows = [dict(id='u1', role='user', text='Mira la red.'),
                dict(id='a1', role='assistant', text='Ahí van.'),
                dict(id='u2', role='user', text='Y sus macs.')]
        events = {'u1': [dict(tool='network.local', arguments={},
                              result=dict(unidentified_neighbors=vecinos))]}
        messages = native_messages(rows, 'Perfil vacío', 'Y sus macs.', events)
        respuesta = messages[1]['tool_responses'][0]['response']
        self.assertTrue(respuesta['truncated'])
        self.assertIn('network_local', respuesta['note'])
        self.assertIn('vuelve a llamar', respuesta['note'])
        # Un resultado que cabe entero no se toca ni se le añade nota.
        cortos = {'u1': [dict(tool='network.local', arguments={}, result=dict(ok=True))]}
        breve = native_messages(rows, 'Perfil vacío', 'Y sus macs.', cortos)
        self.assertEqual(breve[1]['tool_responses'][0]['response'], dict(ok=True))

    def test_anunciar_una_lista_sin_escribirla_no_es_una_respuesta(self):
        # «Te muestro las 16 direcciones IP y MACs» y ahí acababa el turno.
        with self.assertRaises(InvalidDecision) as caught:
            validate_reply('Te muestro las 16 direcciones IP y MACs de los vecinos '
                           'que no están registradas en la red.')
        self.assertIn('Escríbela entera', caught.exception.repair)

    def test_una_lista_entregada_pasa_esté_en_viñetas_o_en_línea(self):
        for respuesta in [
                'Aquí tienes los 15 vecinos:\n* 192.168.1.187\n* 192.168.1.45',
                'Estos son los 3 contenedores en marcha: minecraft-java, projectzomboid y n8n.',
                '| IP | MAC |\n| :-- | :-- |\n| 192.168.1.1 | f8:98:ef:93:cc:11 |',
                # Prosa legítima que empieza igual: no se rechaza por decir «aquí tienes».
                'Aquí tienes el diagnóstico: el disco sda tiene el enlace limitado a 1.5 Gbps.',
                'He revisado el NAS y no hay nada nuevo.']:
            self.assertEqual(validate_reply(respuesta), respuesta)

    def test_el_reintento_dice_qué_arreglar_y_no_habla_de_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = runtime_with_outputs('Te muestro las 16 direcciones IP y MACs.',
                                           'Aquí van:\n* 192.168.1.187\n* 192.168.1.45')
            agent = Agent(tmp, runtime)
            resultado = agent.chat('muéstrame las no registradas')
            self.assertEqual(resultado['diagnostics']['format_retries'], 1)
            self.assertIn('192.168.1.45', resultado['reply'])
            self.assertIn('Escríbela entera', ' '.join(
                m['content'] for m in runtime.messages if isinstance(m.get('content'), str)))
            # Reanudar en el canal de llamada haría que la lista se parsease como
            # una llamada y el turno muriese con «valor inválido».
            self.assertFalse(runtime.repair_call)

    def test_native_chat_does_not_reinject_old_task_as_current_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = runtime_with_outputs('Hola.')
            agent = Agent(tmp, runtime)
            with agent.store() as store:
                store.db.execute("INSERT INTO agent_state VALUES ('active',?)", ('{"result_id":"OLD_RESULT"}',))
                store.db.commit()
            agent.chat('Hola.')
            self.assertIn('OLD_RESULT', referencias(runtime.messages))
            # Lo que importa: la petición actual es el ÚLTIMO mensaje y es solo eso.
            self.assertEqual(runtime.messages[-1]['content'], 'Hola.')
            with agent.store() as store:
                self.assertEqual(agent.tool(store, 'task.current', {})['result_id'], 'OLD_RESULT')

    def test_current_result_can_be_read_without_id_or_recalculation(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = runtime_with_outputs('Listo.')
            agent = Agent(tmp, runtime)
            agent.chat('Resume pendientes.')
            with agent.store() as store:
                uid = store.db.execute("SELECT id FROM conversation WHERE role='user'").fetchone()[0]
                result = agent.tool(store, 'procedure.run', {'id':'pending_report'}, turn_id=uid)
                before = store.db.total_changes
                self.assertEqual(agent.tool(store, 'result.get', {}), result)
                self.assertEqual(before, store.db.total_changes)

    def test_reset_clears_turns_but_retrieves_only_user_citations(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = runtime_with_outputs('Soy Marta.', 'Hola.')
            agent = Agent(tmp, runtime)
            agent.chat('Soy Elena.')
            agent.clear_context()
            agent.chat('Hola.')
            # system(POLICY) · user(referencias) · user(petición) · assistant:
            # el bloque de datos ya no se funde con la política, va aparte y al final.
            self.assertEqual([m['role'] for m in runtime.messages],
                             ['system','user','user','assistant'])
            self.assertEqual(runtime.messages[2]['content'], 'Hola.')
            self.assertIn('Soy Elena.', referencias(runtime.messages))
            self.assertNotIn('Soy Marta.', referencias(runtime.messages))

    def test_context_resource_reads_are_explicit_and_do_not_recalculate(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = runtime_with_outputs('Listo.', 'Recuperado.')
            agent = Agent(tmp, runtime)
            agent.chat('Resume pendientes.')
            with agent.store() as store:
                uid = store.db.execute("SELECT id FROM conversation WHERE role='user'").fetchone()[0]
                resource = agent.tool(store, 'procedure.run', {'id':'pending_report'}, turn_id=uid)
            agent.clear_context()
            result = agent.chat('Recupera el resultado.')
            self.assertEqual(result['tools'], [])
            self.assertEqual(result['context_sources'][0]['id'], resource['id'])
            self.assertEqual(result['context_sources'][0]['text'], resource['text'])
            with agent.store() as store:
                self.assertEqual(store.db.execute('SELECT COUNT(*) FROM agent_results').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
