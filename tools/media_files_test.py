"""Límites reales de archivos: cambio de origen, cancelación y publicación exclusiva."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hexos.agent.media_jobs.remote import file_operations as ops
from hexos.agent.media_jobs.remote import file_control
from hexos.agent.media_jobs.remote.file_common import (Cancelled, Rejected, copy_checked, inspect, save)
from hexos.agent.media_jobs.remote.file_media import validate_media
from hexos.agent.media_jobs.files import movie
from hexos.agent.media_jobs.nas_files_transport import bundle
from hexos.agent.file_catalog.sqlite_repository import publish_snapshot, database


def probe():
    return dict(format=dict(duration='15',format_name='matroska'),streams=[
        dict(codec_type='video',codec_name='h264',width=320,height=180),
        dict(codec_type='audio',codec_name='aac')])


def preset():
    return dict(AudioTrackSelectionBehavior='first',AudioList=[dict(AudioEncoder='fdk_aac')],
                SubtitleTrackSelectionBehavior='none')


class FilesTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        library=self.base/'biblioteca';library.mkdir()
        self.source=library/'Subcarpeta'/'Película á.mkv';self.source.parent.mkdir()
        self.source.write_bytes(b'original content')
        source=movie(dict(device='nas',kind='movie',path=str(self.source),library_root=str(library),identity=inspect(self.source)))
        self.job=dict(id='a'*32,attempt=0,source=source,profile=dict(preset=preset()))
        self.config=dict(libraries=[str(library)],storage=str(self.base/'storage'),output=str(self.base/'output'),control=str(self.base/'control'))
        self.request=dict(job=self.job,config=self.config,run_id='b'*64,operation='stage')
        self.root=self.base/'control'/'file-jobs'/self.job['id']/'actions'/('c'*64)
        self.root.mkdir(parents=True)

    def staged(self):
        with patch.object(ops,'probe',return_value=probe()):
            self.job['staging']=ops.stage(self.request,self.root,lambda *args:None)
        return self.job['staging']

    def encoded(self):
        self.staged()
        output=ops.paths(self.request)[3];output.parent.mkdir(parents=True)
        output.write_bytes(b'encoded movie')
        self.job['completion']=dict(exit_code=0,run_id=self.request['run_id'],output_bytes=output.stat().st_size)
        with patch.object(ops,'probe',return_value=probe()),patch.object(ops,'decode'):
            self.job['validation']=ops.verify(self.request,self.root,lambda *args:None)
        return output

    def test_copy_complete_preserves_original_and_subfolder_destination(self):
        # Biblioteca en otro volumen (p. ej. /volume4): se copia y se comprueba el hash.
        with patch.object(ops,'same_filesystem',return_value=False):
            receipt=self.staged()
        self.assertEqual(Path(receipt['path']).read_bytes(),self.source.read_bytes())
        self.assertEqual(receipt['sha256'],hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertIn('/'+self.job['id']+'/',receipt['container_path'])
        self.assertEqual(Path(self.job['source']['destination']).parent,self.source.parent)

    def test_changed_source_not_copied(self):
        self.source.write_bytes(b'changed')
        with self.assertRaises(Rejected): self.staged()

    def test_parent_symlink_cannot_escape_library(self):
        outside=self.base/'outside';self.source.parent.rename(outside)
        self.source.parent.symlink_to(outside,target_is_directory=True)
        with self.assertRaises(OSError): self.staged()

    def test_cancel_partial_copy_never_promotes_input(self):
        def cancel(*args): raise Cancelled()
        with self.assertRaises(Cancelled): ops.stage(self.request,self.root,cancel)
        self.assertFalse(ops.paths(self.request)[2].exists())
        self.assertEqual(self.source.read_bytes(),b'original content')

    def test_low_space_fails_before_copy(self):
        from types import SimpleNamespace
        with patch('os.fstatvfs',return_value=SimpleNamespace(f_bavail=0,f_frsize=4096)), \
                patch.object(ops,'same_filesystem',return_value=False):
            with self.assertRaises(OSError): self.staged()
        self.assertFalse(ops.paths(self.request)[2].exists())

    def test_publish_verified_copy_and_keep_original(self):
        output=self.encoded()
        receipt=ops.publish(self.request,self.root,lambda *args:None)
        self.assertEqual(Path(receipt['path']).read_bytes(),output.read_bytes())
        self.assertEqual(self.source.read_bytes(),b'original content')
        self.assertTrue(receipt['original_preserved'])

    def published(self):
        output=self.encoded()
        self.job['publication']=ops.publish(self.request,self.root,lambda *args:None)
        return output

    def test_stage_on_same_volume_links_instead_of_copying(self):
        staging=self.staged()
        staged=Path(staging['path'])
        self.assertEqual(staged.stat().st_ino,self.source.stat().st_ino)
        self.assertIsNone(staging['sha256'])
        self.assertEqual(self.source.read_bytes(),b'original content')

    def test_publish_on_same_volume_moves_without_leftover_part(self):
        output=self.published()
        destination=Path(self.job['publication']['path'])
        self.assertEqual(destination.stat().st_ino,output.stat().st_ino)
        self.assertEqual(list(destination.parent.glob('.hexos-*')),[])

    def test_cleanup_removes_temporaries_and_keeps_original_by_default(self):
        output=self.published()
        staged=Path(self.job['staging']['path'])
        receipt=ops.cleanup(self.request,self.root,lambda *args:None)
        self.assertTrue(receipt['cleaned'])
        self.assertFalse(receipt['original_removed'])
        self.assertFalse(staged.exists() or output.exists())
        self.assertEqual(self.source.read_bytes(),b'original content')
        self.assertEqual(Path(self.job['publication']['path']).read_bytes(),b'encoded movie')
        # Idempotente: una segunda pasada no falla ni borra nada más.
        self.assertEqual(ops.cleanup(self.request,self.root,lambda *args:None)['removed'],[])

    def test_cleanup_replaces_original_only_after_checking_published_file(self):
        self.published()
        self.config['replace_original']=True
        receipt=ops.cleanup(self.request,self.root,lambda *args:None)
        self.assertTrue(receipt['original_removed'])
        self.assertFalse(self.source.exists())
        self.assertEqual(Path(self.job['publication']['path']).read_bytes(),b'encoded movie')

    def test_cleanup_keeps_original_if_published_file_differs(self):
        self.published()
        self.config['replace_original']=True
        self.job['validation']=dict(self.job['validation'],sha256='0'*64)
        with self.assertRaises(Rejected):ops.cleanup(self.request,self.root,lambda *args:None)
        self.assertEqual(self.source.read_bytes(),b'original content')

    def test_cleanup_without_checked_publication_does_nothing(self):
        output=self.encoded()
        with self.assertRaises(Rejected):ops.cleanup(self.request,self.root,lambda *args:None)
        self.assertTrue(output.exists())

    def test_publish_between_filesystems(self):
        if not Path('/dev/shm').is_dir(): self.skipTest('Requiere segundo filesystem')
        with tempfile.TemporaryDirectory(dir='/dev/shm') as other:
            if os.stat(other).st_dev==os.stat(self.base).st_dev:self.skipTest('Mismo filesystem')
            self.config['output']=other
            output=self.encoded()
            receipt=ops.publish(self.request,self.root,lambda *args:None)
            self.assertEqual(Path(receipt['path']).read_bytes(),output.read_bytes())
            self.assertEqual(list(Path(receipt['path']).parent.glob('.hexos-*')),[])

    def test_original_changed_during_conversion_prevents_publication(self):
        self.encoded();self.source.write_bytes(b'original replaced')
        with self.assertRaises(Rejected):ops.publish(self.request,self.root,lambda *args:None)
        self.assertFalse(Path(self.job['source']['destination']).exists())

    def test_existing_destination_is_not_overwritten(self):
        self.encoded();destination=Path(self.job['source']['destination']);destination.write_bytes(b'existing')
        with self.assertRaises(FileExistsError):ops.publish(self.request,self.root,lambda *args:None)
        self.assertEqual(destination.read_bytes(),b'existing')

    def test_changed_output_after_validation_is_rejected(self):
        output=self.encoded();output.write_bytes(b'changed')
        with self.assertRaises(Rejected):ops.publish(self.request,self.root,lambda *args:None)
        self.assertFalse(Path(self.job['source']['destination']).exists())

    def test_forged_hash_prevents_publication(self):
        self.encoded();self.job['validation']['sha256']='0'*64
        with self.assertRaises(Rejected):ops.publish(self.request,self.root,lambda *args:None)
        self.assertFalse(Path(self.job['source']['destination']).exists())

    def test_reject_invalid_duration_codec_and_audio(self):
        for change in ('duration','codec','audio'):
            result=probe()
            if change=='duration':result['format']['duration']='5'
            if change=='codec':result['streams'][0]['codec_name']='hevc'
            if change=='audio':result['streams'].pop()
            with self.subTest(change=change),self.assertRaises(Rejected):validate_media(probe(),result,preset())
        self.assertEqual(validate_media(probe(),probe(),preset())['audio_tracks'],1)

    def test_spanish_subtitles_pass_and_others_are_rejected(self):
        wanted=dict(preset(),SubtitleTrackSelectionBehavior='all',SubtitleLanguageList=['spa'],
                    SubtitleAddForeignAudioSearch=True,SubtitleBurnBehavior='foreign',
                    SubtitleBurnBDSub=False,SubtitleBurnDVDSub=False)
        track=lambda lang:dict(codec_type='subtitle',codec_name='hdmv_pgs_subtitle',tags=dict(language=lang))
        source=probe();source['streams']+=[track('spa'),track('spa'),track('eng')]
        output=probe();output['streams']+=[track('spa'),track('spa')]
        self.assertEqual(validate_media(source,output,wanted)['subtitle_tracks'],2)
        self.assertEqual(validate_media(source,probe(),wanted)['subtitle_tracks'],0)
        english=probe();english['streams'].append(track('eng'))
        extra=probe();extra['streams']+=[track('spa')]*3
        for name,result in (('idioma',english),('de más',extra)):
            with self.subTest(name),self.assertRaises(Rejected):validate_media(source,result,wanted)
        with self.assertRaises(Rejected):validate_media(source,output,preset())

    def test_subtitle_profile_must_not_burn_full_tracks(self):
        base=dict(preset(),SubtitleTrackSelectionBehavior='all',SubtitleLanguageList=['spa'],
                  SubtitleBurnBehavior='foreign',SubtitleBurnBDSub=False,SubtitleBurnDVDSub=False)
        for change in (dict(SubtitleBurnBDSub=True),dict(SubtitleBurnBehavior='first'),
                       dict(SubtitleLanguageList=[]),dict(SubtitleLanguageList=['es'])):
            with self.subTest(change=change),self.assertRaises(Rejected):
                validate_media(probe(),probe(),dict(base,**change))

    def test_missing_decode_confirmation_blocks_publication(self):
        self.encoded();self.job['validation']['decoded']=False
        with self.assertRaises(Rejected):ops.publish(self.request,self.root,lambda *args:None)

    def test_output_without_savings_needs_explicit_test_override(self):
        output=self.encoded();output.write_bytes(b'x'*100)
        self.job['completion']['output_bytes']=100
        with patch.object(ops,'probe',return_value=probe()),patch.object(ops,'decode'):
            with self.assertRaises(Rejected):ops.verify(self.request,self.root,lambda *args:None)
            self.config['require_smaller']=False
            self.assertEqual(ops.verify(self.request,self.root,lambda *args:None)['size_goal'],'not_enforced')

    def test_lost_response_does_not_launch_second_worker(self):
        message=dict(request=self.request,operation='start',action_id='d'*64)
        with patch.object(file_control.subprocess,'Popen') as launch:
            file_control.control(message,'/tmp/runtime.zip')
            file_control.control(message,'/tmp/runtime.zip')
        self.assertEqual(launch.call_count,1)

    def test_cancel_before_start_prevents_worker(self):
        message=dict(request=self.request,operation='stop',action_id='d'*64)
        result=file_control.control(message,'/tmp/runtime.zip')
        self.assertTrue(result['result']['stopped'])
        message['operation']='start'
        with patch.object(file_control.subprocess,'Popen') as launch:
            self.assertEqual(file_control.control(message,'/tmp/runtime.zip')['status'],'cancelled')
        launch.assert_not_called()

    def test_dead_worker_blocks_instead_of_claiming_success(self):
        save(self.root/'state.json',dict(status='running'))
        self.assertEqual(file_control.snapshot(self.root)['status'],'blocked')

    def test_bundle_is_deterministic(self):
        self.assertEqual(bundle(),bundle())

    def test_catalog_replay_is_idempotent_and_partial(self):
        item=dict(path=str(self.source),root=self.job['source']['library_root'],name=self.source.name,
                  media_kind='video',**inspect(self.source))
        result=dict(items=[item],device='nas',observed_at='now',complete=False,stopped_reason='single_published_file')
        for _ in range(2):publish_snapshot(self.base/'catalog',result,[item['root']],scan_id='test-output')
        db=database(self.base/'catalog')
        self.assertEqual(db.execute('SELECT count(*) FROM scans').fetchone()[0],1)
        self.assertFalse(json.loads(db.execute('SELECT coverage FROM scans').fetchone()[0])['complete'])
        db.close()
        result['items'][0]['size_bytes']=999
        with self.assertRaises(ValueError):publish_snapshot(self.base/'catalog',result,[item['root']],scan_id='test-output')


if __name__=='__main__':unittest.main()
