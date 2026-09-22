"""Sesión NDJSON propia y ausencia de mensajes/resets sobre la conversación."""
import json
import queue
import unittest
from hexos.agent.internal_tasks.native_session import decision


class FakeTransport:
    pending=None
    poisoned=False
    def __init__(self):self.events=queue.Queue();self.writes=[]
    def write(self,payload):
        self.writes.append(payload)
        if payload['type']=='turn':
            request=json.loads(payload['messages'][1]['content'])
            answer=dict(request_id=request['request_id'],job_id=request['job_id'],expected_revision=request['expected_revision'],
                        action='wait',reason='Working',evidence_ids=[])
            self.events.put(dict(type='completed',request_id=payload['request_id'],visible_text=json.dumps(answer),finish_reason='eos'))
        else:self.events.put(dict(type='result',request_id=payload['request_id']))


class NativeInternalTest(unittest.TestCase):
    def test_fresh_session_each_time_and_no_chat_reset(self):
        transport=FakeTransport()
        request=dict(request_id='r',job_id='j',expected_revision=1)
        decision(transport,request);decision(transport,request)
        sessions=[w['session'] for w in transport.writes if w['type']=='session_open']
        self.assertEqual(len(set(sessions)),2)
        self.assertTrue(all(s.startswith('media-') for s in sessions))
        self.assertFalse(any(w.get('session') in ('0','aux') or w['type']=='reset' for w in transport.writes))
        self.assertEqual(len([w for w in transport.writes if w['type']=='session_close']),2)

    def test_truncated_decision_rejected_and_session_closed(self):
        transport=FakeTransport();original=transport.write
        def emit(payload):
            original(payload)
            if payload['type']=='turn':
                event=transport.events.get();event['finish_reason']='length';transport.events.put(event)
        transport.write=emit
        with self.assertRaises(ValueError):decision(transport,dict(request_id='r',job_id='j',expected_revision=1))
        self.assertEqual(transport.writes[-1]['type'],'session_close')

    def test_transport_with_unfinished_chat_is_not_used(self):
        transport=FakeTransport();transport.pending=('chat','0',[])
        with self.assertRaises(RuntimeError):decision(transport,{})
        self.assertEqual(transport.writes,[])


if __name__=='__main__':unittest.main()
