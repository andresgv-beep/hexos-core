"""Modelo real y Agent completo; NAS sintético y cola sin worker ni credenciales reales."""
import argparse
import json
from pathlib import Path
import time

from hexos.agent.chat_backend.agent import Agent
from hexos.agent.chat_backend.state import AgentDependencies
from hexos.agent.native import NativeRuntime
from hexos.agent.file_catalog.service import FileCatalog
from hexos.agent.file_catalog.sqlite_repository import SQLiteCatalog
from hexos.agent.media_jobs.configuration import load
from hexos.agent.media_jobs.planning import ensure
from hexos.agent.media_jobs.store import JobStore
from tools.media_jobs_test import profile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('runtime','model','template','evidence-dir'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    root=Path(args.evidence_dir);root.mkdir(parents=True,exist_ok=False)
    config=dict(enabled=True,device='synology 1',profiles=[profile()],
                preset_version=dict(VersionMajor=59,VersionMinor=0,VersionMicro=0),
                files=dict(libraries=['/peliculas'],storage='/storage',output='/output',control='/config',
                           ffmpeg='/bin/ffmpeg',ffprobe='/bin/ffprobe'))
    (root/'media_jobs.json').write_text(json.dumps(config))
    # Incluye límites, archivos fuera del rango y subcarpetas con espacios/tildes.
    sizes=[3,8,12,18,25,35,50,80]
    items=[dict(path=f'/peliculas/Película {size}/Vídeo.mkv',root='/peliculas',name='Vídeo.mkv',
                size_bytes=size*10**9,mtime_ns=1,inode=i+1,filesystem_id='1',media_kind='video')
           for i,size in enumerate(sizes)]
    def reader(device,request):
        if request['operation']!='find' or device!='synology 1':
            raise ValueError('Esta prueba solo admite buscar en synology 1')
        return dict(device=device,observed_at='2026-09-22T00:00:00Z',complete=True,roots=['/peliculas'],items=items)
    service=FileCatalog(reader,SQLiteCatalog(root))
    def nas_files(workspace,*,operation,**kwargs):
        if operation not in ('find','search','locations'):
            raise ValueError('Operación no disponible en NAS sintético')
        return getattr(service,operation)(**kwargs)
    def offline(*args,**kwargs):
        raise ValueError('Sin red en esta prueba')
    deps=AgentDependencies(nas_files=nas_files,nas_read=offline,web_read=offline,web_search=offline)
    runtime=NativeRuntime(args.runtime,args.model,8192,root,args.template)
    agent=Agent(root,runtime,dependencies=deps)
    from hexos.agent.hosts import save
    save(root,'synology 1','fixture','not-a-real-credential',host='192.0.2.1')
    records=[]
    try:
        for prompt in (
            'Busca películas MKV entre 8 y 50 GB en /peliculas del synology 1 y dime cuáles hay.',
            'Ahora coge las 5 más pesadas de esas y pásalas a comprimir con el perfil configurado.'):
            store=JobStore(root);ensure(store.db);cfg=load(root)
            store.db.execute('INSERT OR REPLACE INTO media_service VALUES (?,?,?)',
                             (cfg['resource'],time.time(),json.dumps(dict(ready=True,config_digest=cfg['digest']))))
            store.close()
            result=agent.chat(prompt)
            store=JobStore(root)
            batches=store.listing();store.close()
            records.append(dict(prompt=prompt,result=result,batches=batches))
            (root/'conversation.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
            print(json.dumps(dict(prompt=prompt,reply=result.get('reply'),tools=[t['tool'] for t in result.get('tools',[])],
                                  batches=len(batches)),ensure_ascii=False),flush=True)
    finally:
        with agent.store() as store:
            events=[json.loads(r[0]) for r in store.db.execute('SELECT body FROM generation_events ORDER BY seq')]
        (root/'generations.json').write_text(json.dumps(events,ensure_ascii=False,indent=2))
        runtime.close()
    expected=[50,35,25,18,12]
    actual=[j['source']['identity']['size_bytes']//10**9 for b in records[-1]['batches'] for j in b['jobs']]
    valid=not records[0]['batches'] and actual==expected and all(
        j['state']=='queued' for b in records[-1]['batches'] for j in b['jobs'])
    (root/'verdict.json').write_text(json.dumps(dict(passed=valid,expected_gb=expected,actual_gb=actual,
                                                    effects='synthetic queue only; no NAS or encoder worker')))
    if not valid:raise SystemExit('El modelo no completó la selección y cola esperadas; consultar trazas')


if __name__=='__main__':main()
