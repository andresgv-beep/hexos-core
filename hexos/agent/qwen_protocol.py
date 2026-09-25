"""Qwen chat serialization; executors and authorization remain in Agent."""
import json


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
    text = text.strip()
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
