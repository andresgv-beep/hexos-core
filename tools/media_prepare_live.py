"""12B + NAS real, isolated conversation, prepare only. No worker is started."""
import argparse
import json
from pathlib import Path
import shutil
import sqlite3
from unittest.mock import patch

from hexos.agent.chat_backend.agent import Agent
from hexos.agent.native import NativeRuntime
from hexos.agent.media_jobs.store import JobStore


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('workspace','evidence-dir','runtime','model','template'):
        p.add_argument('--'+arg,required=True)
    args=p.parse_args()
    root=Path(args.evidence_dir)
    root.mkdir(parents=True,exist_ok=False)
    source=Path(args.workspace)
    for name in ('devices.json','credentials.json','media_jobs.json'):
        shutil.copy2(source/name,root/name)
    for path in source.glob('*_known_hosts'):
        shutil.copy2(path,root/path.name)
    runtime=NativeRuntime(args.runtime,args.model,16384,root,args.template)
    agent=Agent(root,runtime)
    records=[]
    try:
        # A mistaken start must be observable but must never enqueue real work.
        with patch('hexos.agent.media_jobs.planning.start',side_effect=ValueError('Esta prueba no autoriza iniciar compresión')):
            for prompt in (
                'Busca películas MKV entre 8 y 50 GB en la carpeta de películas de multimedia 1 del Synology 1.',
                'De esas, selecciona las cinco más pesadas y prepara el lote con mi perfil configurado, sin iniciar todavía la compresión.',
            ):
                result=agent.chat(prompt)
                records.append(dict(prompt=prompt,result=result))
                (root/'conversation.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
                print(json.dumps(dict(reply=result.get('reply'),tools=[dict(tool=t['tool'],arguments=t['arguments'],failed=t.get('failed'),error=t.get('result',{}).get('error')) for t in result.get('tools',[])]),ensure_ascii=False),flush=True)
    finally:
        runtime.close()
    store=JobStore(root)
    try:
        assert not store.listing(), 'Unexpected queued batch'
    finally:
        store.close()
    tools=[t for r in records for t in r['result'].get('tools',[])]
    assert not any(t['tool']=='media.start' for t in tools), 'Model attempted unauthorized start'
    assert any(t['tool']=='media.options' and not t.get('failed') for t in tools), 'No options lookup'
    prepared=[t for t in tools if t['tool']=='media.prepare' and not t.get('failed') and 'error' not in t.get('result',{})]
    assert prepared, 'No successful preparation'
    expected_root='/volume1/multimedia 1/Multimedia/peliculas'
    searches=[t for t in tools if t['tool']=='nas.find' and not t.get('failed')]
    assert searches and all(t['result']['roots']==[expected_root] for t in searches), 'Search outside requested movie library'
    assert all(t['arguments'].get('min_bytes')==8*10**9 and t['arguments'].get('max_bytes')==50*10**9
               and t['arguments'].get('extensions')==['mkv'] for t in searches), 'Incorrect search filters'
    plan=prepared[-1]
    db=sqlite3.connect((root/'nas_files.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    try:
        prefix=expected_root+'/'
        expected=db.execute("""SELECT path,size_bytes FROM files WHERE scan_id=?
            AND substr(path,1,?)=? AND lower(path) LIKE '%.mkv'
            AND size_bytes BETWEEN ? AND ? ORDER BY size_bytes DESC,path LIMIT 5""",
            (plan['arguments']['scan_id'],len(prefix),prefix,8*10**9,50*10**9)).fetchall()
    finally:
        db.close()
    actual=[(f['path'],f['size_bytes']) for f in plan['result']['files']]
    assert len(actual)==5 and actual==expected, 'Selection differs from full filtered catalog'
    (root/'verdict.json').write_text(json.dumps(dict(passed=True,count=5,root=expected_root,
        size_bytes=[size for _,size in actual],media_start_calls=0,queued_batches=0),indent=2))
    print('PASS: real NAS, exact movie root, decimal GB filters, global top five, options and preparation; no start.',flush=True)


if __name__=='__main__':
    main()
