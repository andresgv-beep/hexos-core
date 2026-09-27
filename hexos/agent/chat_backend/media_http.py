"""La cola de vídeo tal como la enseña la interfaz: solo los campos de la tarjeta.

La tarjeta viva no pasa por el modelo. Lee la misma cola que el trabajador y
devuelve una lista cerrada de datos —título, estado, progreso, tamaños—; nada
de rutas completas, perfiles ni recibos, que no pintan nada en pantalla.
"""
import json
import sqlite3
import time
from pathlib import Path

from ..media_jobs.policy import TERMINAL
from ..media_jobs.store import JobStore
from ..task_notices import movie_title

LABELS = dict(queued='En cola', copying='Copiando al equipo', ready='Preparada', running='Convirtiendo',
              recovering='Recuperando', verifying='Comprobando el resultado', publishing='Publicando',
              indexing='Actualizando la biblioteca', cleaning='Retirando el original',
              cancel_requested='Cancelando', blocked='Necesita tu decisión', awaiting_review='En revisión',
              completed='Terminada', failed='Fallida', cancelled='Cancelada')
# Después de convertir solo quedan pasos cortos: la barra ya está llena.
AFTER_ENCODE = frozenset({'verifying', 'publishing', 'indexing', 'cleaning'})
RECENT_SECONDS = 6*3600
LIMIT = 20


def _gb(value):
    return round(value/1e9, 1) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _card(job, paused, updated):
    state = job['state']
    source = job.get('source') or {}
    item = dict(id=job['id'], batch_id=job['batch_id'], title=movie_title(source.get('path') or job['id']),
                state=state, label=LABELS.get(state, state), paused=bool(paused), updated_at=updated,
                size_before_gb=_gb((source.get('identity') or {}).get('size_bytes')))
    observation = job.get('observation') or {}
    if state == 'running' and observation.get('status') == 'running':
        percent = observation.get('percent')
        if isinstance(percent, (int, float)) and not isinstance(percent, bool):
            item['percent'] = round(max(0.0, min(100.0, percent)), 1)
            eta = observation.get('eta_seconds')
            if isinstance(eta, (int, float)) and not isinstance(eta, bool) and eta >= 0:
                item['eta_seconds'] = int(eta)
            # Con poco hecho la extrapolación dice cualquier cosa.
            if percent >= 5:
                item['estimated_gb'] = _gb((observation.get('output_bytes') or 0) * 100 / percent)
    elif state in AFTER_ENCODE or state == 'completed':
        item['percent'] = 100.0
    if state == 'completed':
        item['size_after_gb'] = _gb(((job.get('publication') or {}).get('identity') or {}).get('size_bytes'))
    elif state in ('failed', 'blocked') and job.get('error'):
        item['error'] = str(job['error'])[:200]
    return item


def summary(workspace, now=None):
    """Lo activo y lo que terminó en las últimas horas, lo más reciente primero."""
    now = time.time() if now is None else now
    path = Path(workspace)/'media_jobs.sqlite'
    if not path.exists():
        return dict(jobs=[])
    db = sqlite3.connect('file:'+str(path)+'?mode=ro', uri=True, timeout=5)
    try:
        rows = db.execute(
            'SELECT j.body, b.paused, (SELECT max(ts) FROM media_events e WHERE e.job_id=j.id) '
            'FROM media_jobs j JOIN media_batches b ON b.id=j.batch_id ORDER BY j.rowid DESC LIMIT ?',
            (LIMIT*3,)).fetchall()
    finally:
        db.close()
    jobs = []
    for body, paused, last_event in rows:
        job = json.loads(body)
        updated = last_event or job.get('created_at') or 0
        if job['state'] in TERMINAL and now - updated > RECENT_SECONDS:
            continue
        jobs.append(_card(job, paused, updated))
        if len(jobs) == LIMIT:
            break
    return dict(jobs=jobs)


def control(workspace, payload, now=None):
    """Pausar, reanudar o cancelar un lote desde la tarjeta, como haría media.control."""
    if not isinstance(payload, dict) or set(payload) != {'batch_id', 'operation'}:
        raise ValueError('se espera {"batch_id": "...", "operation": "pause|resume|cancel"}')
    batch_id, operation = payload['batch_id'], payload['operation']
    if not isinstance(batch_id, str) or not batch_id.strip() or len(batch_id) > 64:
        raise ValueError('batch_id no válido')
    store = JobStore(workspace)
    try:
        store.control(batch_id, operation, time.time() if now is None else now)
    finally:
        store.close()
    return summary(workspace, now)
