"""Estado de sesión y de turno explícito, sin persistencia ni decisiones."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import threading
from typing import Any, Callable


def default_nas_read(workspace, **kwargs):
    """Lectura NAS de producción, resuelta tarde para no congelar sustituciones.

    El backend depende de la capacidad (leer un NAS), no de un módulo concreto.
    La importación tardía conserva además un punto de sustitución limpio para las
    pruebas y para futuros adaptadores de transporte.
    """
    from ..nas_session import read
    return read(workspace, **kwargs)


def default_web_search(query, limit=5):
    from ..web import search
    return search(query, limit=limit)


def default_nas_files(workspace, *, operation, **kwargs):
    from .. import nas_files
    return {'browse': nas_files.browse, 'index': nas_files.index,
            'search': nas_files.search, 'find': nas_files.find,
            'locations': nas_files.locations, 'directories': nas_files.directories,
            'shares': nas_files.shares, 'directory_page': nas_files.directory_page,
            'file_open': nas_files.file_open, 'file_read': nas_files.file_read}[operation](workspace, **kwargs)


def default_web_read(url):
    from ..web import read
    return read(url)


@dataclass(frozen=True)
class AgentDependencies:
    """Capacidades externas que el núcleo del agente recibe desde fuera.

    Aquí entran los bordes que hacen E/S. El resto de servicios solo recibe el
    entorno y no importa ni parchea transportes por su cuenta.
    """
    nas_read: Callable[..., Any] = default_nas_read
    web_search: Callable[..., Any] = default_web_search
    web_read: Callable[..., Any] = default_web_read
    nas_files: Callable[..., Any] = default_nas_files


@dataclass
class Environment:
    workspace: Path
    runtime: Any
    profile: Any = None
    dependencies: AgentDependencies = field(default_factory=AgentDependencies)


@dataclass
class SessionState:
    lock: Any = field(default_factory=threading.Lock)
    state: str = 'idle'
    progress: dict = field(default_factory=lambda: {'turn_id': None, 'messages': []})
    active_tools: list = field(default_factory=list)
    credential_request: dict | None = None
    context_cut: dict | None = None
    # Última lectura de red: sirve para nombrar «la que termina en 129» sin
    # convertir cada vecino observado en inventario persistente.
    network_observation: dict | None = None


@dataclass
class RetryState:
    schema_retries: int = 0
    recovery_requests: int = 0
    said_retries: int = 0
    coverage_retries: int = 0
    coverage_mark: int = -1
    context_retries: int = 0
    format_retries: int = 0
    web_evidence_retries: int = 0
    web_read_guided: bool = False


@dataclass
class TurnState:
    text: str
    image: Any = None
    # Puede contener contexto de trabajo que el modelo necesita, mientras
    # ``text`` conserva exactamente lo que la persona escribió y verá luego.
    model_request: str = ''
    uid: str = ''
    document: dict | None = None
    prompt_text: str = ''
    pointed_note: dict | None = None
    listing_followup: bool = False
    reading_started: float | None = None
    document_read_mark: tuple | None = None
    document_read_retries: int = 0
    document_read_corrected: bool = False
    native: bool = False
    budget: int = 0
    boundary: int = 0
    history: list = field(default_factory=list)
    messages: list = field(default_factory=list)
    metadata: str = ''
    memory_evidence: list = field(default_factory=list)
    context_sources: list = field(default_factory=list)
    trace: list = field(default_factory=list)
    # Número de pasos que ya estaban terminados cuando hubo que reconstruir el
    # contexto a mitad del turno. Es la frontera que impide ejecutarlos otra vez.
    checkpointed_steps: int = 0
    checkpoint_reuses: int = 0
    previous_reply: str | None = None
    # Traspaso persistente creado al cortar el contexto. No es una memoria del
    # modelo ni una deducción: son citas recientes y el estado operativo que ya
    # estaba en disco, para que el siguiente bloque no empiece desorientado.
    handoff: dict | None = None
    retries: RetryState = field(default_factory=RetryState)
