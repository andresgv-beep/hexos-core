"""Comprobar que el aviso mostrado procede del preámbulo real de Gemma."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent
from hexos.agent.native import NativeRuntime


def main():
    parser=argparse.ArgumentParser()
    for name in ('runtime','model','template','output'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    records=[]
    with tempfile.TemporaryDirectory() as tmp:
        runtime=NativeRuntime(args.runtime,args.model,8192,tmp,args.template)
        try:
            normal_generate=runtime.generate
            for i,request in enumerate(['Consulta los procedimientos disponibles.', 'Busca en el historial qué hablamos sobre el inventario.', 'Consulta los procedimientos disponibles.']):
                if i==2:
                    # Forzar el caso sin preámbulo; la redacción suplementaria usa Gemma real.
                    def without_preamble(messages):
                        value=normal_generate(messages)
                        runtime.last_preamble=None
                        return value
                    runtime.generate=without_preamble
                agent=Agent(Path(tmp)/str(i),runtime)
                result=agent.chat(request)
                with agent.store() as store:
                    generations=[json.loads(r[0]) for r in store.db.execute('SELECT body FROM generation_events ORDER BY seq')]
                prefixes=[g['visible_output'].split('<|tool_call>')[0].strip() for g in generations if '<|tool_call>' in g.get('visible_output','')]
                progress=result['progress']['messages']
                extra=[g['raw'].strip() for g in generations if g.get('kind')=='announcement']
                candidates=extra if i==2 else prefixes+extra
                valid=bool(result['tools'] and progress and progress[0]['text'] in candidates)
                records.append(dict(request=request,result=result,model_preambles=prefixes,valid=valid))
                Path(args.output).write_text(json.dumps(records,ensure_ascii=False,indent=2))
                print(json.dumps(dict(request=request,progress=progress,valid=valid),ensure_ascii=False),flush=True)
        finally:runtime.close()
    if not all(r['valid'] for r in records):raise SystemExit('No se observó preámbulo del modelo en todos los casos')


if __name__=='__main__':main()
