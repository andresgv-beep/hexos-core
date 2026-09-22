"""Lecturas del registro operativo; no lanza simuladores ni conversiones."""
from pathlib import Path
from ..media_jobs.store import JobStore


def dispatch(workspace, name, args):
    if not (Path(workspace)/'media_jobs.sqlite').exists():
        if name == 'media.jobs':
            return dict(execution_enabled=False, batches=[], note='No hay tareas; adaptador NAS aún no habilitado.')
        raise ValueError('No hay registro de tareas multimedia')
    store = JobStore(workspace)
    try:
        if name == 'media.jobs':
            batches = store.listing()
            return dict(execution_enabled=False, batches=[dict(id=b['id'], paused=b['paused'], mode=b['mode'],
                         jobs=[{k:j[k] for k in ('id','state','position','due','attempt')} for j in b['jobs']]) for b in batches],
                        note='Registro operativo. Una tarea simulation no acredita una conversión real.')
        if name == 'media.job':
            job = store.get(args['id'])
            return {k:job.get(k) for k in ('id','batch_id','state','revision','mode','source','attempt','due',
                                         'observation','error','publication','validation')}
        raise ValueError('Herramienta multimedia desconocida')
    finally:
        store.close()
