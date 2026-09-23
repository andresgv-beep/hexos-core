"""Cobertura de texto entregado al agente y comprobación acotada del cierre.

La evidencia procede de tool_events, nunca del visor ni de afirmaciones del LLM.
Cada file_id identifica una copia inmutable. Cobertura no implica comprensión ni
que todos los fragmentos sigan presentes en la ventana de contexto.
"""
import json
import re

from .reading_budget import exhausted


def coverage(total, intervals):
    merged = []
    for start, end in sorted((max(0, a), min(total, b)) for a, b in intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    covered = sum(b - a for a, b in merged)
    first = merged[0][1] if merged and merged[0][0] == 0 else 0
    return dict(read_characters=covered, total_characters=total,
                offset_unit='unicode_code_points', covered_ranges=merged,
                remaining_characters=total-covered,
                percent=round(100*covered/total, 1) if total else 100.0,
                document_complete=covered == total,
                continue_from=None if covered == total else first)


def read_events(store, file_id=None):
    # Extraer solo metadatos evita cargar de nuevo el texto de todos los documentos.
    query = """SELECT json_extract(body,'$.result.file_id'),
        json_extract(body,'$.result.name'), json_extract(body,'$.result.offset'),
        length(json_extract(body,'$.result.text')),
        json_extract(body,'$.result.total_characters') FROM tool_events
        WHERE json_extract(body,'$.tool')='nas.file_read'
        AND coalesce(json_extract(body,'$.failed'),0)=0
        AND coalesce(json_extract(body,'$.delivered_to_model'),1)=1
        AND json_extract(body,'$.result.error') IS NULL"""
    args = ()
    if file_id is not None:
        query += " AND json_extract(body,'$.result.file_id')=?"
        args = (file_id,)
    query += ' ORDER BY rowid'
    return [tuple(row) for row in store.db.execute(query, args)
            if isinstance(row[0], str) and all(isinstance(row[i], int) for i in (2, 3, 4))]


def progress(store, file_id, result=None):
    rows = read_events(store, file_id)
    if result is not None:
        rows.append((file_id, result['name'], result['offset'], len(result['text']), result['total_characters']))
    if not rows:
        return None
    _, name, _, _, total = rows[-1]
    return dict(file_id=file_id, name=name,
                **coverage(total, [(r[2], r[2]+r[3]) for r in rows]))


def enrich(store, tool, result):
    if tool == 'nas.file_read' and isinstance(result, dict) and 'error' not in result:
        result = dict(result, reading_progress=progress(store, result['file_id'], result))
        result['note'] = (result.get('note', '') + ' reading_progress cuenta caracteres únicos entregados al modelo. '
            'Solo document_complete=true acredita cobertura completa. Si es false, sigue desde continue_from '
            'para cubrir huecos; no afirmes haber leído todo ni resumas secciones no entregadas.')
    return result


# Alcance deliberado: lectura completa explícita o confirmación de haberla acabado.
# No clasifica semánticamente cualquier paráfrasis posible del lenguaje natural.
FULL = re.compile(r'\b(?:le[eé](?:r|lo|la)?|le[ií]do|lectura|documento|archivo)\b.{0,90}'
                  r'\b(?:todo|entero|complet[oa](?:mente)?|[ií]ntegro)\b', re.I | re.S)
CLAIM = re.compile(r'\b(?:he|hemos)\s+(?:ya\s+)?(?:le[ií]do|terminado|completado)\b.{0,90}'
                   r'\b(?:todo|entero|complet[oa](?:mente)?|lectura|documento)\b', re.I | re.S)
CONFIRM = re.compile(r'\b(?:lo|la)\s+has\s+le[ií]do\s+(?:todo|entero|completo)\b', re.I)


def status(p):
    return (f"«{p['name']}»: lectura registrada {p['read_characters']:,} / "
            f"{p['total_characters']:,} caracteres ({p['percent']} %). "
            f"Pendientes: {p['remaining_characters']:,}. Documento completo: "
            + ('SÍ.' if p['document_complete'] else f"NO. Continuar desde: {p['continue_from']}."))


def check_completion(store, turn, output):
    """Devuelve True para un reintento; al agotarlo sustituye el cierre falso."""
    ids = list(dict.fromkeys(s['result']['file_id'] for s in turn.trace
        if s.get('tool') == 'nas.file_read' and not s.get('failed')
        and isinstance(s.get('result'), dict) and s['result'].get('file_id') and 'error' not in s['result']))
    requested = bool(FULL.search(turn.text))
    claimed = bool(CLAIM.search(output['reply']))
    if not ids and CONFIRM.search(turn.text):
        rows = read_events(store)
        if rows:
            ids = [rows[-1][0]]
    states = [p for identifier in ids if (p := progress(store, identifier))]
    pending = [p for p in states if not p['document_complete']]
    if pending:
        mark = tuple((p['file_id'], p['read_characters']) for p in pending)
        if ((requested or claimed) and not exhausted(turn, 'nas.file_read') and turn.document_read_mark != mark
                and turn.document_read_retries < 48):
            turn.document_read_mark = mark
            turn.document_read_retries += 1
            turn.messages = [dict(role='user', content='COMPROBACIÓN DE LECTURA (registro del backend):\n'
                + json.dumps(pending, ensure_ascii=False) + '\nLa lectura completa sigue pendiente. '
                'Continúa con nas.file_read usando file_id y continue_from, count=6000. '
                'Si no puedes continuar, explica que es parcial. No afirmes que has leído todo.')]
            return True
        # La cobertura parcial no invalida observaciones sobre el fragmento.
        # Retener evidencia y distinguirla de una afirmación de lectura total.
        if claimed:
            output['reply'] = 'No consta una lectura completa del documento.'
        output['reply'] = output['reply'].rstrip() + '\n\n' + '\n\n'.join(status(p) for p in states)
        turn.document_read_corrected = True
    elif states:
        output['reply'] = output['reply'].rstrip() + '\n\n' + '\n\n'.join(status(p) for p in states)
        turn.document_read_corrected = True
    return False
