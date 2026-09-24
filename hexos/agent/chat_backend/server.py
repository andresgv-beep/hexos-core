"""Adaptador HTTP. Las rutas y los códigos de respuesta se mantienen."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from .. import core, notes, catalog
from ..work import strict_json, string
from .images import decode_image
from .settings import MAX_INPUT
from .history_archive import history_page
from .file_http import serve as serve_file


def make_handler(agent, system_telemetry, allowed_origins, ui_path: Path, *, native_template=False):
    """Inyecta dependencias y la ruta original de chat.html (no la del subpaquete)."""
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, obj):
            data = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == '/':
                data = ui_path.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif self.path == '/api/files' or self.path.startswith('/api/files/'):
                serve_file(self, agent.env.workspace)
            elif self.path == '/api/status':
                self.respond(200, {'state': agent.state, 'progress':agent.progress,
                                   'active_tools':[dict(item) for item in agent.active_tools],
                                   'credential_request': agent.credential_request,
                                   'thinking': agent.thinking(),
                                   'model': (agent.runtime.status()
                                             if hasattr(agent.runtime, 'status') else
                                             {'state':'ready', 'ready':True}),
                                   'generation': agent.generation_snapshot(),
                                   'metrics': agent.metrics_snapshot(),
                                   'mode':'native-experimental' if native_template else 'json'})
            elif self.path == '/api/core':
                # El panel se pinta sin gastar un turno del modelo, pero del MISMO
                # recuento que responde el chat: no puede haber dos verdades.
                with agent.store() as store:
                    self.respond(200, core.overview(store, agent.profile))
            elif self.path == '/api/notes' or self.path.startswith('/api/notes?'):
                consulta = parse_qs(urlparse(self.path).query)
                with agent.store() as store:
                    try:
                        self.respond(200, notes.listing(
                            store, consulta.get('query', [''])[0],
                            consulta.get('state', [None])[0],
                            {'true': True, 'false': False}.get(consulta.get('favorite', [''])[0]),
                            int(consulta.get('limit', ['50'])[0])))
                    except ValueError as exc:
                        self.respond(400, {'error': str(exc)})
            elif self.path.startswith('/api/notes/'):
                identificador = unquote(self.path[len('/api/notes/'):]).split('?')[0]
                with agent.store() as store:
                    try:
                        self.respond(200, dict(notes.get(store, identificador),
                                               revisions=notes.history(store, identificador)))
                    except ValueError as exc:
                        self.respond(404, {'error': str(exc)})
            elif self.path == '/api/telemetry':
                self.respond(200, system_telemetry.snapshot())
            elif self.path == '/api/work':
                with agent.store() as store:
                    jobs = [json.loads(r['body']) for r in store.db.execute('SELECT body FROM jobs ORDER BY rowid DESC LIMIT 100')]
                self.respond(200, jobs)
            elif self.path.startswith('/api/history?'):
                query = parse_qs(urlparse(self.path).query)
                try:
                    with agent.store() as store:
                        page = history_page(store, limit=int(query.get('limit', ['100'])[0]),
                            before=int(query['before'][0]) if 'before' in query else None)
                    self.respond(200, page)
                except ValueError as exc:
                    self.respond(400, {'error': str(exc)})
            elif self.path == '/api/history':
                with agent.store() as store:
                    rows = [dict(r) for r in store.db.execute('SELECT * FROM conversation ORDER BY rowid DESC LIMIT 100')][::-1]
                    for row in rows:
                        if row['role'] != 'user':
                            row['progress'] = []
                            row['tools'] = []
                            continue
                        row['progress'] = [dict(e) for e in store.db.execute('SELECT * FROM progress_events WHERE turn_id=? ORDER BY ts', (row['id'],))]
                        # Sin esto, al recargar se veía la conversación pero no lo ejecutado.
                        row['tools'] = []
                        for event in store.db.execute(
                                'SELECT ts, body FROM tool_events WHERE turn_id=? ORDER BY seq', (row['id'],)):
                            entry = json.loads(event['body'])
                            # Los turnos anteriores a la traza ampliada se completan al leerlos,
                            # para que la interfaz no tenga que distinguir formatos.
                            if 'effect' not in entry:
                                effect = catalog.TOOLS.get(entry.get('tool'), {}).get('effect', 'read')
                                entry.update(effect=effect, changes_state=effect != 'read', ts=event['ts'],
                                             seconds=None, historical=True,
                                             failed=isinstance(entry.get('result'), dict) and 'error' in entry['result'])
                            row['tools'].append(entry)
                self.respond(200, rows)
            else:
                self.respond(404, {'error':'ruta inexistente'})

        def do_POST(self):
            if self.path not in ('/api/chat', '/api/work', '/api/context/reset', '/api/credentials',
                                 '/api/thinking', '/api/cancel', '/api/model/warmup'):
                self.respond(404, {'error':'ruta inexistente'})
                return
            # Una página abierta en otra pestaña no puede accionar el agente ni,
            # sobre todo, provocar la ventana que pide una credencial.
            origin = self.headers.get('Origin')
            if origin is not None and origin not in allowed_origins:
                self.respond(403, {'error':'Origen no permitido: ' + origin})
                return
            try:
                size = int(self.headers.get('Content-Length', '-1'))
                if not 0 < size <= MAX_INPUT:
                    self.respond(413, {'error':'Máximo 8 MiB; no se ha guardado ni recortado'})
                    return
                data = self.rfile.read(size)
                if len(data) != size:
                    raise ValueError('Mensaje incompleto')
                if self.path == '/api/cancel':
                    payload = strict_json(data.decode('utf-8'))
                    if set(payload) != {'request_id'}:
                        raise ValueError('se espera request_id')
                    rid = string(payload['request_id'], 'request_id', 128)
                    self.respond(200, agent.cancel_generation(rid))
                elif self.path == '/api/model/warmup':
                    if strict_json(data.decode('utf-8')) != {}:
                        raise ValueError('Se espera {}')
                    if hasattr(agent.runtime, 'warmup'):
                        self.respond(202, agent.runtime.warmup())
                    else:
                        self.respond(200, {'state':'ready', 'ready':True})
                elif self.path == '/api/credentials':
                    saved = agent.save_access(strict_json(data.decode('utf-8')))
                    operation = saved.pop('_resume_operation', None)
                    resume = saved.get('resume')
                    if resume and operation:
                        try:
                            saved['resumed_request'] = resume
                            saved['resumed'] = agent.resume_access(resume, operation)
                        except (ValueError, RuntimeError, OSError) as exc:
                            # El acceso ya está guardado. Un fallo posterior no
                            # puede convertir ese hecho en «no se guardó».
                            saved['resume_error'] = str(exc)
                    self.respond(200, saved)
                elif self.path == '/api/thinking':
                    payload = strict_json(data.decode('utf-8'))
                    if set(payload) != {'enabled'}:
                        raise ValueError('se espera {"enabled": true|false}')
                    self.respond(200, agent.set_thinking(payload['enabled']))
                elif self.path == '/api/context/reset':
                    if strict_json(data.decode('utf-8')) != {}:
                        raise ValueError('Se espera {}')
                    self.respond(200, agent.clear_context())
                elif self.path == '/api/work':
                    with agent.store() as store:
                        result = store.dispatch(strict_json(data.decode('utf-8')), actor='user')
                    self.respond(200, result)
                elif self.headers.get('Content-Type','').startswith('application/json'):
                    # Forma ampliada: adjunto o pensamiento limitado a este turno.
                    # El text/plain de siempre sigue valiendo para un turno sin imagen.
                    payload = strict_json(data.decode('utf-8'))
                    if set(payload) - {'text', 'image', 'thinking', 'display_text', 'request_id'}:
                        raise ValueError('campos permitidos: text, image, thinking, display_text, request_id')
                    rid = payload.get('request_id')
                    if rid is not None:
                        rid = string(rid, 'request_id', 128)
                    thinking = payload.get('thinking')
                    if thinking is not None and not isinstance(thinking, bool):
                        raise ValueError('thinking debe ser true o false')
                    # Con imagen el texto puede venir vacío: la pregunta la pone el agente.
                    mensaje = string(payload.get('text'), 'text', MAX_INPUT,
                                     empty=payload.get('image') is not None)
                    visible = payload.get('display_text')
                    if visible is not None:
                        visible = string(visible, 'display_text', MAX_INPUT)
                    self.respond(200, agent.chat(mensaje, decode_image(payload.get('image')),
                                                 thinking=thinking, display_text=visible, request_id=rid))
                else:
                    self.respond(200, agent.chat(data.decode('utf-8')))
            except (ValueError, RuntimeError, OSError) as exc:
                self.respond(409, {'error':str(exc)})
    return Handler
