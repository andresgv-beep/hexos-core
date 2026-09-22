"""Base de tareas sin NAS: recuperación, exclusión, publicación y simulación explícita."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hexos.agent.media_jobs.store import JobStore, Conflict
from hexos.agent.media_jobs.profiles import freeze
from hexos.agent.media_jobs.runner import Runner
from hexos.agent.media_jobs.simulation import Simulation
from hexos.agent.media_jobs.policy import check_delay, observe_progress
from hexos.agent.media_jobs.contracts import SharedFailure, UncertainEffect
from hexos.agent.media_jobs.handbrake import UnconfiguredHandBrake
from hexos.agent.chat_backend.media_tools import dispatch


def source(i=1):
    return dict(device='nas-fixture', path=f'/peliculas/Carpeta {i}/Película {i}.mkv',
                library_root='/peliculas', kind='movie',
                identity=dict(size_bytes=30000,mtime_ns=1,inode=i,filesystem_id='1'))


def profile():
    # Fixture mínimo; no es el preset real del usuario ni se exporta como tal.
    return freeze('fixture-rf19', dict(PresetName='fixture',VideoEncoder='x264',FileFormat='av_mkv',
                                     VideoQualitySlider=19,VideoPreset='fast',AudioList=[]))


class Clock:
    def __init__(self): self.now=1000
    def __call__(self): return self.now


class MediaJobsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.clock=Clock()
        self.store=JobStore(self.root)
        self.sim=Simulation(self.root,self.clock,duration=240)
        self.runner=Runner(self.store,self.sim,self.sim,self.clock)
        self.batch=self.store.create([source()],profile(),'encoder','request-1',self.clock())
        self.job_id=self.batch['jobs'][0]['id']

    def tearDown(self):
        self.sim.close();self.store.close();self.temp.cleanup()

    def tick(self): return self.runner.tick('encoder')

    def until(self,state):
        for _ in range(80):
            job=self.store.get(self.job_id)
            if job['state']==state: return job
            self.clock.now=max(self.clock.now,job['due'])
            self.tick()
        self.fail('No alcanzó '+state)

    def test_complete_and_restart_preserves_receipts(self):
        job=self.until('completed')
        self.assertTrue(job['publication']['simulated'])
        self.assertTrue(job['index_receipt']['indexed'])
        self.assertEqual(job['publication']['path'],'/peliculas/Carpeta 1/Película 1.optimizada.mkv')
        reopened=JobStore(self.root)
        try: self.assertEqual(reopened.get(self.job_id),job)
        finally: reopened.close()

    def test_five_movies_are_staged_sequentially(self):
        self.store.control(self.batch['id'],'cancel',self.clock())
        batch=self.store.create([source(i) for i in range(2,7)],profile(),'encoder','five',self.clock())
        for item in batch['jobs']:
            self.job_id=item['id']
            self.until('completed')
            for later in self.store.batch(batch['id'])['jobs'][item['position']+1:]:
                self.assertEqual(later['state'],'queued')
        self.assertIsNone(self.tick())

    def test_request_deduplication_and_changed_request(self):
        again=self.store.create([source()],profile(),'encoder','request-1',self.clock())
        self.assertEqual(again['id'],self.batch['id'])
        with self.assertRaises(Conflict):
            self.store.create([source(2)],profile(),'encoder','request-1',self.clock())
        with self.assertRaises(Conflict):
            self.store.create([source()],profile(),'other','request-2',self.clock())

    def test_invalid_kind_identity_and_profile(self):
        for changes in (dict(kind='series'),dict(kind='documentary'),dict(path='/else/film.mkv'),
                        dict(path='/peliculas/../secret.mkv'),dict(identity={}),
                        dict(path='/peliculas/result.optimizada.mkv')):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.store.create([dict(source(2),**changes)],profile(),'encoder','bad',self.clock())
        p=profile();p['preset']['VideoQualitySlider']=25
        with self.assertRaises(ValueError):
            self.store.create([source(2)],p,'encoder','bad-profile',self.clock())

    def test_pause_resume_and_cancel_queued(self):
        self.store.control(self.batch['id'],'pause',self.clock())
        self.assertIsNone(self.tick())
        self.store.control(self.batch['id'],'resume',self.clock())
        self.assertEqual(self.tick()['state'],'copying')
        self.store.control(self.batch['id'],'cancel',self.clock())
        self.assertEqual(self.tick()['state'],'cancelled')

    def test_pause_keeps_monitoring_active_job(self):
        self.until('running')
        self.store.control(self.batch['id'],'pause',self.clock())
        self.until('completed')
        self.assertTrue(self.store.batch(self.batch['id'])['paused'])

    def test_shared_failure_pauses_without_skipping_and_resume_reconciles(self):
        self.until('copying')
        with patch.object(self.sim,'stage',side_effect=SharedFailure('disco lleno')):
            self.assertEqual(self.tick()['state'],'blocked')
        self.assertIsNone(self.tick())
        self.assertTrue(self.store.batch(self.batch['id'])['paused'])
        self.store.control(self.batch['id'],'resume',self.clock())
        self.until('completed')

    def test_uncertain_start_reuses_key_after_lost_response(self):
        self.until('ready')
        original=self.sim.start
        def lost(job,key):
            original(job,key)
            raise UncertainEffect('Conexión perdida tras lanzamiento')
        with patch.object(self.sim,'start',side_effect=lost):
            result=self.tick()
        self.assertEqual(result['state'],'ready')
        self.clock.now=result['due']
        self.tick()
        self.assertEqual(self.sim.db.execute('SELECT count(*) FROM runs').fetchone()[0],1)

    def test_expired_worker_cannot_commit_and_new_worker_reuses_effect(self):
        job=self.until('ready')
        claimed,token=self.store.claim('encoder',self.clock())
        key=f"{job['id']}:0:ready"
        self.store.intention(claimed,token,key,self.clock())
        self.sim.start(claimed,key)
        self.clock.now+=31
        result=self.tick()
        self.assertEqual(result['state'],'running')
        with self.assertRaises(Conflict):
            self.store.finish(claimed,token,dict(state='failed'),self.clock())
        self.assertEqual(self.sim.db.execute('SELECT count(*) FROM runs').fetchone()[0],1)

    def test_two_connections_cannot_claim_same_resource(self):
        other=JobStore(self.root)
        try:
            self.assertIsNotNone(self.store.claim('encoder',self.clock()))
            self.assertIsNone(other.claim('encoder',self.clock()))
        finally: other.close()

    def test_cancel_during_start_reconciles_unrecorded_run(self):
        self.until('ready')
        def cancel_during_start(job,key):
            result=Simulation.start(self.sim,job,key)
            self.store.control(self.batch['id'],'cancel',self.clock())
            return result
        with patch.object(self.sim,'start',side_effect=cancel_during_start),self.assertRaises(Conflict):
            self.tick()
        self.clock.now+=31
        self.assertEqual(self.tick()['state'],'cancelled')
        self.assertEqual(self.sim.db.execute('SELECT stopped FROM runs').fetchone()[0],1)

    def test_bad_output_never_published(self):
        self.until('verifying')
        with patch.object(self.sim,'verify',return_value={'valid':False}),patch.object(self.sim,'publish') as publish:
            self.assertEqual(self.tick()['state'],'failed')
            publish.assert_not_called()

    def test_finished_without_exit_code_is_not_success(self):
        job=self.until('running');self.clock.now=job['due']
        with patch.object(self.sim,'observe',return_value=dict(run_id=job['run_id'],status='finished')):
            self.assertEqual(self.tick()['state'],'running')

    def test_publication_lost_response_does_not_duplicate(self):
        self.until('publishing')
        original=self.sim.publish
        def lost(job,key):
            original(job,key)
            raise OSError('lost')
        with patch.object(self.sim,'publish',side_effect=lost): self.tick()
        self.until('completed')
        self.assertEqual(self.sim.db.execute("SELECT count(*) FROM effects WHERE key LIKE '%:publishing'").fetchone()[0],1)

    def test_one_retry_then_failure_after_verified_stop(self):
        for attempt in range(2):
            job=self.until('running'); self.assertEqual(job['attempt'],attempt)
            self.clock.now=job['due']
            with patch.object(self.sim,'observe',return_value=dict(run_id=job['run_id'],status='finished',exit_code=1)):
                self.tick()
            result=self.tick()
        self.assertEqual(result['state'],'failed')
        self.assertEqual(self.sim.db.execute('SELECT count(*) FROM runs').fetchone()[0],2)

    def test_never_restart_with_other_work(self):
        self.until('running')
        self.store.control(self.batch['id'],'cancel',self.clock())
        with patch.object(self.sim,'stop',return_value=dict(stopped=False,exclusive=False)),patch.object(self.sim,'restart') as restart:
            self.assertEqual(self.tick()['state'],'blocked')
            restart.assert_not_called()

    def test_restart_requires_confirmed_health(self):
        self.until('running');self.store.control(self.batch['id'],'cancel',self.clock())
        with patch.object(self.sim,'stop',return_value=dict(stopped=False,exclusive=True)),patch.object(self.sim,'restart',return_value=dict(stopped=True,healthy=True)) as restart:
            self.assertEqual(self.tick()['state'],'cancelled')
            restart.assert_called_once()

    def test_pending_stop_waits_without_restart_or_losing_cancellation(self):
        self.until('running'); self.store.control(self.batch['id'],'cancel',self.clock())
        with patch.object(self.sim,'stop',return_value=dict(stopped=False,pending=True,exclusive=False)),patch.object(self.sim,'restart') as restart:
            result=self.tick()
            self.assertEqual(result['state'],'cancel_requested')
            self.assertEqual(result['due'],self.clock()+15)
            restart.assert_not_called()

    def test_simulation_never_substitutes_for_live(self):
        self.runner.encoder=UnconfiguredHandBrake()
        self.assertEqual(self.tick()['state'],'blocked')
        self.assertEqual(self.sim.db.execute('SELECT count(*) FROM effects').fetchone()[0],0)

    def test_long_copy_reports_pending_without_starting_encoder(self):
        self.until('copying')
        with patch.object(self.sim,'stage',return_value=dict(pending=True,bytes_copied=12)),patch.object(self.sim,'start') as start:
            result=self.tick()
            self.assertEqual(result['state'],'copying')
            self.assertEqual(result['copy_progress']['bytes_copied'],12)
            self.assertEqual(result['due'],self.clock()+120)
            start.assert_not_called()
        self.until('completed')

    def test_chat_dispatch_reads_jobs_without_executing(self):
        from hexos.agent.chat import Agent
        agent=Agent(self.root,None)
        with agent.store() as store:
            result=agent.tool(store,'media.jobs',{})
            detail=agent.tool(store,'media.job',dict(id=self.job_id))
        self.assertEqual(result['batches'][0]['id'],self.batch['id'])
        self.assertEqual(detail['state'],'queued')
        self.assertEqual(self.sim.db.execute('SELECT count(*) FROM effects').fetchone()[0],0)

    def test_tools_return_real_registry_and_explicit_mode(self):
        self.assertEqual(dispatch(self.root,'media.job',{'id':self.job_id})['mode'],'simulation')
        self.assertFalse(dispatch(self.root,'media.jobs',{})['execution_enabled'])


class PolicyTest(unittest.TestCase):
    def test_timing(self):
        self.assertEqual([check_delay(3360,first=True),check_delay(3360),check_delay(1200),check_delay(60)],
                         [120,1800,1200,60])
        for eta in (None,-1,float('nan'),float('inf'),True,'56'):
            self.assertEqual(check_delay(eta),120)

    def test_stall_requires_multiple_valid_signals_and_samples(self):
        sample=dict(phase='encode',percent=50,output_bytes=1000,activity_counter=3)
        previous,stall=observe_progress(None,sample,0)
        for at in (600,1200):
            previous,stall=observe_progress(previous,sample,at)
            self.assertFalse(stall)
        previous,stall=observe_progress(previous,sample,1800)
        self.assertTrue(stall)
        previous,stall=observe_progress(previous,dict(sample,phase='mux'),1900)
        self.assertFalse(stall)
        with self.assertRaises(ValueError): observe_progress(previous,{},2000)


if __name__=='__main__': unittest.main()
