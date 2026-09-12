"""Recorrido con el modelo real y almacén temporal; no toca el perfil de la persona."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent, Runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--native-template')
    parser.add_argument('--native-thinking', action='store_true')
    parser.add_argument('--inject-invalid-arguments', action='store_true',
                        help='Sabotea una llamada para probar recuperación, no fallo natural')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='hexos-procedures-live-') as workspace:
        if args.native_template:
            from hexos.agent.native import NativeRuntime
            runtime = NativeRuntime(args.runtime,args.model,8192,workspace,args.native_template,thinking=args.native_thinking)
        else:
            runtime = Runtime(args.runtime, args.model, 8192, workspace)
        generate = runtime.generate
        injected = False
        def traced(messages):
            nonlocal injected
            try:
                result = generate(messages)
            except Exception:
                if args.native_template:
                    print(json.dumps({'failed_raw':getattr(runtime,'last_raw',''),
                                      'header':getattr(runtime,'last_header',[])},ensure_ascii=False),flush=True)
                raise
            if args.inject_invalid_arguments and not injected and result.get('tool') == 'procedure.run':
                result['arguments']['state'] = 'pendiente'
                injected = True
                print('INYECCIÓN DE PRUEBA: argumento state no admitido', flush=True)
            print(json.dumps({'model_output': result}, ensure_ascii=False), flush=True)
            return result
        runtime.generate = traced
        try:
            agent = Agent(workspace, runtime)
            with agent.store() as s:
                s.dispatch(dict(op='create', title='Revisar espacio de NAS Faro',
                                request='Revisa el espacio', source_ref='test:persona'), actor='user')
            first = agent.chat('Resume mis trabajos pendientes.')
            print(json.dumps({'step':'report','result':first}, ensure_ascii=False), flush=True)
            drafts = [t['result'] for t in first['tools'] if t['tool']=='procedure.run' and 'id' in t['result']]
            assert drafts, 'El modelo no ejecutó el procedimiento'
            with agent.store() as s:
                assert s.db.execute('SELECT COUNT(*) FROM agent_reports').fetchone()[0] == 0, 'Guardó sin petición'
            if args.inject_invalid_arguments:
                assert injected, 'No se ejercitó el sabotaje'
                assert any('error' in t['result'] for t in first['tools']), 'No se rechazó el argumento'
            saved = agent.chat('Guárdalo.')
            print(json.dumps({'step':'save_existing','result':saved}, ensure_ascii=False), flush=True)
            reports = [t['result'] for t in saved['tools'] if t['tool']=='report.save' and 'id' in t['result']]
            assert reports, 'No guardó el resultado anterior'
            report = reports[0]
            assert report['result_id'] == drafts[0]['id'], 'Guardó otro resultado'
            agent.clear_context()
            agent = Agent(workspace, runtime)
            second = agent.chat('Recupera el informe del último encargo y dime qué había pendiente.')
            print(json.dumps({'step':'recover_after_reset_restart','result':second}, ensure_ascii=False), flush=True)
            assert (any(t['tool']=='report.get' and t['result'].get('id')==report['id']
                       for t in second['tools']) or any(s['tool']=='report.get' and s['id']==report['id']
                       and s.get('text')==report['text'] for s in second.get('context_sources', []))), 'No recuperó el informe original'
            assert 'Faro' in second['reply'], 'No comunicó el trabajo recuperado'
            with agent.store() as s:
                assert len(s.listing())==1, 'La consulta creó otra tarea'
                assert s.db.execute('SELECT COUNT(*) FROM agent_reports').fetchone()[0] == 1, 'Recuperar creó otro informe'
                assert s.db.execute('SELECT COUNT(*) FROM agent_results').fetchone()[0] == 1, 'Recalculó el resumen'
                current_job = s.get(drafts[0]['items'][0]['id'])
                s.dispatch(dict(op='update', id=current_job['id'], revision=current_job['revision'],
                                state='terminado', summary='Finalizado en esta prueba'), actor='user')
            fresh = agent.chat('Consulta ahora mis trabajos pendientes y prepara un resumen actualizado.')
            print(json.dumps({'step':'fresh_state_after_old_report','result':fresh}, ensure_ascii=False), flush=True)
            assert any(t['tool']=='procedure.run' and t['result'].get('items')==[] for t in fresh['tools']), \
                'Reutilizó el resumen histórico para responder sobre el estado actual'
            # Nuevo historial: petición vaga, aclaración y ejecución sin repetir filtros.
            other = Agent(Path(workspace) / 'clarification', runtime)
            with other.store() as s:
                s.dispatch(dict(op='create', title='Revisar copias del NAS',
                                request='Revisa copias', source_ref='test:persona'), actor='user')
            vague = other.chat('Haz un informe general.')
            print(json.dumps({'step':'vague_request','result':vague}, ensure_ascii=False), flush=True)
            clarified = other.chat('Sí, un resumen de los trabajos pendientes.')
            print(json.dumps({'step':'clarified','result':clarified}, ensure_ascii=False), flush=True)
            assert any(t['tool']=='procedure.run' and 'id' in t['result'] for t in clarified['tools']), \
                'Pidió otra aclaración o no hizo el informe'
            ideas = other.chat('¿Qué podría mejorar en la organización de los trabajos? Solo dame ideas.')
            print(json.dumps({'step':'ideas_only','result':ideas},ensure_ascii=False),flush=True)
            with other.store() as s:
                assert s.db.execute('SELECT COUNT(*) FROM agent_reports').fetchone()[0]==0, 'Guardó sin pedirlo'
                assert len(s.listing())==1, 'Creó un trabajo por pedir ideas'
            print('PASS: procedimiento, informe y recuperación real sin contexto', flush=True)
        finally:
            runtime.close()


if __name__ == '__main__':
    main()
