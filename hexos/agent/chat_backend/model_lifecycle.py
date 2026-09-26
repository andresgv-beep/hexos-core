"""Carga perezosa y descarga por inactividad del modelo propiedad de HexOS."""
from __future__ import annotations

from contextlib import contextmanager
import threading
import time
from ..native_transport import TurnCancelled
from ..internal_tasks.resources import InferenceSlot


class ModelLifecycle:
    """Mantiene un runtime cargado solo mientras la conversación lo necesita.

    El adaptador concreto sigue siendo dueño del protocolo de Héctor. Esta capa
    solo decide cuándo existe. Tras una descarga no conserva ``messages`` ni la
    posición KV: ContextManager ve un runtime vacío y reconstruye el contexto
    desde el archivo de conversación en el turno siguiente.
    """

    def __init__(self, factory, *, ctx, thinking=False, idle_seconds=600,
                 native=True, progressive=True):
        if idle_seconds <= 0:
            raise ValueError('idle_seconds debe ser mayor que cero')
        self._factory = factory
        self.ctx = ctx
        self.native = native
        self._progressive = progressive
        self._thinking = bool(thinking)
        self._idle_seconds = float(idle_seconds)
        self._runtime = None
        self._state = 'unloaded'
        self._error = None
        self._busy = 0
        self._last_activity = time.monotonic()
        self._reload_requested = False
        self._closed = False
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._turn_acquired = False
        self._harvest_pending = False
        self._pending_image = None
        self._on_update = None
        self.inference_slot = InferenceSlot()
        self._chat_slot = None
        self._io_lock = threading.RLock()
        threading.Thread(target=self._idle_worker, daemon=True,
                         name='hexos-model-idle').start()

    @property
    def thinking(self):
        return self._thinking

    @thinking.setter
    def thinking(self, value):
        self._thinking = bool(value)
        with self._condition:
            if self._runtime is not None:
                self._runtime.thinking = self._thinking

    @property
    def progressive(self):
        return self._progressive

    @property
    def messages(self):
        with self._condition:
            return self._runtime.messages if self._runtime is not None else []

    @property
    def kv_position(self):
        with self._condition:
            return self._runtime.kv_position if self._runtime is not None else 0

    @property
    def harvest_pending(self):
        return self._harvest_pending

    @harvest_pending.setter
    def harvest_pending(self, value):
        self._harvest_pending = bool(value)
        with self._condition:
            if self._runtime is not None:
                self._runtime.harvest_pending = self._harvest_pending

    @property
    def pending_image(self):
        with self._condition:
            return (self._runtime.pending_image if self._runtime is not None
                    else self._pending_image)

    @pending_image.setter
    def pending_image(self, value):
        self._pending_image = value
        with self._condition:
            if self._runtime is not None:
                self._runtime.pending_image = value

    @property
    def on_update(self):
        return self._on_update

    @on_update.setter
    def on_update(self, value):
        self._on_update = value
        with self._condition:
            if self._runtime is not None:
                self._runtime.on_update = value

    def status(self):
        with self._condition:
            remaining = None
            if self._state == 'ready' and not self._busy:
                remaining = max(0, self._idle_seconds -
                                (time.monotonic() - self._last_activity))
            return dict(state=self._state, ready=self._state == 'ready',
                        busy=bool(self._busy), idle_seconds=self._idle_seconds,
                        unload_in_seconds=remaining,
                        error=str(self._error) if self._error else None)

    def _start_loading_locked(self):
        if self._state in ('loading', 'ready', 'unloading') or self._closed:
            return
        self._state = 'loading'
        self._error = None
        threading.Thread(target=self._load, daemon=True,
                         name='hexos-model-load').start()

    def _load(self):
        runtime = None
        try:
            runtime = self._factory()
        except Exception as exc:
            with self._condition:
                if not self._closed:
                    self._error = exc
                    self._state = 'error'
                self._condition.notify_all()
            return
        with self._condition:
            if self._closed:
                close = True
            else:
                close = False
                runtime.thinking = self._thinking
                runtime.harvest_pending = self._harvest_pending
                runtime.pending_image = self._pending_image
                runtime.on_update = self._on_update
                self._runtime = runtime
                self._state = 'ready'
                self._last_activity = time.monotonic()
                self._condition.notify_all()
        if close:
            runtime.close()

    def warmup(self):
        """Inicia la carga sin bloquear al navegador; es seguro repetirlo."""
        with self._condition:
            if self._closed:
                raise RuntimeError('HexOS se está cerrando')
            if self._state == 'error' and self._runtime is not None:
                raise RuntimeError('No se pudo cerrar el modelo: ' + str(self._error))
            self._last_activity = time.monotonic()
            if self._state == 'error':
                self._state = 'unloaded'
            if self._state == 'unloading':
                self._reload_requested = True
            else:
                self._start_loading_locked()
            return self.status()

    def acquire_turn(self, stop=None):
        if self._turn_acquired:
            return
        slot = self.inference_slot.chat()
        slot.__enter__()
        try:
            self._acquire_turn(stop)
            self._chat_slot = slot
        except BaseException:
            slot.__exit__(None, None, None)
            raise

    def _acquire_turn(self, stop=None):
        """Reserva el modelo para todo el turno y espera el ``ready`` real."""
        with self._condition:
            if self._turn_acquired:
                return
            self._busy += 1
            self._last_activity = time.monotonic()
            try:
                # Un calentamiento previo pudo fallar. El envío hace un intento
                # nuevo, pero una carga que falle durante ESTE envío se devuelve
                # como error: nunca se reintenta en bucle a espaldas de la persona.
                if self._state == 'error':
                    if self._runtime is not None:
                        raise RuntimeError('No se pudo cerrar el modelo: ' + str(self._error))
                    self._state = 'unloaded'
                    self._error = None
                while True:
                    if stop is not None and stop.is_set():
                        raise TurnCancelled('Carga cancelada para este turno')
                    if self._closed:
                        raise RuntimeError('HexOS se está cerrando')
                    if self._state == 'ready':
                        self._turn_acquired = True
                        return
                    if self._state == 'error':
                        raise RuntimeError('No se pudo cargar el modelo: ' + str(self._error))
                    elif self._state == 'unloaded':
                        self._start_loading_locked()
                    self._condition.wait(timeout=.1)
            except Exception:
                self._busy -= 1
                self._condition.notify_all()
                raise

    def release_turn(self):
        with self._condition:
            if not self._turn_acquired:
                return
            self._turn_acquired = False
            self._busy -= 1
            self._last_activity = time.monotonic()
            self._condition.notify_all()
        if self._chat_slot is not None:
            slot, self._chat_slot = self._chat_slot, None
            slot.__exit__(None, None, None)

    @contextmanager
    def _use(self):
        with self._condition:
            self._busy += 1
            self._last_activity = time.monotonic()
            try:
                while True:
                    if self._closed:
                        raise RuntimeError('HexOS se está cerrando')
                    if self._state == 'ready':
                        runtime = self._runtime
                        break
                    if self._state == 'error':
                        error = self._error
                        raise RuntimeError('No se pudo cargar el modelo: ' + str(error))
                    if self._state == 'unloaded':
                        self._start_loading_locked()
                    self._condition.wait()
            except Exception:
                self._busy -= 1
                self._condition.notify_all()
                raise
        try:
            yield runtime
        finally:
            with self._condition:
                self._busy -= 1
                self._last_activity = time.monotonic()
                self._condition.notify_all()

    def _invoke(self, name, *args, **kwargs):
        with self._io_lock, self._use() as runtime:
            return getattr(runtime, name)(*args, **kwargs)

    def internal_decision(self, request):
        with self.inference_slot.internal() as acquired:
            if not acquired:
                return dict(status='deferred')
            with self._io_lock, self._use() as runtime:
                return dict(status='proposed', decision=runtime.internal_decision(request))

    def begin_request(self, callback):
        return self._invoke('begin_request', callback)

    def generate(self, messages):
        return self._invoke('generate', messages)

    def call(self, request):
        # Si no hay proceso, reset ya está cumplido: no cargues 5 GiB solo para
        # borrar un KV inexistente.
        if request == {'type': 'reset'}:
            with self._condition:
                if self._runtime is None:
                    self._pending_image = None
                    return {'ok': True}
        return self._invoke('call', request)

    def attach_image(self, pixels, width, height):
        return self._invoke('attach_image', pixels, width, height)

    def attach_audio(self, pcm, sample_rate):
        return self._invoke('attach_audio', pcm, sample_rate)

    def transcribe(self, clip):
        return self._invoke('transcribe', clip)

    def begin_tool(self, messages, operation):
        return self._invoke('begin_tool', messages, operation)

    def tool_result(self, result):
        return self._invoke('tool_result', result)

    def require_read(self, name):
        return self._invoke('require_read', name)

    def extract_facts(self, text):
        return self._invoke('extract_facts', text)

    def announce(self, tool, arguments, request):
        return self._invoke('announce', tool, arguments, request)

    def cancel(self):
        with self._condition:
            runtime = self._runtime
        if runtime is not None:
            runtime.cancel()

    def __getattr__(self, name):
        # Datos de la última generación solo se consultan después de invocar el
        # runtime. No provocar una carga por una lectura de telemetría.
        if name.startswith('last_') or name in ('repair_instruction',):
            with self._condition:
                runtime = self._runtime
            if runtime is not None and hasattr(runtime, name):
                return getattr(runtime, name)
        raise AttributeError(name)

    def _idle_worker(self):
        interval = min(1.0, max(0.05, self._idle_seconds / 10))
        while not self._stop.wait(interval):
            with self._condition:
                if (self._state != 'ready' or self._busy or
                        time.monotonic() - self._last_activity < self._idle_seconds):
                    continue
                runtime = self._runtime
                self._runtime = None
                self._state = 'unloading'
            error = None
            try:
                runtime.close()
            except Exception as exc:
                error = exc
            finally:
                with self._condition:
                    self._state = 'closed' if self._closed else ('error' if error else 'unloaded')
                    self._error = error
                    if error:
                        # Conserva el proceso si no se pudo confirmar su cierre.
                        self._runtime = runtime
                    if self._reload_requested and not self._closed:
                        self._reload_requested = False
                        if not error:
                            self._start_loading_locked()
                    self._condition.notify_all()

    def close(self):
        self._stop.set()
        with self._condition:
            self._closed = True
            runtime = self._runtime
            self._runtime = None
            self._state = 'closed'
            self._condition.notify_all()
        if runtime is not None:
            runtime.close()
