"""Entrada de chat basada en catálogo, servicio real disponible e idempotencia."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from hexos.agent.chat_backend.media_tools import dispatch
from hexos.agent.media_jobs.configuration import load
from hexos.agent.media_jobs.planning import ensure
from hexos.agent.media_jobs.store import JobStore
from hexos.agent.file_catalog.sqlite_repository import publish_snapshot
from tools.media_jobs_test import profile


class ChatMediaTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.workspace=Path(self.temp.name)
        self.config=dict(enabled=True,device='nas',profiles=[profile()],preset_version=dict(VersionMajor=59,VersionMinor=0,VersionMicro=0),
                         files=dict(libraries=['/films'],storage='/storage',output='/output',control='/config',ffmpeg='/bin/ffmpeg',ffprobe='/bin/ffprobe'))
        (self.workspace/'media_jobs.json').write_text(json.dumps(self.config))
        items=[dict(path='/films/Sub '+str(i)+'/Film.mkv',root='/films',name='Film.mkv',size_bytes=i*100,
                    mtime_ns=1,inode=i,filesystem_id='1',media_kind='video') for i in range(1,9)]
        self.scan=publish_snapshot(self.workspace,dict(device='nas',observed_at='now',complete=True,items=items),['/films'])['scan_id']

    def heartbeat(self):
        store=JobStore(self.workspace);ensure(store.db)
        config=load(self.workspace)
        store.db.execute('INSERT INTO media_service VALUES (?,?,?)',(config['resource'],time.time(),json.dumps(dict(ready=True,config_digest=config['digest']))))
        store.close()

    def prepare(self,**kwargs):
        return dispatch(self.workspace,'media.prepare',dict(scan_id=self.scan,profile_id='fixture-rf19',**kwargs))

    def test_five_largest_from_full_catalog_then_one_idempotent_batch(self):
        plan=self.prepare(count=5)
        self.assertEqual([x['size_bytes'] for x in plan['files']],[800,700,600,500,400])
        self.assertTrue(all('/Sub ' in x['destination'] for x in plan['files']))
        with self.assertRaises(ValueError):dispatch(self.workspace,'media.start',dict(plan_id=plan['plan_id']))
        self.heartbeat()
        first=dispatch(self.workspace,'media.start',dict(plan_id=plan['plan_id']))
        second=dispatch(self.workspace,'media.start',dict(plan_id=plan['plan_id']))
        self.assertEqual(first['batch_id'],second['batch_id'])
        self.assertEqual(first['status'],'queued')
        store=JobStore(self.workspace)
        self.assertTrue(all(j['require_review'] for j in store.batch(first['batch_id'])['jobs']))
        store.close()

    def test_range_is_applied_before_top_five(self):
        plan=self.prepare(count=5,min_bytes=200,max_bytes=600,extensions=['.MKV'])
        self.assertEqual([x['size_bytes'] for x in plan['files']],[600,500,400,300,200])
        with self.assertRaises(ValueError):self.prepare(count=5,min_bytes=600,max_bytes=200)
        with self.assertRaises(ValueError):self.prepare(count=5,min_bytes=True)
        with self.assertRaises(ValueError):self.prepare(count=5,extensions=['mp4'])
        with self.assertRaises(ValueError):self.prepare(paths=['/films/Sub 3/Film.mkv'],max_bytes=600)

    def test_prepare_does_not_silently_drop_delivered_search_filters(self):
        import sqlite3
        db=sqlite3.connect(self.workspace/'work.sqlite')
        db.execute('CREATE TABLE tool_events(seq INTEGER PRIMARY KEY, body TEXT)')
        db.execute('INSERT INTO tool_events(body) VALUES (?)',(json.dumps(dict(
            tool='nas.find',failed=False,result=dict(scan_id=self.scan,
            filters=dict(min_bytes=200,max_bytes=600,extensions=['mkv'])))),))
        db.commit();db.close()
        with self.assertRaisesRegex(ValueError, '"min_bytes": 200'):
            self.prepare(count=5)
        plan=self.prepare(count=5,min_bytes=200,max_bytes=600,extensions=['mkv'],query='')
        self.assertEqual([f['size_bytes'] for f in plan['files']],[600,500,400,300,200])

    def test_missing_root_names_the_covered_library_without_expanding_scope(self):
        self.config['files']['libraries'].append('/other-library')
        (self.workspace/'media_jobs.json').write_text(json.dumps(self.config))
        with self.assertRaisesRegex(ValueError, 'root.*\\["/films"\\]'):
            self.prepare(count=3)
        self.assertEqual(self.prepare(count=3,root='/films')['count'],3)

    def test_context_exposes_configured_libraries_without_preset_or_permission(self):
        from hexos.agent.chat_backend.media_tools import context_reference
        reference=context_reference(self.workspace)
        self.assertIn('/films',reference)
        self.assertIn('media_options',reference)
        self.assertIn('no un escaneo ni una orden',reference)
        self.assertNotIn('AudioList',reference)
        self.assertNotIn('fixture-rf19',reference)
        (self.workspace/'media_jobs.json').unlink()
        self.assertEqual(context_reference(self.workspace),'')

    def test_search_range_then_prepare_and_enqueue_five(self):
        from hexos.agent.file_catalog.service import FileCatalog
        from hexos.agent.file_catalog.sqlite_repository import SQLiteCatalog
        page=FileCatalog(None,SQLiteCatalog(self.workspace)).search(
            scan_id=self.scan,min_bytes=200,max_bytes=600,extensions=['mkv'],limit=2)
        self.assertEqual(page['total_matches'],5)
        self.assertIsNotNone(page['next_offset'])
        plan=self.prepare(count=5,min_bytes=page['filters']['min_bytes'],
                          max_bytes=page['filters']['max_bytes'],extensions=page['filters']['extensions'])
        self.heartbeat()
        batch=dispatch(self.workspace,'media.start',dict(plan_id=plan['plan_id']))
        store=JobStore(self.workspace)
        try:jobs=store.batch(batch['batch_id'])['jobs']
        finally:store.close()
        self.assertEqual([j['source']['identity']['size_bytes'] for j in jobs],[600,500,400,300,200])
        self.assertTrue(all(j['state']=='queued' for j in jobs))

    def test_exact_paths_error_names_every_incompatible_field(self):
        for filters in (dict(count=1,extensions=['mkv'],min_bytes=0,max_bytes=800),
                        dict(extensions=['mkv'],min_bytes=0,max_bytes=800)):
            with self.assertRaises(ValueError) as caught:
                self.prepare(paths=['/films/Sub 3/Film.mkv'],**filters)
            for key in filters:
                self.assertIn(key,str(caught.exception))
            self.assertIn('solo scan_id, profile_id y paths',str(caught.exception))
        self.assertEqual(self.prepare(paths=['/films/Sub 3/Film.mkv'])['count'],1)

    def test_specific_observed_movie_only(self):
        plan=self.prepare(paths=['/films/Sub 3/Film.mkv'])
        self.assertEqual(plan['count'],1)
        self.assertEqual(plan['files'][0]['size_bytes'],300)
        with self.assertRaises(ValueError):self.prepare(paths=['/films/invented.mkv'])
        with self.assertRaises(ValueError):self.prepare(paths=['/films/Sub 3/Film.mkv'],count=1)

    def test_partial_scan_cannot_claim_global_top(self):
        db=__import__('sqlite3').connect(self.workspace/'nas_files.sqlite')
        db.execute('UPDATE scans SET coverage=?',(json.dumps(dict(complete=False)),));db.commit();db.close()
        with self.assertRaises(ValueError):self.prepare(count=5)
        self.assertEqual(self.prepare(paths=['/films/Sub 3/Film.mkv'])['count'],1)

    def test_changed_configuration_invalidates_plan(self):
        plan=self.prepare(count=1);self.heartbeat()
        self.config['files']['storage']='/different'
        (self.workspace/'media_jobs.json').write_text(json.dumps(self.config))
        with self.assertRaises(ValueError):dispatch(self.workspace,'media.start',dict(plan_id=plan['plan_id']))

    def test_no_config_does_not_enable_execution(self):
        (self.workspace/'media_jobs.json').unlink()
        self.assertFalse(dispatch(self.workspace,'media.options',{})['execution_enabled'])
        with self.assertRaises(ValueError):self.prepare(count=1)

    def test_cancel_queued_batch_does_not_require_model_review(self):
        plan=self.prepare(count=1);self.heartbeat()
        batch=dispatch(self.workspace,'media.start',dict(plan_id=plan['plan_id']))
        result=dispatch(self.workspace,'media.control',dict(batch_id=batch['batch_id'],operation='cancel'))
        self.assertEqual(result['jobs'][0]['state'],'cancelled')

    def test_agent_dispatch_exposes_preparation_and_launch(self):
        from hexos.agent.chat_backend.agent import Agent
        self.heartbeat();agent=Agent(self.workspace,None)
        with agent.store() as store:
            options=agent.tool(store,'media.options',{})
            self.assertTrue(options['execution_enabled'])
            plan=agent.tool(store,'media.prepare',dict(scan_id=self.scan,profile_id='fixture-rf19',count=1))
            result=agent.tool(store,'media.start',dict(plan_id=plan['plan_id']))
        self.assertEqual(result['status'],'queued')


if __name__=='__main__':unittest.main()
