"""La cola de vídeo tal como la enseña la interfaz: solo los campos de la tarjeta.

La tarjeta viva no pasa por el modelo. Lee la misma cola que el trabajador y
devuelve una lista cerrada de datos —título, estado, progreso, tamaños—; nada
de rutas completas, perfiles ni recibos, que no pintan nada en pantalla.
"""
import json
import sqlite3
import threading
import time
from pathlib import Path

from ..media_jobs.configuration import load
from ..media_jobs.contracts import SharedFailure, UncertainEffect
from ..media_jobs.nas_encoder import NasEncoderTransport, NasHandBrake
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


class LiveProgress:
    """El progreso que la tarjeta pide al encoder mientras alguien la mira.

    La cola observa cada muchos minutos (lo que decide su ritmo es la cola, no
    la pantalla), así que la barra avanzaba a saltos. Esta lectura es aparte:
    solo lee, no guarda nada en la cola, va en segundo plano para no bloquear
    la respuesta y como mucho una vez cada `interval` segundos por película.
    """

    def __init__(self, observe, clock=time.time, interval=20, spawn=None):
        self.observe, self.clock, self.interval = observe, clock, interval
        self.spawn = spawn or (lambda work: threading.Thread(target=work, daemon=True).start())
        self._samples, self._busy, self._lock = {}, set(), threading.Lock()

    def sample(self, job):
        """La última lectura de esta ejecución, y pide otra si ya es vieja."""
        with self._lock:
            entry = self._samples.get(job['id'])
            start = ((not entry or self.clock() - entry['at'] >= self.interval)
                     and job['id'] not in self._busy)
            if start:
                self._busy.add(job['id'])
        if start:
            self.spawn(lambda: self._read(job))
        if entry and entry['sample'].get('run_id') == job.get('run_id'):
            return entry['sample']
        return None

    def _read(self, job):
        try:
            sample = self.observe(job)
            if isinstance(sample, dict) and sample.get('run_id') == job.get('run_id'):
                with self._lock:
                    self._samples[job['id']] = dict(at=self.clock(), sample=sample)
        except (SharedFailure, UncertainEffect, OSError, ValueError, KeyError, TypeError):
            pass  # La tarjeta sigue con la última lectura de la cola.
        finally:
            with self._lock:
                self._busy.discard(job['id'])


def encoder_observer(workspace):
    """Lee el encoder como lo hace media.job: misma configuración y misma ejecución."""
    def observe(job):
        config = load(workspace)
        if (not config or job['source']['device'] != config['device']
                or job.get('config_digest') != config['digest']):
            raise ValueError('Configuración distinta de la tarea; no consultar otro destino')
        encoder = NasHandBrake(NasEncoderTransport(workspace, config['device'], config['container']),
                               config['preset_version'])
        return encoder.observe(job)
    return observe


def _gb(value):
    return round(value/1e9, 1) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _card(job, paused, updated, live=None):
    state = job['state']
    source = job.get('source') or {}
    item = dict(id=job['id'], batch_id=job['batch_id'], title=movie_title(source.get('path') or job['id']),
                state=state, label=LABELS.get(state, state), paused=bool(paused), updated_at=updated,
                size_before_gb=_gb((source.get('identity') or {}).get('size_bytes')))
    observation = job.get('observation') or {}
    if live and live.get('status') == 'running':
        observation = live
    if state == 'running' and observation.get('status') == 'running':
        percent = observation.get('percent')
        if isinstance(percent, (int, float)) and not isinstance(percent, bool):
            item['percent'] = round(max(0.0, min(100.0, percent)), 1)
            eta = observation.get('eta_seconds')
            if isinstance(eta, (int, float)) and not isinstance(eta, bool) and eta >= 0:
                item['eta_seconds'] = int(eta)
            # Con poco hecho la extrapolación dice cualquier cosa, y en la primera
            # pasada de un perfil a dos pasadas todavía no hay archivo de salida.
            written = observation.get('output_bytes')
            if percent >= 5 and isinstance(written, (int, float)) and written > 0:
                item['estimated_gb'] = _gb(written * 100 / percent)
    elif state in AFTER_ENCODE or state == 'completed' or job.get('review_kind') == 'publication':
        item['percent'] = 100.0
    if state == 'awaiting_review' and job.get('review_kind') == 'publication':
        # Convertida y comprobada: solo falta el visto bueno para ponerla en la biblioteca.
        item['label'] = 'Lista para publicar'
    if state == 'completed':
        item['size_after_gb'] = _gb(((job.get('publication') or {}).get('identity') or {}).get('size_bytes'))
    elif (job.get('validation') or {}).get('valid') is True:
        item['size_after_gb'] = _gb(((job.get('validation') or {}).get('identity') or {}).get('size_bytes'))
    elif state in ('failed', 'blocked') and job.get('error'):
        item['error'] = str(job['error'])[:200]
    return item


def summary(workspace, now=None, progress=None):
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
        live = (progress.sample(job) if progress and job['state'] == 'running'
                and job.get('mode') == 'live' and job.get('run_id') else None)
        jobs.append(_card(job, paused, updated, live))
        if len(jobs) == LIMIT:
            break
    return dict(jobs=jobs)


def control(workspace, payload, now=None, progress=None):
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
    return summary(workspace, now, progress)
