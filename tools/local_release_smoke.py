"""Opt-in real model smoke; ephemeral workspace, no NAS or live chat writes."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.native import NativeRuntime
from hexos.agent.chat import Agent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'model', 'template'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='helios-release-smoke-') as workspace:
        rt = NativeRuntime(args.runtime, args.model, 16384, workspace, args.template)
        try:
            original_tools = rt.tools
            rt.tools = []
            write = rt._transport.write
            def bounded(request, payload=b''):
                if request['type'] == 'turn':
                    request['generation']['max_visible_tokens'] = 128
                return write(request, payload)
            rt._transport.write = bounded
            out = rt.generate([dict(role='user', content=
                'Devuelve solamente un bloque de código HTML completo, de unas 150 palabras como máximo, '
                'con doctype, head, style, body, un título Hola y un botón que cambia ese título a Adiós '
                'usando JavaScript. Sin explicaciones.')])
            generation = rt.last_generation
            assert generation['continuations'] >= 1, 'No se ejercitó el corte'
            assert '</html>' in out['reply']
            assert out['reply'].lower().count('<!doctype') == 1
            print(json.dumps(dict(test='code_continuation', finish=generation['finish_reason'],
                                  segments=generation['segments']), ensure_ascii=False), flush=True)
            rt._transport.write = write
            rt.call({'type': 'reset'})
            rt.tools = [tool for tool in original_tools if tool['function']['name'] == 'note_list']
            agent = Agent(workspace, rt)
            result = agent.chat('Consulta las notas guardadas usando la herramienta de notas y dime cuántas hay.')
            assert any(step['tool'] == 'note.list' and not step.get('failed') for step in result['tools'])
            print(json.dumps(dict(test='isolated_tool', tools=[step['tool'] for step in result['tools']],
                                  reply=result['reply']), ensure_ascii=False), flush=True)
        finally:
            rt.close()


if __name__ == '__main__':
    main()
