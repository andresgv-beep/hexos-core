"""Entrada compatible del chat Helios/HexOS.

La implementación vive en chat_backend. Se mantiene el módulo de lanzamiento y
los nombres propios exportados por la versión original.
"""
import argparse
import base64
import binascii
import hashlib
import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4

from .work import KINDS, WorkStore, now, strict_json, string, strings
from . import procedures, catalog, workflow, devices, hosts, notes, core
from .continuity import HeraProfile, history_tool
from .decisions import InvalidDecision, validate_reply
from .context import native_messages
from .network import snapshot as network_snapshot
from .nas_session import read as nas_read
from .progress import announcement
from .telemetry import SystemTelemetry

from .chat_backend.agent import Agent as BackendAgent
from .chat_backend.bootstrap import main
from .chat_backend.runtime import Runtime
from .chat_backend.images import decode_image
from .chat_backend.settings import MAX_INPUT, MAX_IMAGE_SIDE, PROMPT, IMAGEN_SIN_TEXTO
from .chat_backend.memory import (
    AFIRMACION, RECUERDO, PALABRAS_VACIAS, sin_tildes, recall_terms, frase_del_hecho,
)
from .chat_backend.references import PEDIR_VER, PEDIR_CERRAR, NOTA_MENCIONADA
from .chat_backend.completion import FUGA_AVISO


def _compat_nas_read(workspace, **kwargs):
    """Puente temporal para los consumidores del módulo público histórico.

    `Agent` sigue siendo la puerta pública mientras la migración vive en este
    worktree. La función mira `nas_read` en el momento de usarla, por lo que un
    adaptador o una prueba puede sustituir el transporte sin que el backend tenga
    que conocer el módulo de entrada.
    """
    return nas_read(workspace, **kwargs)


class Agent(BackendAgent):
    """Fachada pública compatible que inyecta los bordes del proceso actual."""
    def __init__(self, workspace, runtime, profile=None, *, dependencies=None):
        if dependencies is None:
            from .chat_backend.state import AgentDependencies
            dependencies = AgentDependencies(nas_read=_compat_nas_read)
        super().__init__(workspace, runtime, profile, dependencies=dependencies)


if __name__ == '__main__':
    main()
