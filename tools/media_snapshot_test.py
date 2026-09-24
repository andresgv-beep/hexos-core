import copy
import unittest
from unittest.mock import patch
from hexos.agent.chat_backend.media_tools import job_snapshot
from hexos.agent.media_jobs.contracts import UncertainEffect
from hexos.agent.media_jobs import presence
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile


class SnapshotTest(unittest.TestCase):
    def test_historical_validation_does_not_hide_missing_file(self):
        self.job.update(state='awaiting_review', completion={'exit_code':0}, validation={'valid':True})
        before = copy.deepcopy(self.job)
        with patch.object(presence, 'observe', return_value=dict(source='live_ssh_stat',
                files={'encoded': {'status':'missing'}})):
            result = job_snapshot('/unused', self.config, self.job)
        self.assertEqual(result['file_presence']['files']['encoded']['status'], 'missing')
        self.assertTrue(result['validation']['valid'])
        self.assertEqual(result['completion']['exit_code'], 0)
        self.assertEqual(self.job, before)

    def test_unreachable_presence_is_unknown_not_missing(self):
        self.job.update(state='awaiting_review', completion={'exit_code':0})
        with patch.object(presence, 'observe', side_effect=ValueError('offline')):
            result=job_snapshot('/unused',self.config,self.job)
        self.assertEqual(result['file_presence']['source'], 'unavailable')
        self.assertNotIn('files',result['file_presence'])

    def test_presence_rejects_changed_config_before_ssh(self):
        with patch.object(presence.nas_session, 'execute_remote') as remote:
            with self.assertRaises(ValueError):
                presence.observe('/unused', dict(self.config,digest='different'), self.job)
            remote.assert_not_called()

    def test_remote_probe_is_read_only_and_distinguishes_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); original=root/'original.mkv'; original.write_bytes(b'video')
            alias=root/'alias.mkv'; alias.symlink_to(original)
            paths=dict(source=str(original), encoded=str(root/'missing.mkv'), alias=str(alias))
            payload=base64.b64encode(json.dumps(paths).encode()).decode()
            out=subprocess.run([sys.executable,'-c',presence.REMOTE,payload],capture_output=True,text=True,check=True)
            result=json.loads(out.stdout.split('__HEXOS_PRESENCE__',1)[1])['files']
            self.assertEqual(result['source']['status'],'present')
            self.assertEqual(result['encoded']['status'],'missing')
            self.assertEqual(result['alias']['status'],'not_regular')
            self.assertEqual(original.read_bytes(),b'video')
            self.assertFalse((root/'missing.mkv').exists())

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
