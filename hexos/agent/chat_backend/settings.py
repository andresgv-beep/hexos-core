"""Constantes del protocolo original."""
from __future__ import annotations

from .. import catalog


MAX_INPUT = 8 * 1024 * 1024
PROMPT = catalog.prompt()

MAX_IMAGE_SIDE = 1536

IMAGEN_SIN_TEXTO = 'Mira esta imagen y dime qué ves.'
AUDIO_SIN_TEXTO = 'Escucha mi mensaje de voz y responde a lo que te pido.'

# La traza original también cuenta la recuperación automática del historial.
# Con 6 se cortaban cadenas que iban bien: localizar, listar, preparar y
# corregir un intento ya las agota. Las iteraciones guardan el margen para
# la respuesta final y sus reintentos.
MAX_TRACE_EVENTS = 12
MAX_TURN_ITERATIONS = 16
