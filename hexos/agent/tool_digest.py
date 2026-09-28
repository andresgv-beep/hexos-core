"""Resultados de herramientas que no se arrastran turno tras turno.

Un resultado crudo que ya se usó para contestar ocupaba contexto en cada turno
siguiente (un SMART son 2.800 tokens) y además invitaba al modelo a contestar
con datos de hace diez minutos en vez de volver a consultar. Regla única para la
conversación viva del adaptador y para la reconstrucción desde el archivo:

- Los resultados pequeños se quedan: identificadores y confirmaciones que un
  turno posterior puede necesitar («márcala como hecha»).
- El último grupo de llamadas se queda entero mientras sea reciente, para las
  preguntas encadenadas («¿y los números de serie?»).
- El resto se sustituye por un aviso con la hora de la consulta y qué hacer si
  vuelve a hacer falta. El dato completo sigue en tool_events.
"""
from datetime import datetime
import json
import time

KEEP_CHARS = 400
FRESH_SECONDS = 300
_MARK = 'resultado_anterior'


def _clock(ts):
    return datetime.fromtimestamp(ts).strftime('%H:%M')


def stub(tool, effect, ts, now):
    """Aviso que sustituye a un resultado antiguo. `tool` es el alias nativo."""
    minutes = max(0, int((now - ts) // 60)) if ts else None
    when = ('consultado a las ' + _clock(ts) + ' (hace ' + str(minutes) + ' min)') if ts else 'de un turno anterior'
    if effect == 'read':
        note = ('Ya se usó para contestar en su momento y no sigue en contexto. No es el estado '
                'actual: si vuelve a hacer falta, llama otra vez a ' + tool + ', que es una lectura.')
    else:
        note = ('El efecto quedó registrado y ya se informó. El detalle completo está en el historial '
                '(history_read); no repitas la acción para recuperarlo.')
    return {_MARK: when, 'nota': note}


def is_stub(response):
    return isinstance(response, dict) and _MARK in response


def _small(response):
    return len(json.dumps(response, ensure_ascii=False)) <= KEEP_CHARS


def compact_live(messages, names, effects, now=None):
    """Resume en sitio los resultados antiguos de la conversación viva.

    `names` traduce alias nativo -> nombre del catálogo y `effects` nombre -> efecto.
    Devuelve cuántos resultados se han resumido.
    """
    now = time.time() if now is None else now
    tool_indices = [i for i, m in enumerate(messages) if m.get('tool_responses')]
    if not tool_indices:
        return 0
    # Último grupo: las llamadas posteriores al último mensaje de la persona que las precede.
    last = tool_indices[-1]
    start = max((i for i in range(last) if messages[i].get('role') == 'user'), default=-1)
    newest = [r.get('ts') for i in tool_indices if i > start for r in messages[i]['tool_responses']]
    # Sin hora conocida no se da por caducado: se conserva como hasta ahora.
    fresh = all(ts is None or now - ts <= FRESH_SECONDS for ts in newest)
    changed = 0
    for i in tool_indices:
        if i > start and fresh:
            continue
        for response in messages[i]['tool_responses']:
            body = response.get('response')
            if is_stub(body) or _small(body):
                continue
            alias = response.get('name', 'herramienta')
            effect = effects.get(names.get(alias, alias.replace('_', '.', 1)), 'read')
            response['response'] = stub(alias, effect, response.get('ts'), now)
            changed += 1
    return changed


def compact_archived(event, newest_group, effects, now=None):
    """Versión para eventos de tool_events al reconstruir desde el archivo."""
    now = time.time() if now is None else now
    result = event.get('result')
    ts = epoch(event.get('ts'))
    if _small(result) or (newest_group and (ts is None or now - ts <= FRESH_SECONDS)):
        return event
    event = dict(event)
    event['result'] = stub(event['tool'].replace('.', '_'), effects.get(event['tool'], 'read'), ts, now)
    return event


def epoch(ts):
    """ts de tool_events (ISO) o epoch -> epoch; None si no se entiende."""
    if isinstance(ts, (int, float)):
        return ts
    try:
        return datetime.fromisoformat(ts).timestamp()
    except (TypeError, ValueError):
        return None
