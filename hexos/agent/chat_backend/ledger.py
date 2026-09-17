"""Checkpoint mecánico de las operaciones ejecutadas dentro de un turno."""
from __future__ import annotations

import json


PREFERRED_RESULT_KEYS = (
    'headline', 'primary_suspect', 'facts', 'target', 'observed_at', 'section',
    'container_state', 'outcome', 'verification', 'counts', 'identified_devices',
    'devices', 'diagnostic_limits', 'storage', 'kernel', 'smart', 'note', 'error',
)


def _size(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')))


def compact(value, limit=4000):
    """Vista acotada para el modelo; la traza conserva el resultado completo.

    Un resultado grande fue precisamente lo que llenó el contexto. El checkpoint
    no puede reinyectarlo entero, pero tampoco puede limitarse a decir «se hizo»:
    conserva primero los campos que explican el resultado y marca cualquier corte.
    """
    if _size(value) <= limit:
        return value
    if isinstance(value, str):
        return value[:max(0, limit - 80)] + '… [recortado en checkpoint]'
    if isinstance(value, list):
        out = []
        for item in value:
            candidate = out + [compact(item, max(240, limit // 3))]
            if _size(candidate) > limit - 100:
                break
            out = candidate
        return {'items': out, 'total': len(value), 'checkpoint_truncated': len(out) < len(value)}
    if not isinstance(value, dict):
        return value

    ordered = [key for key in PREFERRED_RESULT_KEYS if key in value]
    ordered += [key for key in value if key not in ordered]
    out = {}
    for key in ordered:
        candidate_value = compact(value[key], max(300, min(1200, limit // 3)))
        candidate = dict(out, **{key: candidate_value})
        if _size(candidate) > limit - 140:
            continue
        out[key] = candidate_value
    out['checkpoint_truncated'] = True
    out['checkpoint_note'] = ('Vista acotada del resultado ya obtenido; el original completo '
                              'sigue en la traza local del turno.')
    return out


def checkpoint_messages(trace, budget=6500):
    """Reconstruye llamadas y resultados como mensajes nativos, no como prosa."""
    messages = []
    remaining = budget
    for index, step in enumerate(trace):
        left = max(1, len(trace) - index)
        result = compact(step.get('result'), max(500, min(4000, remaining // left)))
        alias = step['tool'].replace('.', '_')
        message = {
            'role': 'assistant',
            'tool_calls': [{'function': {'name': alias, 'arguments': step.get('arguments', {})}}],
            'tool_responses': [{'name': alias, 'response': result}],
        }
        size = _size(message)
        if size > remaining:
            result = {
                'checkpoint_result': 'registrado',
                'failed': bool(step.get('failed')),
                'verification': step.get('verification'),
                'note': 'El resultado completo sigue en la traza local del turno.',
            }
            message['tool_responses'][0]['response'] = result
            size = _size(message)
        messages.append(message)
        remaining = max(0, remaining - size)
    return messages


def completed_call(turn, name, arguments):
    """Llamada del checkpoint cuyo efecto ya consta, si se puede reutilizar."""
    limit = min(turn.checkpointed_steps, len(turn.trace))
    for index in range(limit - 1, -1, -1):
        step = turn.trace[index]
        if step.get('tool') != name or step.get('arguments') != arguments:
            continue
        result = step.get('result')
        if step.get('failed') or (isinstance(result, dict) and 'error' in result):
            continue
        # Una lectura anterior a una escritura posterior puede haber quedado
        # obsoleta. Las escrituras, en cambio, jamás se repiten a ciegas.
        if not step.get('changes_state'):
            changed_after = any(
                later.get('changes_state') and not later.get('failed')
                for later in turn.trace[index + 1:]
            )
            if changed_after:
                return None
        return step
    return None


def completed_registration(turn, name, arguments):
    """Registro equivalente ya completado aunque el modelo cambie de herramienta.

    Tras device.remote, device.identify no añade nada: la dirección remota ya
    creó o actualizó esa misma ficha. Ejecutarlo convierte un éxito en un error
    porque identify solo acepta vecinos locales.
    """
    if name != 'device.identify':
        return None
    wanted = (arguments.get('name') or '').casefold()
    if not wanted:
        return None
    for step in reversed(turn.trace):
        result = step.get('result')
        if (step.get('tool') == 'device.remote' and not step.get('failed') and
                isinstance(result, dict) and result.get('saved') and
                (result.get('device') or '').casefold() == wanted):
            return step
    return None
