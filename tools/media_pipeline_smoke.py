"""Recorrido NAS real con biblioteca sintética aislada; reloj de consultas acelerado.

No selecciona películas existentes. Conserva origen, salida y recibos de prueba.
"""
import argparse
import base64
import json
from pathlib import Path
import subprocess
import tempfile
import time
from uuid import uuid4

from hexos.agent.media_jobs.nas_encoder import NasHandBrake, NasEncoderTransport
from hexos.agent.media_jobs.nas_files_adapter import NasFiles
from hexos.agent.media_jobs.nas_files_transport import NasFilesTransport
from hexos.agent.media_jobs.profiles import freeze
from hexos.agent.media_jobs.runner import Runner
from hexos.agent.media_jobs.store import JobStore
from tools.media_encoder_smoke import remote


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('workspace','device','config','preset-json','test-library-root','evidence-dir'):
        parser.add_argument('--'+flag,required=True)
    parser.add_argument('--review-model', help='HNF text/0x0 para revisar realmente antes de publicar')
    parser.add_argument('--runtime', help='helios_runtime NDJSON; requerido con --review-model')
    args=parser.parse_args()
    if args.review_model and not args.runtime:parser.error('--review-model requiere --runtime')
    config=json.loads(Path(args.config).read_text())
    preset=json.loads(Path(args.preset_json).read_text())
    root=str(Path(args.test_library_root)/('smoke-'+uuid4().hex))
    source=root+'/Subcarpeta con espacios/Película sintética.mkv'
    evidence_dir=Path(args.evidence_dir)
    evidence_dir.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory() as tmp:
        fixture=Path(tmp)/'source.mkv'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i',
                        'color=c=blue:size=320x180:rate=24','-f','lavfi','-i',
                        'sine=frequency=440:sample_rate=48000','-t','15','-c:v','libx264',
                        '-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-b:a','16k',str(fixture)],check=True)
        data=base64.b64encode(fixture.read_bytes()).decode()
        if len(data)>90000:raise ValueError('Fixture demasiado grande')
        code=('import os,json,base64; p='+repr(source)+';os.makedirs(os.path.dirname(p),exist_ok=False);'
              'open(p,"xb").write(base64.b64decode('+repr(data)+'));s=os.stat(p);'
              'print("__SOURCE__"+json.dumps(dict(size_bytes=s.st_size,mtime_ns=s.st_mtime_ns,inode=s.st_ino,filesystem_id=str(s.st_dev))))')
        observed=json.loads(remote(args.workspace,args.device,code,'__SOURCE__'))
    config['libraries']=[root]
    # Un tono de 15 s a AAC 16k puede crecer con el preset 160k del usuario.
    # Esta prueba acredita el recorrido, no el ahorro de una película.
    config['require_smaller']=False
    store=JobStore(evidence_dir)
    encoder=NasHandBrake(NasEncoderTransport(args.workspace,args.device),preset['version'])
    files=NasFiles(NasFilesTransport(args.workspace,args.device),config,evidence_dir)
    clock=[time.time()]
    runner=Runner(store,files,encoder,lambda:clock[0])
    batch=store.create([dict(device=args.device,path=source,library_root=root,kind='movie',identity=observed)],
                       freeze('user-rf19-smoke',preset['preset']),args.device+'/HandBrake',uuid4().hex,clock[0],mode='live',
                       require_review=bool(args.review_model))
    job_id=batch['jobs'][0]['id']
    (evidence_dir/'config.json').write_text(json.dumps(config,indent=2))
    deadline=time.monotonic()+120
    transport=None
    model_log=None
    try:
        while time.monotonic()<deadline:
            job=store.get(job_id)
            if job['state'] in ('completed','failed','blocked','cancelled'):break
            clock[0]=max(time.time(),job['due'])
            if job['state']=='awaiting_review':
                from hexos.agent.native_transport import NativeTransport
                from hexos.agent.internal_tasks.native_session import decision
                from hexos.agent.internal_tasks.queue import ReviewQueue
                if transport is None:
                    model_log=(evidence_dir/'model.log').open('w')
                    transport=NativeTransport(args.runtime,args.review_model,4096,model_log)
                queue=ReviewQueue(store)
                request,token=queue.claim(clock[0])
                answer=decision(transport,request)
                queue.finish(request,token,clock[0],decision=answer)
                (evidence_dir/'review.json').write_text(json.dumps(dict(request=request,decision=answer),ensure_ascii=False,indent=2))
                print('REVIEW '+json.dumps(answer,ensure_ascii=False),flush=True)
                continue
            result=runner.tick(job['resource'])
            print(json.dumps({k:result.get(k) for k in ('id','state','error','due')},ensure_ascii=False),flush=True)
            time.sleep(.5)
        job=store.get(job_id)
        (evidence_dir/'result.json').write_text(json.dumps(job,ensure_ascii=False,indent=2))
        if job['state']!='completed':
            raise RuntimeError('Recorrido no completado: '+job['state']+'; revisar ficha antes de reintentar')
        code=('import os,json,hashlib; a='+repr(source)+';b='+repr(job['publication']['path'])+';s=os.stat(a);'
              'print("__VERIFY__"+json.dumps(dict(original_identity=dict(size_bytes=s.st_size,mtime_ns=s.st_mtime_ns,inode=s.st_ino,filesystem_id=str(s.st_dev)),output_hash=hashlib.sha256(open(b,"rb").read()).hexdigest())))')
        check=json.loads(remote(args.workspace,args.device,code,'__VERIFY__'))
        if check['original_identity']!=observed or check['output_hash']!=job['validation']['sha256']:
            raise RuntimeError('No coincide la verificación independiente final')
        (evidence_dir/'independent-check.json').write_text(json.dumps(check,indent=2))
        print('OK: copia → conversión → verificación → publicación → catálogo; original intacto.')
    finally:
        if transport:transport.close()
        if model_log:model_log.close()
        store.close()


if __name__=='__main__':main()
