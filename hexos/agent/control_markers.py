"""Marcadores de control del protocolo dentro de texto que no es protocolo.

El tokenizador del motor busca los tokens añadidos en TODO el prompt: un
«<|tool_call>» pegado por la persona, leído en una página o devuelto por una
herramienta llegaba al modelo como el token de control de verdad. El 07/11 la
persona pegó el parser de una auditoría y el 26B vio llamadas y canales dentro
de un turno de usuario; al explicarlo los citó y HEXOS tomó la cita por una
llamada: dos turnos perdidos («valor inválido», «texto fuera de llamada»).

Un WORD JOINER (U+2060) dentro del marcador lo deja igual a la vista pero ya no
coincide con el token. Se pone al montar el prompt, nunca en lo guardado, y se
quita de lo que escribe el modelo antes de enseñarlo o guardarlo.
"""
import re

UNION = '⁠'

# Los de Gemma 4 llevan barra en un extremo o en los dos; los de Qwen y los de
# servicio de Gemma, no. Solo estos últimos se nombran: neutralizar cualquier
# «<algo>» tocaría el HTML y el JSX que HEXOS edita. La unión va siempre tras el
# «<», así ni «<|tool_» ni «<tool_call» aparecen en lo neutralizado.
_MARCADOR = re.compile(r'<(?=\||[A-Za-z_"]+\|>|/?(?:tool_call|tool_response|think)>|'
                       r'(?:bos|eos|pad|unk|mask)>)')


def neutral(text):
    """El texto tal cual, sin nada que el tokenizador pueda leer como control."""
    if not isinstance(text, str) or '<' not in text:
        return text
    return _MARCADOR.sub('<' + UNION, text)


def neutral_messages(messages):
    """Copia de los mensajes con todas sus cadenas neutralizadas."""
    def walk(value):
        if isinstance(value, str):
            return neutral(value)
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value
    return [walk(m) for m in messages]


def restore(text):
    """Quita las uniones que puso neutral(): lo que ve y copia la persona queda limpio."""
    if not isinstance(text, str) or UNION not in text:
        return text
    return text.replace('<' + UNION, '<')


# Bloque ``` desde el principio de línea hasta su cierre, o código en línea
# hasta su cierre, el fin de línea o el final (la salida puede estar a medias).
_CODIGO = re.compile(r'^(`{3,}).*?(?:^\1|\Z)|(`+).*?(?:\2|\n|\Z)', re.S | re.M)


_LLAMADA = re.compile(r'<\|tool_call>|<tool_call>')


def quoted(text):
    """Neutraliza los marcadores que el modelo escribe dentro de código markdown.

    Una llamada de verdad nunca va entre comillas invertidas; una cita, sí. Lo
    que queda fuera del código se sigue validando como protocolo. Desde la
    primera llamada sin citar ya no se toca nada: sus argumentos pueden llevar
    comillas invertidas (JSX, shell) y son datos del parser, no markdown.
    """
    if '`' not in text:
        return text
    out, pos = [], 0
    for m in _CODIGO.finditer(text):
        if _LLAMADA.search(text, pos, m.start()):
            break
        out += [text[pos:m.start()], neutral(m[0])]
        pos = m.end()
    out.append(text[pos:])
    return ''.join(out)
