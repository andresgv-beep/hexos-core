"""Prueba opt-in de tres decisiones internas; no ejecuta acciones NAS."""
import argparse
import copy
import json
from pathlib import Path
from uuid import uuid4
from hexos.agent.native_transport import NativeTransport
from hexos.agent.internal_tasks.native_session import decision
from hexos.agent.internal_tasks.requests import build, validate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('runtime','model','evidence-dir'):parser.add_argument('--'+arg,required=True)
    args=parser.parse_args()
    root=Path(args.evidence_dir);root.mkdir(parents=True,exist_ok=False)
    job=dict(id=uuid4().hex,revision=1,attempt=0,state='awaiting_review',review_kind='publication',
             profile=dict(id='configured-rf19'),source=dict(path='/films/Subcarpeta/Película.mkv',destination='/films/Subcarpeta/Película.optimizada.mkv'),
             validation=dict(valid=True,decoded=True))
    cases=[('verified',copy.deepcopy(job),[dict(id='v1',verified=True,decoded=True)],'publish')]
    job.update(state='running',review_kind=None)
    cases.append(('active',copy.deepcopy(job),[dict(id='p1',percent=45,activity_advancing=True,eta_seconds=900)],'wait'))
    job.update(state='blocked',review_kind='incident',validation={})
    cases.append(('invalid',copy.deepcopy(job),[dict(id='e1',verified=False,error='Duración incorrecta; salida rechazada')],'report_incident'))
    results=[]
    with (root/'runtime.log').open('w') as log:
        transport=NativeTransport(args.runtime,args.model,4096,log)
        try:
            rid=uuid4().hex
            transport.write(dict(type='turn',request_id=rid,session='0',messages=[dict(role='user',content='Responde solamente OK.')],
                                 generation=dict(max_visible_tokens=32,max_thinking_tokens=0,close_turn=True)))
            while True:
                event=transport.receive()
                if event.get('request_id')==rid and event['type']=='error':raise RuntimeError(event)
                if event.get('request_id')==rid and event['type']=='completed':break
            before=transport.control(dict(type='status',session='0'))['model_state']
            for name,job,evidence,expected in cases:
                request=build(job,evidence)
                answer=decision(transport,request)
                validate(request,answer,job)
                after=transport.control(dict(type='status',session='0'))['model_state']
                result=dict(case=name,expected=expected,answer=answer,correct=answer['action']==expected,
                            chat_state_unchanged=before==after)
                results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
        finally:transport.close()
    (root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    if not all(r['correct'] and r['chat_state_unchanged'] for r in results):
        raise RuntimeError('Alguna decisión o el aislamiento no pasó la prueba')


if __name__=='__main__':main()
