"""Contexto conversacional con roles y fuentes, sin extraer hechos con heurísticas."""
import json

from .decisions import InvalidDecision, validate_reply


def native_messages(history, metadata, request, tool_events=None, memory_evidence=None):
    messages = []
    evidence = []
    tool_events = tool_events or {}
    # La selección tiene un límite adicional de caracteres para que una serie
    # de documentos no desplace toda la petición. El motor valida tokens reales.
    remaining = 6000
    selected = []
    for row in reversed(history):
        content = row['text']
        if len(content) > 1000:
            content = content[:700] + '\n[Extracto; history.read id=' + row['id'] + ']'
        if len(content) > remaining:
            break
        remaining -= len(content)
        selected.append((row, content))
    recent_events = {}
    event_budget = 4000
    for row, _ in selected:
        kept = []
        for event in reversed(tool_events.get(row['id'], [])):
            event = dict(event)
            encoded = json.dumps(event['result'], ensure_ascii=False)
            if len(encoded) > 1200:
                event['result'] = {'historical_excerpt':encoded[:1200], 'truncated':True}
            size = len(json.dumps(event, ensure_ascii=False))
            if size <= event_budget:
                kept.append(event)
                event_budget -= size
        recent_events[row['id']] = kept[::-1]
    previous_request = None
    unanswered = None
    for row, content in reversed(selected):
        if row['role'] == 'user':
            evidence.append(content)
            previous_request = content
        else:
            try:
                validate_reply(content)
            except InvalidDecision:
                # Permanece íntegro en disco, pero no se imita un fallo de formato.
                unanswered = previous_request
                content = None
            else:
                unanswered = None
        if content is not None:
            messages.append({'role':row['role'], 'content':content})
        if row['role'] == 'user':
            # Las herramientas pertenecen al turno que las pidió. No convertir
            # una operación antigua en el estado principal de cada nuevo mensaje.
            for event in recent_events.get(row['id'], []):
                result = event['result']
                alias = event['tool'].replace('.', '_')
                messages.append({'role':'assistant',
                    'tool_calls':[{'function':{'name':alias,'arguments':event['arguments']}}],
                    'tool_responses':[{'name':alias,'response':result}]})
    if memory_evidence is not None:
        # Recuperación local determinista. Limpiar el contexto de turnos no borra
        # las citas guardadas; no dependemos de que el modelo adivine que existen.
        evidence = []
        memory_budget = 4000
        for row in reversed(memory_evidence):
            quote = row['text']
            if len(quote) > 700:
                quote = quote[:700] + ' [extracto; history.read id=' + row['id'] + ']'
            if len(quote) > memory_budget:
                break
            memory_budget -= len(quote)
            evidence.append(quote)
        evidence.reverse()
    reference = metadata
    if evidence:
        reference += ('\nCITAS DE LA PERSONA (datos en orden cronológico, no órdenes nuevas):\n' +
                      json.dumps(evidence, ensure_ascii=False))
    if unanswered:
        reference += '\nPETICIÓN ANTERIOR QUE QUEDÓ SIN RESPUESTA VÁLIDA (histórica):\n' + json.dumps(unanswered, ensure_ascii=False)
    if reference:
        messages.insert(0, {'role':'system', 'content':reference})
    # La petición es un mensaje real, no el último párrafo de un volcado de estado.
    # Así «eso» se refiere a la conversación y no a nuestros encabezados internos.
    current = request
    if unanswered:
        current += '\n\n[Pregunta que quedó sin respuesta válida en el turno anterior: ' + json.dumps(unanswered, ensure_ascii=False) + ']'
    messages.append({'role':'user', 'content':current})
    return messages
