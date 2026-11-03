"""API pública estable y ensamblaje de los servicios del chat."""
from __future__ import annotations

from pathlib import Path
import threading
from uuid import uuid4
from ..native_transport import TurnCancelled
from .live import LiveGeneration
from ..work import WorkStore, now
from .access import CredentialService
from .completion import ReplyPolicy
from .context import ContextManager
from .memory import MemoryService
from .persistence import initialize
from .references import ReferenceResolver
from .state import AgentDependencies, Environment, SessionState
from .tools import ToolDispatcher
from .turn import TurnRunner
from .verification import VerificationService
from .. import catalog


class Agent:
    """Fachada compatible con el Agent original y raíz de composición.

    Los servicios no heredan de Agent. Cada uno recibe sus dependencias, y el
    TurnRunner coordina el mismo orden de operaciones del archivo original.
    """
    SECCIONES = ReferenceResolver.SECCIONES
    PRONOMBRE = ReferenceResolver.PRONOMBRE
    GENERICO = ReferenceResolver.GENERICO
    HECHO = ReplyPolicy.HECHO
    ESCRITURA_DICHA = ReplyPolicy.ESCRITURA_DICHA
    PROMESA = ReplyPolicy.PROMESA
    NEGACION = ReplyPolicy.NEGACION

    def __init__(self, workspace, runtime, profile=None, *, dependencies=None):
        self.env = Environment(Path(workspace), runtime, profile,
                               dependencies or AgentDependencies())
        self.session = SessionState()
        self.live_lock = threading.Lock()
        # La interfaz se ve a la vez en varias pantallas (monitor, móvil): dos pueden
        # aprobar el mismo plan casi a la vez. Solo una lo toma. No es self.lock, que
        # está ocupado durante todo un turno y no dejaría aprobar mientras Helios habla.
        self.system_lock = threading.Lock()
        self.live = None
        self.runtime_turn_acquired = False
        with self.store() as store:
            initialize(store)
        self.access = CredentialService(self.env, self.session, self.store)
        self.memory = MemoryService(self.env)
        self.references = ReferenceResolver(self.env)
        self.verification = VerificationService(self.env)
        self.dispatcher = ToolDispatcher(self.env, self.session, self.memory,
                                         self.references, self.verification)
        self.context = ContextManager(self)
        self.runner = TurnRunner(self)

    @property
    def workspace(self):
        return self.env.workspace

    @workspace.setter
    def workspace(self, value):
        self.env.workspace = value

    @property
    def runtime(self):
        return self.env.runtime

    @runtime.setter
    def runtime(self, value):
        self.env.runtime = value

    @property
    def profile(self):
        return self.env.profile

    @profile.setter
    def profile(self, value):
        self.env.profile = value

    @property
    def lock(self):
        return self.session.lock

    @lock.setter
    def lock(self, value):
        self.session.lock = value

    @property
    def state(self):
        return self.session.state

    @state.setter
    def state(self, value):
        self.session.state = value

    @property
    def progress(self):
        return self.session.progress

    @progress.setter
    def progress(self, value):
        self.session.progress = value

    @property
    def active_tools(self):
        return self.session.active_tools

    @active_tools.setter
    def active_tools(self, value):
        self.session.active_tools = value

    @property
    def credential_request(self):
        return self.session.credential_request

    @credential_request.setter
    def credential_request(self, value):
        self.session.credential_request = value

    @property
    def system_request(self):
        return self.session.system_request

    def decide_system(self, payload, *, apply=None):
        """La persona aprueba o rechaza el plan pendiente de system.package_plan.

        Es el único camino a la ejecución: viene de la interfaz, no de la conversación. Se
        ejecuta solo el plan que está pendiente, y una vez: se retira antes de lanzarlo.
        """
        from .. import system_packages
        if set(payload) != {'plan_id', 'approve'} or not isinstance(payload['approve'], bool):
            raise ValueError('se espera {"plan_id": "...", "approve": true|false}')
        with self.system_lock:
            pending = self.session.system_request
            if not pending or pending['plan_id'] != payload['plan_id']:
                raise ValueError('Ese plan ya no está pendiente: lo decidió otra pantalla o caducó')
            self.session.system_request = None
        if payload['approve']:
            result = (apply or system_packages.apply)(pending)
            estado = ('hecho y comprobado' if result['executed'] and result['verified'] else
                      'ejecutado, pero la comprobación no cuadra' if result['executed'] else
                      'no se ejecutó: ' + (result['refused'] or 'error del gestor'))
            note = ('[La persona aprobó en la interfaz: ' + pending['summary'] + '. HexOS lo ejecutó: ' +
                    estado + ' (' + result['check'] + ').]')
        else:
            result = dict(plan_id=pending['plan_id'], summary=pending['summary'], executed=False, cancelled=True)
            note = '[La persona rechazó en la interfaz: ' + pending['summary'] + '. No se ha cambiado nada.]'
        # Como al guardar un acceso: sin esta nota el modelo seguiría creyendo que espera aprobación.
        with self.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             (uuid4().hex, now(), 'user', note, note))
            store.db.commit()
        return dict(result, note=note)

    @property
    def context_cut(self):
        return self.session.context_cut

    @context_cut.setter
    def context_cut(self, value):
        self.session.context_cut = value

    def store(self):
        return WorkStore(self.workspace)

    def dismiss_access(self, device):
        return self.access.dismiss_access(device)

    def save_access(self, payload):
        return self.access.save_access(payload)

    def device_in_message(self, store, turn_id):
        return self.references.device_in_message(store, turn_id)

    def devices_named(self, store, turn_id):
        return self.references.devices_named(store, turn_id)

    def explicit_read(self, store, turn_id, text):
        return self.references.explicit_read(store, turn_id, text)

    def pointed_note(self, store, text, turn_id):
        return self.references.pointed_note(store, text, turn_id)

    def verify(self, store, name, args, result):
        return self.verification.verify(store, name, args, result)

    def pending_effect(self, store, device, target):
        return self.verification.pending_effect(store, device, target)

    def resolve_effect(self, store, device, target, state):
        return self.verification.resolve_effect(store, device, target, state)

    def remember_fact(self, store, args, turn_id):
        return self.memory.remember_fact(store, args, turn_id)

    def recall_history(self, store, text, turn_id):
        return self.memory.recall_history(store, text, turn_id)

    def harvest_facts(self, store, text, turn_id, trace=None):
        return self.memory.harvest_facts(store, text, turn_id, trace)

    def tool(self, store, name, args, *, turn_id=None):
        return self.dispatcher.dispatch(store, name, args, turn_id=turn_id)

    def chat(self, text, image=None, *, thinking=None, display_text=None, request_id=None):
        """Ejecuta un turno, con pensamiento opcional solo para ese encargo.

        La preferencia general sigue viviendo en ``runtime.thinking`` y en la
        base de datos. Una revisión de código puede abrir el canal durante este
        turno sin dejar cambiado el botón AUTO de la persona.
        """
        if thinking is None:
            return self.runner.run(text, image, display_text=display_text, request_id=request_id)
        if not isinstance(thinking, bool):
            raise ValueError('thinking debe ser true o false')
        if not hasattr(self.runtime, 'thinking'):
            raise ValueError('Este motor no tiene canal de pensamiento')
        previous = self.runtime.thinking
        self.runtime.thinking = thinking
        try:
            return self.runner.run(text, image, display_text=display_text, request_id=request_id)
        finally:
            self.runtime.thinking = previous

    def resume_access(self, text, operation):
        """Continúa exactamente la lectura que quedó esperando credenciales."""
        if not isinstance(operation, dict) or set(operation) != {'tool', 'arguments'}:
            raise ValueError('Operación pendiente de acceso inválida')
        return self.runner.run(text, initial_tool=operation)

    def begin_generation(self, request_id=None):
        with self.live_lock:
            self.live = LiveGeneration(request_id or uuid4().hex,
                                       bool(getattr(self.runtime, 'progressive', False)))
        try:
            if hasattr(self.runtime, 'acquire_turn'):
                self.live.update(dict(phase='loading'))
                self.runtime.acquire_turn(self.live.stop)
                self.runtime_turn_acquired = True
                self.check_cancelled()
                self.live.update(dict(phase='preparing'))
            if hasattr(self.runtime, 'begin_request'):
                self.runtime.begin_request(self.live.update)
        except Exception:
            if self.runtime_turn_acquired:
                self.runtime.release_turn()
                self.runtime_turn_acquired = False
            raise

    def generation_snapshot(self):
        with self.live_lock:
            return self.live.snapshot() if self.live else None

    def metrics_snapshot(self):
        with self.live_lock:
            snapshot = self.live.snapshot() if self.live else getattr(self, '_last_metrics', {})
        return dict(context_used=getattr(self.runtime, 'kv_position', None),
                    context_capacity=getattr(self.runtime, 'ctx', None),
                    tokens_per_second=snapshot.get('tokens_per_second'))

    def cancel_generation(self, request_id):
        with self.live_lock:
            if not self.live or self.live.request_id != request_id or not self.live.data['cancellable']:
                return dict(ok=False, request_id=request_id)
            self.live.stop.set()
            self.live.update(dict(cancelling=True))
            self.runtime.cancel()
            return dict(ok=True, request_id=request_id)

    def check_cancelled(self):
        if self.live and self.live.stop.is_set():
            raise TurnCancelled('Generación detenida')

    def end_generation(self):
        with self.live_lock:
            if hasattr(self.runtime, 'on_update'):
                self.runtime.on_update = None
            if self.live:
                self._last_metrics = self.live.snapshot()
            self.live = None
        if self.runtime_turn_acquired:
            self.runtime.release_turn()
            self.runtime_turn_acquired = False

    def history_budget(self):
        return self.context.history_budget()

    def window(self, store, turn_id, native, budget):
        return self.context.window(store, turn_id, native, budget)

    def clear_context(self):
        return self.context.clear_context()

    @classmethod
    def uncovered(cls, pedidos, trace, texto='', limit=6):
        return ReferenceResolver.uncovered(pedidos, trace, texto, limit)

    @classmethod
    def denied_success(cls, reply, trace):
        return ReplyPolicy.denied_success(reply, trace)

    @staticmethod
    def announced_without_call(reply, trace, limit=6):
        return ReplyPolicy.announced_without_call(reply, trace, limit)

    @classmethod
    def unfulfilled_promise(cls, reply, trace, limit=6):
        return ReplyPolicy.unfulfilled_promise(reply, trace, limit)

    @classmethod
    def unsupported_claim(cls, reply, trace):
        return ReplyPolicy.unsupported_claim(reply, trace)

    @staticmethod
    def closure(trace, reply=None):
        return VerificationService.closure(trace, reply)

    def thinking(self):
        """¿Está abierto el canal de pensamiento? None si el motor no lo admite."""
        if not hasattr(self.runtime, 'thinking'):
            return None
        return bool(self.runtime.thinking)

    def set_window(self, window):
        """La ventana de trabajo: «chat» o «agente».

        No es una preferencia de estilo: decide qué grupos de herramientas puede pedir
        el selector, así que en una charla el NAS y la terminal ni se nombran. Mecánico y
        elegido por la persona, que es lo que este tamaño de modelo necesita: con 50
        herramientas delante pierde el hilo, y el catálogo entero son 6.491 tokens en
        cada turno contra los 939 del núcleo.

        Se guarda en agent_state, como el canal de pensamiento: una preferencia de la
        persona no debe morir en un reinicio.
        """
        # El atributo se llama `ventana` y no `window` porque `window()` ya es el método
        # que recorta el historial: asignarle una cadena lo deja inservible y el turno
        # entero muere en `context.prepare`.
        if window not in catalog.WINDOWS:
            raise ValueError('ventana desconocida: ' + ', '.join(catalog.WINDOWS))
        # Cada ventana tiene su conversación y su contexto. A mitad de turno no se
        # cambia: el turno escribiría su respuesta en la conversación de la otra.
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('Ya hay un turno en curso')
        try:
            cambia = getattr(self, 'ventana', None) != window
            self.ventana = window
            self.runtime.ventana = window
            if getattr(self, 'grupos', None) is not None:
                # Lo que quedó vivo de la otra ventana no se arrastra.
                self.grupos.reset()
            with self.store() as store:
                store.db.execute("INSERT INTO agent_state VALUES ('window',?) "
                                 'ON CONFLICT(key) DO UPDATE SET value=excluded.value', (window,))
                store.db.commit()
            if cambia:
                # El modelo tiene delante la conversación de la otra ventana: se vacía,
                # y el turno siguiente la reconstruye desde el archivo de esta.
                self.runtime.call({'type': 'reset'})
                if hasattr(self.runtime, 'active_groups'):
                    self.runtime.active_groups = None
        finally:
            self.lock.release()
        return dict(window=window, persisted=True, groups=list(catalog.groups_in(window)))

    def restore_window(self):
        """La ventana guardada, o chat si no hay ninguna."""
        try:
            with self.store() as store:
                fila = store.db.execute("SELECT value FROM agent_state WHERE key='window'").fetchone()
        except Exception:
            fila = None
        guardada = fila[0] if fila and fila[0] in catalog.WINDOWS else catalog.DEFAULT_WINDOW
        self.ventana = guardada
        self.runtime.ventana = guardada
        return guardada

    def set_thinking(self, enabled):
        """El canal se decide por render, así que se puede cambiar en caliente.

        Se guarda en agent_state porque si no dependería de cómo se lanzó el
        proceso, y una preferencia de la persona no debe morir en un reinicio.
        """
        if not hasattr(self.runtime, 'thinking'):
            raise ValueError('Este motor no tiene canal de pensamiento; nada que encender')
        if not isinstance(enabled, bool):
            raise ValueError('enabled debe ser true o false')
        self.runtime.thinking = enabled
        with self.store() as store:
            store.db.execute("INSERT INTO agent_state VALUES ('thinking',?) "
                             'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                             ('1' if enabled else '0'))
            store.db.commit()
        return dict(thinking=enabled, persisted=True,
                    note='Con el canal abierto el modelo decide cuánto pensar: en charla normal '
                         'gasta cero. El coste solo aparece en los turnos que hacen trabajo.')

    def restore_thinking(self):
        """Preferencia guardada por encima del flag de arranque, si la hay."""
        if not hasattr(self.runtime, 'thinking'):
            return None
        with self.store() as store:
            fila = store.db.execute("SELECT value FROM agent_state WHERE key='thinking'").fetchone()
        if fila is not None:
            self.runtime.thinking = fila[0] == '1'
        return bool(self.runtime.thinking)
