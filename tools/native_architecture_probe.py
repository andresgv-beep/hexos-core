"""Sondas de arquitectura con decisiones simuladas; no mide al modelo ni usa GPU.

Imprime comportamientos observados, no una certificación ni tests de aceptación.
Todo efecto se limita a un directorio temporal.
"""
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent


class Runtime:
    def call(self, request):
        pass

    def generate(self, messages):
        return next(self.decisions)


def main():
    findings = {}
    with tempfile.TemporaryDirectory(prefix='hexos-architecture-probe-') as tmp:
        runtime = Runtime()
        agent = Agent(tmp, runtime)
        runtime.decisions = iter([{'tool':'procedure.run','arguments':{'id':'pending_report'}},
                                  {'reply':'Resumen preparado.', 'work':None}])
        draft = agent.chat('Resume mis pendientes')['tools'][0]['result']
        runtime.decisions = iter([{'tool':'report.save','arguments':{'result_id':draft['id']}},
                                  {'reply':'Guardado.', 'work':None}])
        out = agent.chat('Solo dame ideas; no guardes ni cambies nada.')
        findings['save_despite_explicit_prohibition_with_simulated_model'] = out['tools'][0]['result']['saved_report']

        runtime.decisions = iter([{'tool':'procedure.list','arguments':{}} for _ in range(6)] +
                                [{'reply':'He terminado.', 'work':None}])
        try:
            agent.chat('Consulta seis veces los procedimientos y responde.')
        except RuntimeError as exc:
            findings['six_calls_then_final_error'] = str(exc)
        with agent.store() as store:
            uid = store.db.execute("SELECT id FROM conversation WHERE role='user' ORDER BY rowid DESC LIMIT 1").fetchone()[0]
            findings['executed_calls_before_limit'] = store.db.execute(
                'SELECT COUNT(*) FROM tool_events WHERE turn_id=?', (uid,)).fetchone()[0]

        runtime.decisions = iter([{'reply':'','work':None}])
        findings['empty_reply_accepted'] = agent.chat('Dime algo.')['reply'] == ''
    print(json.dumps(findings, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
