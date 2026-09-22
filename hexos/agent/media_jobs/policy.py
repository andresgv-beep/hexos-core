"""Política pura; segundos UTC desde epoch para persistencia y relojes falsos."""
import math

TERMINAL = frozenset({'completed', 'failed', 'cancelled'})
STATES = TERMINAL | {'queued', 'copying', 'ready', 'running', 'recovering',
                     'verifying', 'publishing', 'indexing', 'cancel_requested', 'blocked'}


def check_delay(eta_seconds=None, first=False):
    if first:
        return 120
    if (isinstance(eta_seconds, bool) or not isinstance(eta_seconds, (int, float))
            or not math.isfinite(eta_seconds) or eta_seconds < 0):
        return 120
    if eta_seconds <= 120:
        return 60
    return min(1800, eta_seconds)


def observe_progress(previous, sample, now, stall_seconds=1800, minimum_samples=3):
    """Fase nueva o actividad reinicia el contador; solo muestras válidas cuentan.

    Umbral conservador configurable, no certificación de que cualquier encoder
    esté bloqueado. La recuperación confirma el proceso antes de intervenir.
    """
    previous = previous or {}
    signals = ('phase', 'percent', 'output_bytes', 'activity_counter')
    if any(key not in sample for key in signals):
        raise ValueError('observación sin señales suficientes')
    percent = sample['percent']
    if (not isinstance(sample['phase'], str) or not sample['phase']
            or type(percent) not in (int, float) or not math.isfinite(percent) or not 0 <= percent <= 100
            or any(type(sample[k]) is not int or sample[k] < 0 for k in ('output_bytes','activity_counter'))):
        raise ValueError('Señales de progreso inválidas')
    changed = any(sample[k] != previous.get(k) for k in signals)
    last = now if changed else previous.get('last_advance_at', now)
    count = 0 if changed else previous.get('unchanged_samples', 0) + 1
    result = dict(sample, observed_at=now, last_advance_at=last, unchanged_samples=count)
    return result, count >= minimum_samples and now-last >= stall_seconds
