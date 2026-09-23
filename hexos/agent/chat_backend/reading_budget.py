"""Presupuesto independiente para lecturas de documentos, sin ampliar escrituras."""
import time

from .settings import MAX_TRACE_EVENTS, MAX_TURN_ITERATIONS

READ_TOOLS = frozenset(('nas.file_open', 'nas.file_read'))
MAX_DOCUMENT_CALLS = 48
MAX_READING_SECONDS = 300


def reading_calls(turn):
    return sum(step.get('tool') in READ_TOOLS for step in turn.trace)


def stalled(turn):
    # Tres lecturas consecutivas de la misma copia sin cobertura nueva.
    reads = [s for s in turn.trace if s.get('tool') == 'nas.file_read']
    if len(reads) < 3:
        return False
    marks = []
    for step in reads[-3:]:
        result = step.get('result') or {}
        progress = result.get('reading_progress') or {}
        if not progress.get('file_id') or 'covered_ranges' not in progress:
            return False
        marks.append((progress['file_id'], progress['covered_ranges']))
    return marks[0] == marks[1] == marks[2]


def exhausted(turn, tool):
    if tool not in READ_TOOLS:
        return sum(step.get('tool') not in READ_TOOLS for step in turn.trace) >= MAX_TRACE_EVENTS
    return (reading_calls(turn) >= MAX_DOCUMENT_CALLS or stalled(turn) or
            (turn.reading_started is not None and
             time.monotonic() - turn.reading_started >= MAX_READING_SECONDS))


def iterations(turn):
    return MAX_TURN_ITERATIONS + (MAX_DOCUMENT_CALLS * 2 if reading_calls(turn) else 0)
