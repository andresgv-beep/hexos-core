"""Adaptador JSON del proceso de inferencia Héctor."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import threading
from uuid import uuid4

from ..work import strict_json
from ..decisions import InvalidDecision


class Runtime:
    def __init__(self, binary, model, ctx, workspace):
        self.log = open(Path(workspace) / 'hector.log', 'a')
        self.proc = subprocess.Popen([binary, '--model', model, '--ctx', str(ctx)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
            text=True, bufsize=1, env=dict(os.environ, HELIOS_EMBED_MMAP='1'))
        self.events = queue.Queue()
        threading.Thread(target=self.reader, daemon=True).start()
        try:
            while self.event().get('type') != 'ready':
                pass
        except Exception:
            self.close()
            raise

    def reader(self):
        try:
            for line in self.proc.stdout:
                try:
                    self.events.put(json.loads(line))
                except ValueError:
                    self.events.put({'type': 'error', 'message': 'Salida del motor no válida'})
        finally:
            self.events.put({'type': 'error', 'message': 'El motor terminó'})

    def event(self):
        try:
            event = self.events.get(timeout=180)
        except queue.Empty as exc:
            self.proc.terminate()
            raise RuntimeError('El motor no respondió dentro de 180 segundos') from exc
        if event.get('type') == 'error':
            raise RuntimeError(event.get('message', 'Error de inferencia'))
        return event

    def call(self, request):
        rid = uuid4().hex
        request['request_id'] = rid
        self.proc.stdin.write(json.dumps(request, ensure_ascii=False) + '\n')
        self.proc.stdin.flush()
        while True:
            event = self.event()
            if event.get('request_id') == rid and event.get('type') in ('completed', 'result'):
                return event

    def generate(self, messages):
        result = self.call(dict(type='turn', messages=messages,
            generation=dict(temperature=0.0, max_visible_tokens=900, max_thinking_tokens=256)))
        if result.get('finish_reason') != 'eos':
            raise RuntimeError('Respuesta incompleta del modelo; no se aplica clasificación')
        try:
            output = strict_json(result['visible_text'])
        except ValueError as exc:
            raise InvalidDecision('Respuesta del modelo sin JSON válido; no se ejecutó ninguna acción') from exc
        if not isinstance(output, dict):
            raise ValueError('Respuesta JSON no es un objeto')
        # El campo work es opcional en una respuesta puramente conversacional.
        if 'reply' in output and 'work' not in output:
            output['work'] = None
        return output

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.log.close()
