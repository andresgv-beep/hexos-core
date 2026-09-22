"""NDJSON transport for native Gemma; only the generation thread consumes events."""
import json
import os
import queue
import subprocess
import threading
from uuid import uuid4


class TurnCancelled(RuntimeError):
    pass


def visible_preview(text, open_thought=False):
    """Provisional text only: never expose thought/tool channels, even split tokens."""
    text = text.lstrip()
    thought = '<|channel>thought\n'
    if open_thought:
        text = thought + text
    if thought.startswith(text) or (text.startswith('<|channel>') and not text.startswith(thought)):
        return ''
    if text.startswith(thought):
        end = text.find('<channel|>', len(thought))
        if end < 0:
            return ''
        text = text[end + len('<channel|>'):].lstrip()
    # A tool call may follow a preamble. Clear the provisional response; the
    # validated preamble will be published through Agent's existing progress.
    if '<|tool_' in text or '<tool_' in text:
        return ''
    for marker in ('<|', '<channel|>', '<turn|>', '<tool_call|>', '<eos>'):
        at = text.find(marker)
        if at >= 0:
            text = text[:at]
        for n in range(min(len(marker)-1, len(text)), 0, -1):
            if text.endswith(marker[:n]):
                text = text[:-n]
                break
    return text


class NativeTransport:
    def __init__(self, binary, model, ctx, log):
        self.proc = subprocess.Popen([binary, '--model', model, '--ctx', str(ctx), '--temp', '0'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
            env=dict(os.environ, HELIOS_EMBED_MMAP='1', HELIOS_VISION_MMAP='1'))
        self.events = queue.Queue()
        self.write_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.active = None
        self.cancelled = threading.Event()
        self.aux_ready = False
        self.reset_sessions = set()
        self.pending = None
        threading.Thread(target=self.reader, daemon=True).start()
        try:
            ready = self.receive()
            if ready.get('type') != 'ready':
                raise RuntimeError('Héctor no anunció el protocolo NDJSON')
            self.model_info = ready.get('model', {})
        except Exception:
            self.close()
            raise

    def reader(self):
        try:
            for line in self.proc.stdout:
                self.events.put(json.loads(line))
        except Exception as exc:
            self.events.put(exc)
        finally:
            self.events.put(RuntimeError('El motor terminó'))

    def receive(self):
        try:
            event = self.events.get(timeout=180)
        except queue.Empty as exc:
            self.proc.terminate()
            raise RuntimeError('timeout del motor nativo') from exc
        if isinstance(event, Exception):
            raise RuntimeError(str(event)) from event
        return event

    def write(self, request, payload=b''):
        with self.write_lock:
            self.proc.stdin.write(json.dumps(request, ensure_ascii=False).encode() + b'\n')
            if payload:
                self.proc.stdin.write(payload + b'\n')
            self.proc.stdin.flush()

    def control(self, request, payload=b''):
        if getattr(self, 'poisoned', False):
            raise RuntimeError('Sesión interna no reconciliada; reiniciar el runtime antes de continuar')
        rid = uuid4().hex
        self.write(dict(request, request_id=rid), payload)
        while True:
            event = self.receive()
            if event.get('request_id') != rid:
                continue
            if event['type'] == 'error':
                raise RuntimeError(event.get('code', '') + ': ' + event.get('message', ''))
            if event['type'] == 'result':
                return event

    def cancel(self):
        self.cancelled.set()
        with self.state_lock:
            rid = self.active
        if rid:
            self.write(dict(type='cancel', request_id='cancel-' + uuid4().hex, target=rid))

    def start(self, prompt, image=None, auxiliar=False):
        if getattr(self, 'poisoned', False):
            raise RuntimeError('Sesión interna no reconciliada; reiniciar el runtime antes de continuar')
        if self.cancelled.is_set():
            raise TurnCancelled('Generación detenida')
        session = 'aux' if auxiliar else '0'
        if auxiliar and not self.aux_ready:
            self.control(dict(type='session_open', session=session, max_seq_len=1024))
            self.aux_ready = True
        attachments = []
        if image or session in self.reset_sessions:
            # Visual soft tokens cannot be matched against the next full text
            # prompt. Rebuild from the adapter's textual history on that turn.
            self.control(dict(type='reset', session=session))
            self.reset_sessions.discard(session)
        if image:
            pixels, width, height = image
            if len(pixels) > 64*1024*1024:
                raise ValueError('imagen demasiado grande')
            ack = self.control(dict(type='attachment', kind='rgb8', bytes=len(pixels),
                                    width=width, height=height, stride=width*3), pixels)
            attachments.append(ack['request_id'])
        rid = uuid4().hex
        with self.state_lock:
            self.active = rid
        self.pending = (rid, session, attachments)
        self.write(dict(type='turn', request_id=rid, session=session,
            messages=[dict(role='user', content=prompt)], attachment_ids=attachments,
            generation=dict(temperature=0, max_visible_tokens=3072, max_thinking_tokens=0,
                preformatted=True, reuse_prefix=True, close_turn=False,
                stop_tokens=['<|tool_response>'], prefill_progress=True)))

    def finish(self, update=None):
        rid, session, attachments = self.pending
        try:
            while True:
                event = self.receive()
                if event.get('request_id') != rid:
                    continue
                kind = event['type']
                if self.cancelled.is_set() and kind in ('turn_started', 'prefill_progress'):
                    self.cancel()
                if update and kind in ('text_delta', 'prefill_progress', 'prefill', 'turn_started'):
                    update(event)
                if kind == 'error':
                    raise RuntimeError(event.get('code', '') + ': ' + event.get('message', ''))
                if kind == 'completed':
                    return event
        finally:
            with self.state_lock:
                self.active = None
            self.pending = None
            # Attachments are one-shot at this boundary, even if the engine kept
            # an interrupted upload for retry. Drop explicitly to avoid host leaks.
            for attachment in attachments:
                self.reset_sessions.add(session)
                self.control(dict(type='attachment_drop', attachment_id=attachment))

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
