"""Contrato de respuesta compartido por los adaptadores del chat."""
import re

from . import catalog


class InvalidDecision(ValueError):
    """Generación rechazada: no autoriza ejecución ni una respuesta final."""


def validate_reply(text):
    if not isinstance(text, str) or not text.strip():
        raise InvalidDecision('Respuesta vacía del modelo')
    # Solo llamadas aisladas a funciones conocidas. Explicar o citar código en
    # una respuesta legítima sigue permitido. Nunca convertir este texto en acción.
    candidate = text.strip().strip('`').strip()
    names = '|'.join(re.escape(n) for name in catalog.TOOLS
                     for n in (name, name.replace('.', '_')))
    if re.fullmatch(r'(?:' + names + r')\s*\([\s\S]*\)\s*;?', candidate):
        raise InvalidDecision('El modelo escribió una llamada como texto; no se ejecutó')
    return text
