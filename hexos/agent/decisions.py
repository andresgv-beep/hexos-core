"""Contrato de respuesta compartido por los adaptadores del chat."""
import re

from . import catalog


class InvalidDecision(ValueError):
    """Generación rechazada: no autoriza ejecución ni una respuesta final.

    `repair` es la instrucción concreta para el reintento: decirle «formato
    inválido» cuando lo que pasa es que se dejó la lista sin escribir no le
    ayuda a arreglarlo.
    """

    def __init__(self, message, repair=None):
        super().__init__(message)
        self.repair = repair


# «Te muestro las 16 direcciones» y punto: el turno se cierra habiendo prometido
# una enumeración que no está. Se exige el anuncio Y la cantidad o la palabra
# lista, para no rechazar un «aquí tienes el diagnóstico» que es prosa legítima.
ANUNCIO = re.compile(
    r'\b(aqu[ií] (?:tienes|van|est[aá]n?|te dejo|te los dejo)'
    r'|te (?:muestro|enumero|listo|paso|dejo)|a continuaci[oó]n'
    r'|estos son|estas son|esta es la lista|te la muestro|te las muestro)\b', re.I)
CANTIDAD = re.compile(r'\b(l[oa]s \d+|\d+ (?:vecinos|dispositivos|direcciones|ips?|equipos|elementos)'
                      r'|lista|listado)\b', re.I)
ELEMENTO = re.compile(r'^\s*(?:[-*•]\s+\S|\d+[.)]\s+\S|\|)', re.M)


def _enumera_en_linea(text):
    """«…: minecraft-java, projectzomboid y n8n» es una lista entregada, no una
    promesa. Vale con tres elementos tras los dos puntos."""
    for cola in text.split(':')[1:]:
        cola = cola.split('\n')[0]
        piezas = [p.strip() for p in re.split(r',|\s+y\s+', cola) if p.strip()]
        if len(piezas) >= 3:
            return True
    return False


def promete_sin_entregar(text):
    """¿Anuncia una enumeración y no escribe ninguna, ni en lista ni en línea?"""
    return bool(ANUNCIO.search(text) and CANTIDAD.search(text)
                and len(ELEMENTO.findall(text)) < 2 and not _enumera_en_linea(text))


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
    if promete_sin_entregar(text):
        raise InvalidDecision(
            'El modelo anunció una enumeración y no la escribió',
            repair='Has anunciado una lista y no la has escrito. Escríbela entera ahora, '
                   'un elemento por línea, con todos los datos que pidieron. Si no tienes '
                   'los datos en contexto, vuelve a llamar a la herramienta de lectura '
                   'antes de responder. No vuelvas a anunciarla: escríbela.')
    return text
