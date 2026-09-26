"""Constantes del protocolo original. No cambian sus límites."""
from __future__ import annotations

from .. import catalog


MAX_INPUT = 8 * 1024 * 1024
PROMPT = catalog.prompt()

MAX_IMAGE_SIDE = 1536

IMAGEN_SIN_TEXTO = 'Mira esta imagen y dime qué ves.'
AUDIO_SIN_TEXTO = 'Escucha mi mensaje de voz y responde a lo que te pido.'

# La traza original también cuenta la recuperación automática del historial.
MAX_TRACE_EVENTS = 6
MAX_TURN_ITERATIONS = 10
