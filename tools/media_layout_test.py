"""Nombres legibles, compatibilidad y transición de parcial a verificado."""
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hexos.agent.media_jobs.remote.file_layout import layout
from hexos.agent.media_jobs.remote import encoder_worker
from hexos.agent.media_jobs.nas_encoder import NasHandBrake
from tools import media_files_test
from tools.media_jobs_test import profile


class LayoutTest(unittest.TestCase):
    def job(self):
        return dict(id='a'*32,attempt=0,layout_version=2,source=dict(path='/films/Película á.mkv',
                    device='nas',destination='/films/Película á.optimizada.mkv'))

    def test_unicode_names_bounded_and_attempts_distinct(self):
        job=self.job();job['source']['path']='/films/'+('🎬á'*80)+'.mkv'
        first=layout(job,'b'*64)
        for path in first.values():
            self.assertTrue(all(len(p.encode())<=255 for p in Path(path).parts))
        job['attempt']=1
        self.assertNotEqual(first['output'],layout(job,'c'*64)['output'])
        job['id']='c'*32
        self.assertNotEqual(first['input'],layout(job,'c'*64)['input'])

    def test_legacy_paths_are_unchanged(self):
        job=self.job();job.pop('layout_version')
        self.assertEqual(layout(job,'b'*64)['input'],'a'*32+'/source.mkv')
        self.assertEqual(layout(job,'b'*64)['output'],'b'*64+'/encoded.mkv')

    def test_encoder_and_host_agree_on_output(self):
        job=self.job();job.update(profile=profile(),staging=dict(container_path='/storage/movie.mkv'))
        from unittest.mock import Mock
        transport=Mock(device='nas');encoder=NasHandBrake(transport,{})
        encoder.start(job,job['id']+':0:ready')
        request=transport.call.call_args.args[0]['request']
        self.assertEqual(request['output'],'/output/.hexos-media/'+layout(job,encoder.identity(job))['output'])
        self.assertEqual(request['display']['source'],job['source']['path'])

    def test_verified_output_renamed_and_published_original_intact(self):
        fixture=media_files_test.FilesTest();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.job['layout_version']=2
        partial=fixture.encoded()
        names=layout(fixture.job,fixture.request['run_id'])
        verified=Path(fixture.config['output'])/'.hexos-media'/names['verified']
        self.assertFalse(partial.exists());self.assertEqual(verified.read_bytes(),b'encoded movie')
        self.assertIn('Película á',fixture.job['staging']['path'])
        self.assertFalse(Path(fixture.job['staging']['path']+'.part').exists())
        self.assertEqual(json.loads((verified.parent/'estado.json').read_text())['status'],'verified')
        from hexos.agent.media_jobs.remote.file_operations import publish
        result=publish(fixture.request,fixture.root,lambda *args:None)
        self.assertTrue(result['original_preserved'])
        self.assertEqual(fixture.source.read_bytes(),b'original content')
        self.assertEqual(json.loads((verified.parent/'estado.json').read_text())['status'],'published')

    def test_failed_verification_keeps_partial_name(self):
        fixture=media_files_test.FilesTest();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.job['layout_version']=2;fixture.staged()
        from hexos.agent.media_jobs.remote import file_operations as ops
        partial=ops.paths(fixture.request)[3];partial.parent.mkdir(parents=True)
        partial.write_bytes(b'encoded movie')
        fixture.job['completion']=dict(exit_code=0,run_id=fixture.request['run_id'],output_bytes=partial.stat().st_size)
        with patch.object(ops,'probe',return_value=media_files_test.probe()),patch.object(ops,'decode',side_effect=ValueError('bad decode')):
            with self.assertRaises(ValueError):ops.verify(fixture.request,fixture.root,lambda *args:None)
        verified=Path(fixture.config['output'])/'.hexos-media'/layout(fixture.job,fixture.request['run_id'])['verified']
        self.assertTrue(partial.exists());self.assertFalse(verified.exists())

    def test_encoder_keeps_partial_name_and_writes_readable_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'run';run.mkdir()
            executable=root/'HandBrakeCLI'
            executable.write_text('#!/usr/bin/env python3\nimport sys,pathlib\n'
                'pathlib.Path(sys.argv[sys.argv.index("--output")+1]).write_bytes(b"encoded")\n'
                'print("test encoder log")\n')
            executable.chmod(0o700)
            target=root/'Película--id'/'Película.parcial.mkv'
            request=dict(run_id='b'*64,input='/unused',output=str(target),preset_export={},preset_name='test',
                         display=dict(job_id='a'*32,source='/films/Película.mkv',destination='/films/Película.optimizada.mkv'))
            request_path=run/'request.json';request_path.write_text(json.dumps(request))
            subprocess.run([sys.executable,encoder_worker.__file__,str(request_path)],
                           env=dict(os.environ,PATH=str(root)+os.pathsep+os.environ['PATH']),
                           check=True,timeout=10)
            self.assertTrue(target.exists())
            self.assertIn('test encoder log',(target.parent/'handbrake.log').read_text())
            state=json.loads((target.parent/'estado.json').read_text())
            self.assertEqual(state['status'],'finished')
            self.assertEqual(state['source'],'/films/Película.mkv')
            self.assertEqual(state['exit_code'],0)


if __name__=='__main__':unittest.main()
