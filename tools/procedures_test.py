"""Persistencia y fronteras del recorrido de informes, sin GPU."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent
from hexos.agent import procedures


class Runtime:
    def call(self, request):
        assert request == {'type': 'reset'}

    def generate(self, messages):
        return {'reply': 'ok', 'work': None}


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.agent = Agent(self.tmp.name, Runtime())
        with self.agent.store() as s:
            self.job = s.dispatch(dict(op='create', title='Revisar espacio NAS',
                request='Revisa espacio', source_ref='test:usuario'), actor='user')
            s.db.execute("INSERT INTO conversation VALUES ('u1','2026','user','Resume pendientes','Resume pendientes')")
            s.db.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def run_report(self, s):
        result = self.agent.tool(s, 'procedure.run', {'id':'pending_report'}, turn_id='u1')
        return self.agent.tool(s, 'report.save', {'result_id':result['id']}, turn_id='u1')

    def test_snapshot_and_idempotence(self):
        with self.agent.store() as s:
            before = s.get(self.job['id'])
            r = self.run_report(s)
            self.assertEqual(before, s.get(self.job['id']))
            self.assertEqual(r, self.run_report(s))
            self.assertEqual(r['items'][0]['revision'], 1)
            self.assertEqual(s.db.execute('SELECT COUNT(*) FROM agent_reports').fetchone()[0], 1)

    def test_recovery_after_reset_restart_and_changed_job(self):
        with self.agent.store() as s:
            r = self.run_report(s)
            s.dispatch(dict(op='update', id=self.job['id'], revision=1,
                            state='terminado', summary='Comprobado'), actor='user')
        self.agent.clear_context()
        restarted = Agent(self.tmp.name, Runtime())
        with restarted.store() as s:
            active = restarted.tool(s, 'task.current', {})
            self.assertEqual(active['report_id'], r['id'])
            self.assertEqual(restarted.tool(s, 'report.get', {'id':r['id']}), r)
            self.assertEqual(s.listing(state='pendiente'), [])

    def test_clear_excludes_old_turns_but_injects_task(self):
        with self.agent.store() as s:
            self.agent.tool(s, 'task.focus', dict(intent='Informe de trabajos',
                question='¿Qué estado?'), turn_id='u1')
        self.agent.clear_context()
        seen = []
        self.agent.runtime.generate = lambda messages: (seen.extend(messages) or {'reply':'ok','work':None})
        self.agent.chat('los pendientes')
        prompt = seen[1]['content']
        self.assertIn('awaiting_clarification', prompt)
        self.assertNotIn('user: Resume pendientes', prompt)
        self.assertIn('los pendientes', prompt)

    def test_no_forged_source_or_command(self):
        with self.agent.store() as s:
            for name,args in [('procedure.run', {'id':'ssh'}),
                              ('procedure.run', {'id':'pending_report','command':'ls'}),
                              ('procedure.run', {'id':'pending_report'})]:
                with self.assertRaises(ValueError):
                    self.agent.tool(s, name, args, turn_id='inventado')
            self.assertEqual(s.db.execute('SELECT COUNT(*) FROM agent_reports').fetchone()[0], 0)

    def test_report_not_capped_at_100(self):
        with self.agent.store() as s:
            for i in range(101):
                s.dispatch(dict(op='create', title=f'Tarea {i}', request='prueba',
                                source_ref='test'), actor='user')
            self.assertEqual(len(self.run_report(s)['items']), 102)

    def test_tool_loop_uses_real_store(self):
        outputs = iter([{'tool':'procedure.run','arguments':{'id':'pending_report'}},
                        {'reply':'Tienes pendiente revisar espacio NAS.','work':None}])
        self.agent.runtime.generate = lambda _: next(outputs)
        result = self.agent.chat('Resume los trabajos pendientes')
        self.assertEqual(result['tools'][0]['result']['items'][0]['id'], self.job['id'])
        with self.agent.store() as s:
            self.assertEqual(len(s.listing()), 1)

    def test_invalid_empty_work_retries_without_writing(self):
        outputs = iter([{'reply':'Procedo', 'work':{}},
                        {'tool':'procedure.run','arguments':{'id':'pending_report'}},
                        {'reply':'Informe guardado', 'work':None}])
        self.agent.runtime.generate = lambda _: next(outputs)
        result = self.agent.chat('Resume pendientes')
        self.assertEqual(len(result['tools']), 1)
        with self.agent.store() as s:
            self.assertEqual(len(s.listing()), 1)

    def test_bad_tool_arguments_recover_and_persist(self):
        outputs = iter([
            {'tool':'procedure.run','arguments':{'id':'pending_report','state':'pendiente'}},
            {'reply':'¿Quieres que reintente?', 'work':None},
            {'tool':'procedure.run','arguments':{'id':'pending_report'}},
            {'reply':'Pendiente revisar espacio NAS', 'work':None}])
        self.agent.runtime.generate = lambda _: next(outputs)
        result = self.agent.chat('Resume pendientes')
        self.assertEqual(len(result['tools']), 2)
        self.assertIn('sobran', result['tools'][0]['result']['error'])
        with self.agent.store() as s:
            self.assertEqual(s.db.execute('SELECT COUNT(*) FROM agent_reports').fetchone()[0], 0)
            self.assertEqual(s.db.execute('SELECT COUNT(*) FROM agent_results').fetchone()[0], 1)
            self.assertEqual(s.db.execute('SELECT COUNT(*) FROM tool_events').fetchone()[0], 2)
        restarted = Agent(self.tmp.name, Runtime())
        seen = []
        restarted.runtime.generate = lambda messages: (seen.extend(messages) or {'reply':'ok','work':None})
        restarted.chat('haz un resumen')
        self.assertIn('Revisar espacio NAS', seen[1]['content'])
        self.assertIn('ÚLTIMA OPERACIÓN REGISTRADA', seen[1]['content'])

    def test_summary_save_and_read_are_separate(self):
        with self.agent.store() as s:
            r = self.agent.tool(s, 'procedure.run', {'id':'pending_report'}, turn_id='u1')
            self.assertEqual(s.db.execute('SELECT COUNT(*) FROM agent_reports').fetchone()[0], 0)
            s.dispatch(dict(op='update',id=self.job['id'],revision=1,
                            state='terminado',summary='Hecho'),actor='user')
            saved = self.agent.tool(s, 'report.save', {'result_id':r['id']}, turn_id='u1')
            self.assertEqual(saved['items'], r['items'])
            self.assertEqual(saved['ts'], r['ts'])
            before = s.db.total_changes
            self.agent.tool(s, 'report.get', {'id':saved['id']})
            self.assertEqual(s.db.total_changes, before)

    def test_clarification_is_persistent_decision(self):
        self.agent.runtime.generate = lambda _: {'clarify':'¿Qué estado?', 'intent':'Resumen de trabajos'}
        self.agent.chat('Haz un informe')
        self.agent.clear_context()
        with self.agent.store() as s:
            current = self.agent.tool(s, 'task.current', {})
            self.assertEqual(current['intent'], 'Resumen de trabajos')
            self.assertEqual(current['status'], 'awaiting_clarification')

    def test_catalog_types_and_unknown_keys(self):
        from hexos.agent.catalog import validate, render
        self.assertIn('result_id', render())
        for name,args in [('report.save', {'id':'x'}), ('document.read',{'id':'x','count':True}),
                          ('procedure.run',{'id':'x','state':'pendiente'})]:
            with self.assertRaises(ValueError):
                validate(name,args)

    def test_invalid_json_is_retried_once(self):
        from hexos.agent.chat import InvalidDecision
        count = 0
        def generate(messages):
            nonlocal count
            count += 1
            if count == 1:
                raise InvalidDecision('sin JSON')
            return {'reply':'Hola', 'work':None}
        self.agent.runtime.generate = generate
        self.assertEqual(self.agent.chat('hola')['diagnostics']['format_retries'], 1)
        self.agent.runtime.generate = lambda _: (_ for _ in ()).throw(InvalidDecision('sin JSON'))
        with self.assertRaises(InvalidDecision):
            self.agent.chat('hola')


if __name__ == '__main__':
    unittest.main()
