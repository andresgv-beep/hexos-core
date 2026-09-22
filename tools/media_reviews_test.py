"""La publicación depende de una decisión válida; una respuesta tardía no autoriza efectos."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from hexos.agent.media_jobs.store import JobStore
from hexos.agent.media_jobs.runner import Runner
from hexos.agent.media_jobs.simulation import Simulation
from hexos.agent.internal_tasks.queue import ReviewQueue
from hexos.agent.internal_tasks.requests import validate
from tools.media_jobs_test import Clock,source,profile


class ReviewsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.clock=Clock();self.store=JobStore(self.temp.name);self.addCleanup(self.store.close)
        self.sim=Simulation(self.temp.name,self.clock,duration=1);self.addCleanup(self.sim.close)
        self.runner=Runner(self.store,self.sim,self.sim,self.clock)
        self.batch=self.store.create([source()],profile(),'resource','review',self.clock(),require_review=True)
        self.id=self.batch['jobs'][0]['id'];self.queue=ReviewQueue(self.store)

    def until_review(self):
        for _ in range(20):
            job=self.store.get(self.id)
            if job['state']=='awaiting_review':return job
            self.clock.now=max(self.clock(),job['due']);self.runner.tick('resource')
        self.fail('Falta despertar')

    def answer(self,request,action):
        return dict(request_id=request['request_id'],job_id=request['job_id'],expected_revision=request['expected_revision'],
                    action=action,reason='Comprobado en la ficha',evidence_ids=[request['evidence'][0]['id']])

    def test_verified_output_stops_until_review_and_applies_once(self):
        self.until_review()
        self.assertIsNone(self.runner.tick('resource'))
        request,token=self.queue.claim(self.clock())
        self.assertIn('publish',request['allowed_actions'])
        answer=self.answer(request,'publish')
        self.queue.finish(request,token,self.clock(),decision=answer)
        self.assertEqual(self.store.get(self.id)['state'],'publishing')
        with self.assertRaises(ValueError):self.queue.finish(request,token,self.clock(),decision=answer)

    def test_cancel_invalidates_inflight_review(self):
        self.until_review();request,token=self.queue.claim(self.clock())
        self.store.control(self.batch['id'],'cancel',self.clock())
        self.queue.finish(request,token,self.clock(),decision=self.answer(request,'publish'))
        self.assertEqual(self.store.get(self.id)['state'],'cancel_requested')

    def test_altered_request_cannot_authorize_action(self):
        self.until_review();request,token=self.queue.claim(self.clock())
        request['allowed_actions'].append('shell')
        with self.assertRaises(ValueError):self.queue.finish(request,token,self.clock(),decision=self.answer(request,'shell'))

    def test_chat_deferral_does_not_exhaust_retries(self):
        self.until_review()
        for _ in range(5):
            request,token=self.queue.claim(self.clock())
            self.queue.finish(request,token,self.clock(),deferred=True)
            self.clock.now+=2
        self.assertEqual(self.queue.pending()[0]['attempts'],0)

    def test_invalid_model_outputs_stop_after_three_attempts(self):
        self.until_review()
        for _ in range(3):
            request,token=self.queue.claim(self.clock())
            self.queue.finish(request,token,self.clock(),error='invalid JSON')
            self.clock.now+=120
        self.assertIsNone(self.queue.claim(self.clock()))
        self.assertEqual(self.queue.pending()[0]['status'],'attention')
        self.assertEqual(self.store.get(self.id)['state'],'awaiting_review')

    def test_bad_output_never_allows_publication(self):
        with patch.object(self.sim,'verify',return_value=dict(valid=False,reason='duration')):
            for _ in range(15):
                job=self.store.get(self.id)
                if job['state']=='blocked':break
                self.clock.now=max(self.clock(),job['due']);self.runner.tick('resource')
        request,token=self.queue.claim(self.clock())
        self.assertNotIn('publish',request['allowed_actions'])
        with self.assertRaises(ValueError):self.queue.finish(request,token,self.clock(),decision=self.answer(request,'publish'))


if __name__=='__main__':unittest.main()
