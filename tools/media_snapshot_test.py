import copy
import unittest
from unittest.mock import patch
from hexos.agent.chat_backend.media_tools import job_snapshot
from hexos.agent.media_jobs.contracts import UncertainEffect


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.job = dict(id='job', mode='live', state='running', run_id='run',
                        source=dict(device='nas'), config_digest='digest', error=None,
                        observation=dict(percent=46, observed_at=1))
        self.config = dict(device='nas', container='HandBrake', digest='digest', preset_version={})

    def test_live_observation_does_not_mutate_durable_job(self):
        before = copy.deepcopy(self.job)
        with patch('hexos.agent.chat_backend.media_tools.NasHandBrake.observe',
                   return_value=dict(run_id='run', status='running', percent=52, observed_at=2)):
            result = job_snapshot('/unused', self.config, self.job)
        self.assertEqual(result['observation']['percent'], 52)
        self.assertEqual(result['observation_source'], 'live')
        self.assertNotIn('error', result)
        self.assertEqual(self.job, before)

    def test_unreachable_retains_explicitly_dated_stored_observation(self):
        with patch('hexos.agent.chat_backend.media_tools.NasHandBrake.observe', side_effect=UncertainEffect('offline')):
            result = job_snapshot('/unused', self.config, self.job)
        self.assertEqual(result['observation_source'], 'stored')
        self.assertEqual(result['observation_warning'], 'offline')
        self.assertGreater(result['observation_age_seconds'], 0)

    def test_task_error_is_not_query_failure(self):
        self.job.update(state='blocked', error='encoder unavailable')
        result = job_snapshot('/unused', self.config, self.job)
        self.assertNotIn('error', result)
        self.assertEqual(result['task_error'], 'encoder unavailable')

    def test_changed_config_and_wrong_run_do_not_supply_fresh_progress(self):
        with patch('hexos.agent.chat_backend.media_tools.NasHandBrake.observe') as observe:
            result = job_snapshot('/unused', dict(self.config, digest='other'), self.job)
            observe.assert_not_called()
            self.assertEqual(result['observation_source'], 'stored')
        with patch('hexos.agent.chat_backend.media_tools.NasHandBrake.observe', return_value=dict(run_id='other')):
            result = job_snapshot('/unused', self.config, self.job)
            self.assertEqual(result['observation_source'], 'stored')
