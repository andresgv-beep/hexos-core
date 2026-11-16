"""Qwen chat serialization; executors and authorization remain in Agent."""
import json
import re


def render_messages(messages):
    result = []
    for message in messages:
        item = dict(message)
        responses = item.pop('tool_responses', [])
        item.setdefault('content', '')
        if 'reasoning' in item:
            item['reasoning_content'] = item.pop('reasoning')
        result.append(item)
        for response in responses:
            result.append(dict(role='tool', name=response['name'],
                               content=json.dumps(response['response'], ensure_ascii=False)))
    return result


def split_thought(text, open_thought=False):
    text = ('<think>' if open_thought else '') + text
    text = text.lstrip()
    if not text.startswith('<think>'):
        return text, None
    end = text.find('</think>')
    if end < 0:
        raise ValueError('pensamiento Qwen incompleto')
    return text[end + len('</think>'):].lstrip(), text[len('<think>'):end]


PRODUCT = re.compile(r'\d+(?:\s*\*\s*\d+)+')


def fold_products(text):
    """Resolver «20 * 1024 * 1024 * 1024» fuera de las cadenas.

    Qwen escribe los tamaños como cuentas y el JSON las rechaza: el reintento
    repetía la misma cuenta y el turno moría con «Expecting ',' delimiter». En
    JSON válido no hay asteriscos fuera de cadenas, así que esto no cambia
    ninguna llamada correcta. Solo productos de enteros, nada de evaluar código.
    """
    out, i, inside = [], 0, False
    while i < len(text):
        char = text[i]
        if inside:
            out.append(char)
            if char == '\\':
                out.append(text[i+1:i+2]); i += 1
            elif char == '"':
                inside = False
            i += 1
            continue
        if char == '"':
            inside = True
        else:
            match = PRODUCT.match(text, i)
            if match and '*' in match.group() and (i == 0 or not text[i-1].isalnum()):
                value = 1
                for factor in match.group().split('*'):
                    value *= int(factor)
                if value < 2**63:
                    out.append(str(value)); i = match.end()
                    continue
        out.append(char); i += 1
    return ''.join(out)


def calls(text):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError('clave duplicada')
            obj[key] = value
        return obj
    decoder = json.JSONDecoder(object_pairs_hook=unique,
                               parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    result = []
    text = fold_products(text.strip())
    while text:
        if not text.startswith('<tool_call>') or len(result) >= 6:
            raise ValueError('llamada Qwen inválida')
        body = text[len('<tool_call>'):].lstrip()
        value, end = decoder.raw_decode(body)
        tail = body[end:].lstrip()
        if not tail.startswith('</tool_call>'):
            raise ValueError('llamada Qwen incompleta')
        if (not isinstance(value, dict) or set(value) != {'name', 'arguments'}
                or not isinstance(value['name'], str) or not isinstance(value['arguments'], dict)):
            raise ValueError('nombre o argumentos Qwen inválidos')
        result.append(value)
        text = tail[len('</tool_call>'):].strip()
    return result


# --- Qwen3-Coder: llamadas con etiquetas, no JSON ---------------------------------------
#
#   <tool_call>
#   <function=nombre>
#   <parameter=ruta>
#   valor, que puede ocupar varias líneas
#   </parameter>
#   </function>
#   </tool_call>
#
# El valor va en crudo: un fichero de código entero viaja sin escapar comillas ni saltos de
# línea. A cambio no dice de qué tipo es, así que el tipo lo pone el catálogo.

MAX_LLAMADAS = 6
ABRE_FUNCION = re.compile(r'<function=([A-Za-z_][\w.-]*)>')
ABRE_PARAMETRO = re.compile(r'<parameter=([A-Za-z_]\w*)>')
# El cierre de un valor es el `</parameter>` al que sigue otro parámetro o el fin de la
# función. Así un `</parameter>` escrito dentro del valor (código que habla de este mismo
# formato) no lo corta.
CIERRA_PARAMETRO = re.compile(r'</parameter>\s*(?=<parameter=|</function>)')


def _valor(crudo, tipo, nombre):
    """El texto de un parámetro, convertido al tipo que declara el catálogo."""
    # La plantilla pone un salto de línea tras abrir y otro antes de cerrar: son del formato.
    texto = crudo[1:] if crudo.startswith('\n') else crudo
    texto = texto[:-1] if texto.endswith('\n') else texto
    if tipo in (None, 'str'):
        return texto
    limpio = texto.strip()
    if tipo == 'int':
        if not re.fullmatch(r'-?\d+', limpio):
            raise ValueError(nombre + ': se esperaba un número entero')
        return int(limpio)
    if tipo == 'bool':
        if limpio.lower() not in ('true', 'false'):
            raise ValueError(nombre + ': se esperaba true o false')
        return limpio.lower() == 'true'
    if tipo == 'list':
        try:
            valor = json.loads(limpio)
        except ValueError:
            # Una lista escrita a mano, un elemento por línea, también vale.
            valor = [linea.strip() for linea in limpio.splitlines() if linea.strip()]
        if not isinstance(valor, list):
            raise ValueError(nombre + ': se esperaba una lista')
        return valor
    raise ValueError(nombre + ': tipo de argumento desconocido en el catálogo')


def calls_xml(text, tipos=None):
    """Las llamadas de un texto en el formato de Qwen3-Coder.

    `tipos(nombre)` devuelve {parámetro: 'str'|'int'|'bool'|'list'} para una herramienta, o
    None si no la conoce; sin él todo son textos. Rechaza texto suelto entre llamadas,
    parámetros repetidos y bloques sin cerrar, igual que el analizador de JSON.
    """
    result = []
    text = text.strip()
    while text:
        if not text.startswith('<tool_call>') or len(result) >= MAX_LLAMADAS:
            raise ValueError('llamada Qwen inválida')
        fin = text.find('</tool_call>')
        # El cierre bueno es el que sigue a `</function>`: un valor puede contener el otro.
        cierre = re.search(r'</function>\s*</tool_call>', text)
        if not cierre or fin < 0:
            raise ValueError('llamada Qwen incompleta')
        cuerpo = text[len('<tool_call>'):cierre.start()].strip()
        funcion = ABRE_FUNCION.match(cuerpo)
        if not funcion:
            raise ValueError('llamada Qwen sin <function=nombre>')
        nombre = funcion.group(1)
        clases = (tipos(nombre) if tipos else None) or {}
        resto = cuerpo[funcion.end():].lstrip('\n') + '</function>'
        argumentos = {}
        while not resto.startswith('</function>'):
            abre = ABRE_PARAMETRO.match(resto)
            if not abre:
                raise ValueError('texto inesperado entre los parámetros de ' + nombre)
            clave = abre.group(1)
            if clave in argumentos:
                raise ValueError('clave duplicada')
            cierra = CIERRA_PARAMETRO.search(resto, abre.end())
            if not cierra:
                raise ValueError('parámetro ' + clave + ' sin cerrar')
            argumentos[clave] = _valor(resto[abre.end():cierra.start()], clases.get(clave), nombre + '.' + clave)
            resto = resto[cierra.end():]
        result.append(dict(name=nombre, arguments=argumentos))
        text = text[cierre.end():].strip()
    return result
