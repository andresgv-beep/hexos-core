"""API pública estable y ensamblaje de los servicios del chat."""
from __future__ import annotations

from pathlib import Path
from ..work import WorkStore
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

    def chat(self, text, image=None, *, thinking=None):
        """Ejecuta un turno, con pensamiento opcional solo para ese encargo.

        La preferencia general sigue viviendo en ``runtime.thinking`` y en la
        base de datos. Una revisión de código puede abrir el canal durante este
        turno sin dejar cambiado el botón AUTO de la persona.
        """
        if thinking is None:
            return self.runner.run(text, image)
        if not isinstance(thinking, bool):
            raise ValueError('thinking debe ser true o false')
        if not hasattr(self.runtime, 'thinking'):
            raise ValueError('Este motor no tiene canal de pensamiento')
        previous = self.runtime.thinking
        self.runtime.thinking = thinking
        try:
            return self.runner.run(text, image)
        finally:
            self.runtime.thinking = previous

    def resume_access(self, text, operation):
        """Continúa exactamente la lectura que quedó esperando credenciales."""
        if not isinstance(operation, dict) or set(operation) != {'tool', 'arguments'}:
            raise ValueError('Operación pendiente de acceso inválida')
        return self.runner.run(text, initial_tool=operation)

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
