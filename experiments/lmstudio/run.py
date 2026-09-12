"""Separate experimental chat; never starts or stops Hector."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.lmstudio.adapter import Runtime
from hexos.agent.chat import Agent, MAX_INPUT
from hexos.agent import catalog
from hexos.agent.nas_session import read as nas_read


class ExperimentAgent(Agent):
    def __init__(self, workspace, runtime, *, nas_session=False):
        super().__init__(workspace, runtime)
        self.nas_session = nas_session

    def tool(self, store, name, args, *, turn_id=None):
        if name == "nas.read" and self.nas_session:
            catalog.validate(name, args)
            return nas_read(str(ROOT / "runtime/workspace"), **args)
        return super().tool(store, name, args, turn_id=turn_id)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', default='http://127.0.0.1:1234/v1')
    parser.add_argument('--model', help='Exact API model id; omit only if server offers one model')
    parser.add_argument('--port', type=int, default=8081)
    parser.add_argument('--probe', action='store_true', help='List models without generating or starting chat')
    parser.add_argument('--nas-session', action='store_true', help='Usar la sesión NAS de lectura ya abierta; no copia credenciales ni inventario')
    args = parser.parse_args()
    if args.port == 8080:
        parser.error('8080 queda reservado al chat habitual')
    runtime = Runtime(args.endpoint, args.model)
    try:
        models = runtime.request('/models')['data']
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, 'LM Studio no disponible: ' + str(exc) + '\nActiva su servidor local y vuelve a ejecutar.\n')
    ids = [m['id'] for m in models]
    if args.probe:
        print(json.dumps(ids, ensure_ascii=False, indent=2))
        return
    if not args.model:
        if len(ids) != 1:
            parser.error('Indica --model entre: ' + ', '.join(ids))
        runtime.model = ids[0]
    elif args.model not in ids:
        parser.error('Modelo no anunciado por el servidor: ' + args.model)
    # Deliberately fixed separate workspace: no live history, inventory or SSH socket.
    workspace = ROOT / 'runtime' / 'lmstudio-experiment'
    workspace.mkdir(parents=True, exist_ok=True)
    agent = ExperimentAgent(str(workspace), runtime, nas_session=args.nas_session)

    class Handler(BaseHTTPRequestHandler):
        def respond(self, code, obj):
            raw = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path == '/':
                raw = (ROOT / 'hexos/agent/chat.html').read_text()
                raw = raw.replace('<h1>Helios</h1>', '<h1>Helios · prueba LM Studio</h1>')
                raw = raw.replace('Herramientas JSON', 'LM Studio · almacén separado').encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            elif self.path == '/api/status':
                self.respond(200, {'state': agent.state, 'progress': agent.progress, 'mode': 'lmstudio-experiment'})
            elif self.path == '/api/work':
                self.respond(200, [])
            elif self.path == '/api/history':
                with agent.store() as store:
                    rows = [dict(r) for r in store.db.execute('SELECT * FROM conversation ORDER BY rowid DESC LIMIT 100')][::-1]
                    for row in rows:
                        row['progress'] = [dict(e) for e in store.db.execute('SELECT * FROM progress_events WHERE turn_id=? ORDER BY ts', (row['id'],))]
                self.respond(200, rows)
            else:
                self.respond(404, {'error': 'Ruta no disponible en la prueba'})

        def do_POST(self):
            try:
                if self.path not in ('/api/chat', '/api/context/reset'):
                    self.respond(404, {'error': 'Ruta no disponible en la prueba'})
                    return
                size = int(self.headers.get('Content-Length', '-1'))
                if not 0 < size <= MAX_INPUT:
                    raise ValueError('Tamaño inválido')
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise ValueError('Petición incompleta')
                if self.path == '/api/context/reset':
                    if json.loads(raw) != {}:
                        raise ValueError('Se espera {}')
                    result = agent.clear_context()
                else:
                    result = agent.chat(raw.decode())
                self.respond(200, result)
            except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
                self.respond(409, {'error': str(exc)})

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Prueba LM Studio: http://127.0.0.1:{args.port} · {runtime.model}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        runtime.close()


if __name__ == '__main__':
    main()
