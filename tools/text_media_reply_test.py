"""Regresiones de Text, sin NAS, GPU, trabajador ni workspace real."""
import tempfile
import unittest
from unittest.mock import patch

from hexos.agent.chat import Agent
from hexos.agent.chat_backend.completion import ReplyPolicy
from hexos.agent.native import POLICY


class Runtime:
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.inputs = []
        self.calls = []

    def generate(self, messages):
        self.inputs.append(repr(messages))
        output = next(self.replies)
        return output if isinstance(output, dict) else dict(reply=output, work=None)

    def call(self, request):
        self.calls.append(request)


class TextMediaReplyTest(unittest.TestCase):
    def test_distinct_read_errors_allow_recovery_without_phrase_matching(self):
        with tempfile.TemporaryDirectory() as workspace:
            call=dict(tool='media.prepare', arguments=dict(scan_id='scan',profile_id='profile',count=5))
            runtime=Runtime(call, 'No puedo continuar.', call, 'No puedo continuar.', call, 'Plan preparado.')
            with patch('hexos.agent.chat_backend.media_tools.dispatch', side_effect=[
                dict(error='Faltan filtros'), dict(error='Falta root'), dict(plan_id='plan',count=5)]):
                result=Agent(workspace,runtime).chat('Prepara cinco películas sin iniciar.')
            self.assertEqual(result['diagnostics']['recovery_requests'],2)
            self.assertEqual(len(result['tools']),3)
            self.assertEqual(result['reply'],'Plan preparado.')

    def test_same_error_is_not_retried_forever(self):
        with tempfile.TemporaryDirectory() as workspace:
            call=dict(tool='media.prepare',arguments=dict(scan_id='scan',profile_id='profile'))
            runtime=Runtime(call,'Bloqueado.',call,'Bloqueado.')
            with patch('hexos.agent.chat_backend.media_tools.dispatch',return_value=dict(error='Falta root')):
                result=Agent(workspace,runtime).chat('Prepara la película sin iniciar.')
            self.assertEqual(result['diagnostics']['recovery_requests'],1)
            self.assertEqual(len(result['tools']),2)

    def test_recovery_stops_after_three_distinct_errors(self):
        with tempfile.TemporaryDirectory() as workspace:
            call=dict(tool='media.prepare',arguments=dict(scan_id='scan',profile_id='profile'))
            runtime=Runtime(*[item for _ in range(4) for item in (call,'Bloqueado.')])
            with patch('hexos.agent.chat_backend.media_tools.dispatch',side_effect=[
                dict(error='error '+str(i)) for i in range(4)]):
                result=Agent(workspace,runtime).chat('Prepara la película sin iniciar.')
            self.assertEqual(result['diagnostics']['recovery_requests'],3)
            self.assertEqual(len(result['tools']),4)

    def test_null_error_does_not_reject_correct_progress_reply(self):
        with tempfile.TemporaryDirectory() as workspace:
            runtime = Runtime(dict(tool='media.job', arguments=dict(id='job')),
                              'La compresión lleva 46.58 %.')
            with patch('hexos.agent.chat_backend.media_tools.dispatch', return_value=dict(error=None, state='running')):
                result = Agent(workspace, runtime).chat('¿Cómo va la compresión?')
            self.assertFalse(result['tools'][0]['failed'])
            self.assertEqual(len(runtime.inputs), 2)
            self.assertEqual(result['diagnostics']['recovery_requests'], 0)

    def test_consulted_jobs_does_not_announce_network_scan(self):
        self.assertIsNone(ReplyPolicy.announced_without_call('He consultado el estado de los trabajos.', []))
        self.assertEqual(ReplyPolicy.announced_without_call('He consultado la red local.', [])[1], 'network.local')

    claim = ('Pongo en cola la conversión de La Monja con el perfil jellyfin-rf19. '
             'Te avisaré cuando el proceso esté en marcha.')

    def test_free_text_does_not_execute_or_rewrite_a_claim(self):
        with tempfile.TemporaryDirectory() as workspace:
            runtime = Runtime(self.claim, self.claim)
            agent = Agent(workspace, runtime)
            result = agent.chat('Sí, inicia la conversión.')
            self.assertEqual(result['tools'], [])
            self.assertEqual(len(runtime.inputs), 1)
            self.assertEqual(result['reply'], self.claim)
            with agent.store() as store:
                saved = store.db.execute("SELECT text FROM conversation WHERE role='assistant'").fetchone()[0]
            self.assertEqual(saved, result['reply'])

    def test_metaphors_quotes_and_hypotheses_are_not_tool_calls(self):
        for reply in (
            'Con lo que tenemos, vamos a sacar el máximo provecho.',
            'Si tuviera esas capacidades, podría decirte: «He ajustado la prioridad».',
            'Por ejemplo: «Pongo en cola la conversión. Te avisaré cuando termine».',
            'He consultado el estado de los trabajos.',
        ):
            with self.subTest(reply=reply), tempfile.TemporaryDirectory() as workspace:
                runtime = Runtime(reply)
                result = Agent(workspace, runtime).chat('¿Qué propondrías como mejora?')
                self.assertEqual(result['reply'], reply)
                self.assertEqual(result['tools'], [])
                self.assertEqual(len(runtime.inputs), 1)

    def test_verified_start_and_idempotent_start_keep_claim_but_not_notification(self):
        for status in ('queued', 'already_queued'):
            trace = [dict(tool='media.start', failed=False,
                          result=dict(status=status, batch_id='observed'))]
            corrected = ReplyPolicy.media_reply_correction(self.claim, trace)
            self.assertIn('Pongo en cola', corrected)
            self.assertNotIn('Te avisaré', corrected)

    def test_prepare_failed_start_and_unrelated_write_are_not_start_evidence(self):
        for step in (
            dict(tool='media.prepare', result=dict(plan_id='plan')),
            dict(tool='media.start', failed=True, result=dict(status='queued', batch_id='x')),
            dict(tool='media.start', result=dict(error='no heartbeat')),
            dict(tool='media.start', result={}),
            dict(tool='note.save', result=dict(saved='note')),
        ):
            with self.subTest(step=step):
                self.assertIn('No consta', ReplyPolicy.media_reply_correction(self.claim, [step]))

    def test_negative_questions_history_and_observed_progress_unchanged(self):
        for reply in (
            'No he puesto en cola la conversión.',
            '¿Pongo en cola la conversión?',
            'Ayer puse en cola la conversión.',
            'La conversión lleva 2.64 % y quedan 59 minutos.',
            'El lote está preparado, sin iniciar.',
            'Pongo en cola la descarga del informe.',
        ):
            self.assertEqual(ReplyPolicy.media_reply_correction(reply, []), reply)

    def test_greeting_repair_does_not_order_execution_of_invented_task(self):
        with tempfile.TemporaryDirectory() as workspace:
            runtime = Runtime('El lote está preparado. ¿Quieres iniciarlo?',
                              'Hola. Voy a buscar las películas ahora.', 'Hola, socio.')
            agent = Agent(workspace, runtime)
            agent.chat('Prepara el lote sin iniciar.')
            result = agent.chat('hola helios')
            self.assertEqual(result['reply'], 'Hola. Voy a buscar las películas ahora.')
            self.assertEqual(result['tools'], [])
            self.assertEqual(len(runtime.inputs), 2)
            self.assertNotIn('Ejecútalo AHORA', runtime.inputs[-1])
            self.assertIn('aunque queden pendientes', POLICY)

    def test_acceptance_can_still_execute_start_once_with_observed_plan(self):
        with tempfile.TemporaryDirectory() as workspace:
            runtime = Runtime(
                dict(tool='media.prepare', arguments=dict(scan_id='scan', profile_id='profile', count=1)),
                'El lote está preparado. ¿Quieres iniciarlo?',
                dict(tool='media.start', arguments=dict(plan_id='observed-plan')),
                'He puesto en cola la conversión de La Monja.')
            agent = Agent(workspace, runtime)
            with patch('hexos.agent.chat_backend.media_tools.dispatch', side_effect=[
                dict(plan_id='observed-plan', count=1),
                dict(batch_id='observed-batch', status='queued'),
            ]) as dispatch:
                agent.chat('Prepara La Monja sin iniciar.')
                result = agent.chat('sí')
            self.assertEqual([s['tool'] for s in result['tools']], ['media.start'])
            self.assertFalse(result['tools'][0]['failed'])
            self.assertEqual(dispatch.call_count, 2)
            self.assertEqual(result['reply'], 'He puesto en cola la conversión de La Monja.')


if __name__ == '__main__':
    unittest.main()
