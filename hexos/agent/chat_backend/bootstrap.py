"""CLI y ciclo de vida del servidor; conserva los argumentos existentes."""
from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path
from ..continuity import HeraProfile
from ..telemetry import SystemTelemetry
from .agent import Agent
from .model_lifecycle import ModelLifecycle
from .runtime import Runtime
from .server import make_handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--port', type=int, default=8080)
    # 8192 se quedaba corto en cuanto había dos lecturas de red en la ventana:
    # el prompt llegaba a ~7.100 tokens y no quedaba sitio para responder.
    # Con 16384 y visión el pico medido es 5.381 MiB de 8.151.
    # 32k medido en la RTX 5070: el KV de este Gemma cuesta 48 KiB por token
    # —24 de sus 42 capas guardan el suyo, 2 cabezas KV de 256 en FP16— así que
    # son 1,5 GiB reservados al arrancar, y quedan 1,4 GiB libres. Con 16k se
    # llegaba a 16.380 de 16.384 y la respuesta se cortaba a media palabra.
    parser.add_argument('--ctx', type=int, default=32768)
    parser.add_argument('--hera', help='CLI HERA para recuperar el perfil confirmado')
    parser.add_argument('--memory-home', help='Perfil HERA existente; requiere --hera')
    parser.add_argument('--native-template', help='Gemma nativo con plantilla oficial; usar --runtime helios_runtime para progreso y cancelación')
    parser.add_argument('--native-thinking', action='store_true', help='Activar pensamiento de Gemma en el adaptador nativo')
    parser.add_argument('--model-idle-seconds', type=int, default=600,
                        help='Descargar el modelo tras estos segundos sin actividad (por defecto: 600)')
    args = parser.parse_args()
    if args.model_idle_seconds <= 0:
        parser.error('--model-idle-seconds debe ser mayor que cero')
    if args.native_thinking and not args.native_template:
        parser.error('--native-thinking requiere --native-template')
    if bool(args.hera) != bool(args.memory_home):
        parser.error('--hera y --memory-home deben indicarse juntos')
    Path(args.workspace).mkdir(parents=True, exist_ok=True)
    if args.native_template:
        from ..native import NativeRuntime
        runtime = ModelLifecycle(
            lambda: NativeRuntime(args.runtime,args.model,args.ctx,args.workspace,
                                  args.native_template,thinking=args.native_thinking),
            ctx=args.ctx, thinking=args.native_thinking,
            idle_seconds=args.model_idle_seconds, native=True,
            progressive=Path(args.runtime).name != 'helios_formatted')
    else:
        runtime = Runtime(args.runtime, args.model, args.ctx, args.workspace)
    agent = Agent(args.workspace, runtime,
                  HeraProfile(args.hera, args.memory_home) if args.hera else None)
    # Lo que la persona dejó puesto manda sobre el flag con que se arrancó.
    agent.restore_thinking()
    system_telemetry = SystemTelemetry()
    allowed_origins = {'http://127.0.0.1:%d' % args.port, 'http://localhost:%d' % args.port,
                       'http://[::1]:%d' % args.port}
    Handler = make_handler(agent, system_telemetry, allowed_origins,
                           Path(__file__).resolve().parent.parent / 'chat.html',
                           native_template=args.native_template)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'HexOS agente: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        runtime.close()
