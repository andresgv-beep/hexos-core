"""Aceptación opt-in con sesión NAS real de solo lectura y conversación temporal."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent
from hexos.agent.native import NativeRuntime
from hexos.agent.nas_session import read


def main():
    p=argparse.ArgumentParser()
    for name in ('runtime','model','template','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='hexos-nas-live-') as tmp:
        runtime=NativeRuntime(a.runtime,a.model,8192,tmp,a.template)
        try:
            with patch('hexos.agent.chat.nas_read',side_effect=lambda workspace,**args:read('runtime/workspace',**args)):
                agent=Agent(tmp,runtime)
                try:
                    result=agent.chat('Revisa por SSH los cortes de disco del Synology. Identifica el disco afectado, consulta su SMART y relaciona los errores con el estado del RAID. Dime qué está demostrado y qué no.')
                except Exception as exc:
                    result={'error':str(exc),'tools':[]}
            with agent.store() as s:
                Path(a.output+'.generations.json').write_text(json.dumps([json.loads(r[0]) for r in s.db.execute('SELECT body FROM generation_events')],ensure_ascii=False,indent=2))
            Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2))
            print(json.dumps(result,ensure_ascii=False))
            sections={t['arguments']['section'] for t in result['tools'] if t['tool']=='nas.read' and t['result'].get('exit_code')==0}
            for t in result['tools']:
                r=t['result']
                if t['tool']=='nas.read' and r.get('section')=='diagnosis':
                    if r['storage']['exit_code']==0:sections.add('storage')
                    if r['kernel']['exit_code']==0:sections.add('kernel')
                    if any(s['disk']=='sda' and s['exit_code']==0 for s in r['smart']):sections.add('smart')
            if not {'storage','kernel','smart'}<=sections:raise SystemExit('No completó storage/kernel/SMART')
        finally:runtime.close()


if __name__=='__main__':main()
