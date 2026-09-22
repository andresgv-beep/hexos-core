"""Recibos durables del encoder sin NAS; los efectos se cuentan, no se suponen."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from hexos.agent.media_jobs.remote import encoder_control as control
from hexos.agent.media_jobs.remote.encoder_worker import progress_objects
from hexos.agent.media_jobs.nas_encoder import NasEncoderTransport
from hexos.agent.media_jobs.contracts import UncertainEffect, SharedFailure


class RemoteEncoderTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(control, 'ROOT', self.root)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.run_id = 'a'*64
        self.request = dict(run_id=self.run_id, input='/storage/.hexos-media/test/source.mkv',
                            output='/output/.hexos-media/test/output.mkv', preset_export={}, preset_name='test')
        self.message = dict(operation='start', run_id=self.run_id, request=self.request,
                            worker=base64.b64encode(b'# worker').decode())

    def test_lost_launch_response_does_not_duplicate_encoder(self):
        with patch.object(control.subprocess, 'Popen') as spawn:
            control.control(self.message)
            control.control(self.message)
        self.assertEqual(spawn.call_count, 1)

    def test_failure_between_launch_intent_and_spawn_requires_reconciliation(self):
        with patch.object(control.subprocess, 'Popen', side_effect=OSError('lost')) as spawn:
            with self.assertRaises(OSError): control.control(self.message)
            control.control(self.message)
        self.assertEqual(spawn.call_count, 1)
        with patch.object(control.time, 'time', return_value=10**12):
            state = control.control(dict(operation='observe', run_id=self.run_id))
        self.assertEqual(state['status'], 'unknown')

    def test_cancel_before_start_prevents_late_start(self):
        control.control(dict(operation='stop', run_id=self.run_id))
        with patch.object(control.subprocess, 'Popen') as spawn:
            result = control.control(self.message)
        spawn.assert_not_called()
        self.assertEqual(result['exit_code'], 130)

    def test_reused_key_cannot_change_input(self):
        with patch.object(control.subprocess, 'Popen'):
            control.control(self.message)
        self.request['input'] = '/storage/.hexos-media/other/source.mkv'
        with self.assertRaises(ValueError): control.control(self.message)

    def test_paths_outside_staging_rejected(self):
        for path in ('/storage/film.mkv', '/storage/.hexos-media/../../film.mkv'):
            self.request['input'] = path
            with self.assertRaises(ValueError): control.control(self.message)

    def test_dead_worker_does_not_report_running(self):
        root = self.root/'runs'/self.run_id
        root.mkdir(parents=True)
        (root/'state.json').write_text(json.dumps(dict(status='running', run_id=self.run_id)))
        self.assertEqual(control.snapshot(root, self.run_id)['status'], 'unknown')

    def test_repeated_stop_does_not_reset_deadline(self):
        root = self.root/'runs'/self.run_id
        root.mkdir(parents=True)
        (root/'launch.json').write_text(json.dumps(dict(at=time.time())))
        control.control(dict(operation='stop', run_id=self.run_id))
        os.utime(root/'cancel', (1, 1))
        with patch.object(control, 'snapshot', return_value=dict(status='running')):
            result = control.control(dict(operation='stop', run_id=self.run_id))
        self.assertEqual(result['status'], 'unknown')

    def test_json_progress_tolerates_logs_and_incomplete_next_packet(self):
        value = 'noise\nProgress: {"State":"WORKING","Working":{"Progress":0.5}}\nProgress: {"State":'
        self.assertEqual(list(progress_objects(value))[0]['Working']['Progress'], .5)
        self.assertEqual(len(list(progress_objects(value))), 1)

    def test_transport_accepts_only_complete_framed_reply(self):
        transport = NasEncoderTransport('/tmp/workspace', 'synology 1')
        result = dict(exit_code=0, output='SSH noise\n__HEXOS_MEDIA__{"status":"running"}\n', truncated=False)
        with patch('hexos.agent.media_jobs.nas_encoder.nas_session.execute_remote', return_value=result):
            self.assertEqual(transport.call({})['status'], 'running')
            result['truncated'] = True
            with self.assertRaises(UncertainEffect): transport.call({})

    def test_blocked_reply_is_shared_failure(self):
        result = dict(exit_code=0, output='__HEXOS_MEDIA__{"status":"blocked","error":"busy"}')
        with patch('hexos.agent.media_jobs.nas_encoder.nas_session.execute_remote', return_value=result):
            with self.assertRaises(SharedFailure): NasEncoderTransport('/tmp', 'nas').call({})

    def test_worker_reports_progress_and_cancels_its_process(self):
        from hexos.agent.media_jobs.remote import encoder_worker
        root = self.root/'run'
        root.mkdir()
        binary = self.root/'HandBrakeCLI'
        binary.write_text('#!'+sys.executable+'\n'+'''import pathlib,sys,time,json
pathlib.Path(sys.argv[sys.argv.index('--output')+1]).write_bytes(b'fake video')
print('Progress: '+json.dumps({'State':'WORKING','Working':{'Progress':0.25,'ETASeconds':12}}),flush=True)
time.sleep(20)
''')
        binary.chmod(0o700)
        request = dict(self.request, output=str(root/'encoded.mkv'))
        (root/'request.json').write_text(json.dumps(request))
        env = dict(os.environ, PATH=str(self.root)+os.pathsep+os.environ['PATH'])
        process = subprocess.Popen([sys.executable, encoder_worker.__file__, str(root/'request.json')], env=env)
        try:
            deadline = time.monotonic()+8
            while time.monotonic() < deadline:
                if (root/'state.json').exists():
                    state = json.loads((root/'state.json').read_text())
                    if state.get('percent') == 25:
                        break
                time.sleep(.05)
            else:
                self.fail('No se recibió progreso real del subproceso')
            self.assertEqual(state['eta_seconds'], 12)
            (root/'cancel').touch()
            process.wait(timeout=5)
            state = json.loads((root/'state.json').read_text())
            self.assertEqual(state['status'], 'finished')
            self.assertNotEqual(state['exit_code'], 0)
            self.assertTrue(state['cancelled'])
        finally:
            if process.poll() is None:
                (root/'cancel').touch()
                process.wait(timeout=15)


if __name__ == '__main__':
    unittest.main()
