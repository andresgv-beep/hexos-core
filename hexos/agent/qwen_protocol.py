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
