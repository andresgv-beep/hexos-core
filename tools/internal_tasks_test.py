"""Aislamiento por construcción y rechazo de propuestas obsoletas, sin GPU."""
from contextlib import contextmanager
import copy
import threading
import unittest

from hexos.agent.internal_tasks.requests import build, validate
from hexos.agent.internal_tasks.resources import InferenceSlot
from hexos.agent.internal_tasks.executor import InternalExecutor


def job():
    return dict(id='movie',revision=3,state='running',profile={'id':'rf19'},source={'path':'/film'},attempt=0)


def decision(request):
    return dict(request_id=request['request_id'],job_id=request['job_id'],
                expected_revision=request['expected_revision'],action='wait',reason='Sigue avanzando',evidence_ids=['e1'])


class InternalTasksTest(unittest.TestCase):
    def test_request_and_decision_are_bound_to_revision_and_evidence(self):
        current=job();request=build(current,[dict(id='e1',percent=50)])
        self.assertEqual(validate(request,decision(request),current)['action'],'wait')
        for change in (dict(job_id='other'),dict(expected_revision=2),dict(action='restart'),
                       dict(evidence_ids=['invented']),dict(shell='rm'),dict(reason='')):
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate(request,dict(decision(request),**change),current)
        with self.assertRaises(ValueError):
            validate(request,decision(request),dict(current,revision=4))
        d=dict(decision(request),action='request_stop',evidence_ids=[])
        with self.assertRaises(ValueError): validate(request,d,current)

    def test_boundaries(self):
        with self.assertRaises(ValueError): build(dict(job(),state='completed'),[])
        with self.assertRaises(ValueError): build(job(),[dict(id='e',text='x'*12000)])
        with self.assertRaises(ValueError): build(job(),[dict(id='e')]*2)

    def test_fresh_session_per_request_and_cleanup_on_error(self):
        slot=InferenceSlot();opened=[];closed=[];requests=[]
        @contextmanager
        def factory(*, binding):
            self_outer.assertEqual(binding.domain, 'text')
            self_outer.assertEqual(binding.block_id, 0x0)
            self_outer.assertEqual(binding.load_policy, 'reuse_resident')
            token=object();opened.append(token)
            class Session:
                def generate(self,request,**budget):
                    self_request=copy.deepcopy(request);requests.append(self_request)
                    self_outer.assertEqual(budget,dict(max_tokens=256,timeout_seconds=30))
                    return decision(request)
            try: yield Session()
            finally: closed.append(token)
        self_outer=self
        executor=InternalExecutor(slot,factory,lambda _:job())
        for _ in range(2):
            self.assertEqual(executor.run(build(job(),[dict(id='e1')]))['status'],'proposed')
        self.assertEqual(opened,closed);self.assertIsNot(opened[0],opened[1])
        self.assertNotEqual(requests[0]['request_id'],requests[1]['request_id'])
        executor.current_job=lambda _:dict(job(),revision=4)
        with self.assertRaises(ValueError): executor.run(build(job(),[dict(id='e1')]))
        self.assertEqual(opened,closed)
        with slot.internal() as acquired: self.assertTrue(acquired)

    def test_user_context_busy_defers_without_creating_session(self):
        slot=InferenceSlot()
        def forbidden(): self.fail('No abrir sesión interna mientras chat ocupa GPU')
        executor=InternalExecutor(slot,forbidden,lambda _:job())
        with slot.chat():
            self.assertEqual(executor.run(build(job(),[]))['status'],'deferred')

    def test_chat_waiter_has_priority_after_internal_release(self):
        slot=InferenceSlot();started=threading.Event();entered=threading.Event();release=threading.Event()
        def user():
            started.set()
            with slot.chat():
                entered.set();release.wait(2)
        with slot.internal() as acquired:
            self.assertTrue(acquired)
            thread=threading.Thread(target=user);thread.start();started.wait(1)
            self.assertFalse(entered.is_set())
        self.assertTrue(entered.wait(1))
        with slot.internal() as acquired: self.assertFalse(acquired)
        release.set();thread.join(2);self.assertFalse(thread.is_alive())


if __name__=='__main__': unittest.main()
