"""Demo explícita con reloj virtual; no accede al NAS ni carga un modelo."""
import argparse
import json
import time
from uuid import uuid4
from .store import JobStore
from .simulation import Simulation
from .profiles import freeze
from .runner import Runner
from .policy import TERMINAL


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('demo','list','pause','resume','cancel'))
    parser.add_argument('--workspace',required=True,help='Directorio separado para el registro de simulación')
    parser.add_argument('--count',type=int,choices=range(1,6),default=5)
    parser.add_argument('--batch-id')
    args=parser.parse_args()
    store=JobStore(args.workspace)
    try:
        if args.command=='list':
            print(json.dumps(store.listing(),ensure_ascii=False,indent=2));return
        if args.command!='demo':
            if not args.batch_id: parser.error('--batch-id requerido')
            print(json.dumps(store.control(args.batch_id,args.command,time.time()),ensure_ascii=False,indent=2));return
        current=[time.time()]
        clock=lambda:current[0]
        sim=Simulation(args.workspace,clock)
        try:
            preset=freeze('demo-only',dict(PresetName='DEMO, no preset del usuario',VideoEncoder='x264',
                FileFormat='av_mkv',VideoQualitySlider=19,VideoPreset='fast',AudioList=[]))
            sources=[dict(device='SIMULATED',path=f'/peliculas/Film {i}.mkv',library_root='/peliculas',kind='movie',
                          identity=dict(size_bytes=30000000000,mtime_ns=0,inode=i,filesystem_id='demo'))
                     for i in range(1,args.count+1)]
            batch=store.create(sources,preset,'simulation/handbrake',uuid4().hex,clock())
            runner=Runner(store,sim,sim,clock)
            print('SIMULACIÓN: reloj virtual, sin archivos reales ni SSH.')
            for _ in range(200):
                jobs=store.batch(batch['id'])['jobs']
                pending=[j for j in jobs if j['state'] not in TERMINAL]
                if not pending: break
                current[0]=max(current[0],pending[0]['due'])
                result=runner.tick('simulation/handbrake')
                if result is None: raise RuntimeError('Recurso ocupado; usar un workspace de demo vacío')
                print(json.dumps({k:result[k] for k in ('id','position','state','attempt','due')},ensure_ascii=False))
            else: raise RuntimeError('La demo no terminó dentro del presupuesto')
            print(json.dumps(dict(batch_id=batch['id'],states=[j['state'] for j in store.batch(batch['id'])['jobs']],
                                  mode='simulation'),ensure_ascii=False))
        finally: sim.close()
    finally: store.close()


if __name__=='__main__': main()
