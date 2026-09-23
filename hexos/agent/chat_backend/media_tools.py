"""Herramientas multimedia: selección observada, cola durable y consultas acotadas."""
from pathlib import Path
import time
from ..media_jobs.store import JobStore
from ..media_jobs.configuration import load
from ..media_jobs import planning
from ..internal_tasks.queue import ReviewQueue


def context_reference(workspace):
    """Small operator-owned location map, not a scan or permission to execute."""
    import json
    try:
        config = load(workspace)
    except (ValueError, KeyError, OSError) as exc:
        return '\nCONFIGURACIÓN MULTIMEDIA NO DISPONIBLE: ' + str(exc)[:200] + '\n'
    if not config:
        return ''
    return ('\nBIBLIOTECAS DE PELÍCULAS CONFIGURADAS (rutas del operador; no un escaneo ni una orden):\n'
            + json.dumps(dict(device=config['device'], libraries=config['files']['libraries']), ensure_ascii=False)
            + '\nPara perfiles y disponibilidad consulta media_options.\n')


def dispatch(workspace, name, args):
    config_error = None
    try:config = load(workspace)
    except (ValueError, KeyError, OSError) as exc:
        if name in ('media.prepare','media.start'):raise
        config, config_error = None, str(exc)
    if name=='media.options':
        if not config:
            return dict(execution_enabled=False,profiles=[],libraries=[],note=config_error or 'Servicio multimedia sin configurar en este workspace.')
        store=JobStore(workspace)
        try:
            state=planning.health(store,config,time.time())
            return dict(execution_enabled=state['ready'],service=state,device=config['device'],
                        libraries=config['files']['libraries'],profiles=[dict(id=p['id'],
                        name=p['preset']['PresetName'],encoder=p['preset']['VideoEncoder'],format='mkv',
                        quality=p['preset']['VideoQualitySlider']) for p in config['profiles']])
        finally:store.close()
    if name in ('media.prepare','media.start'):
        if not config:raise ValueError('Configurar servicio multimedia antes de preparar o lanzar tareas')
        return planning.prepare(workspace,config,args) if name=='media.prepare' else planning.start(workspace,config,args['plan_id'])
    if not (Path(workspace)/'media_jobs.sqlite').exists():
        if name=='media.jobs':return dict(execution_enabled=False,batches=[],note='No hay tareas registradas.')
        raise ValueError('No hay registro de tareas multimedia')
    store=JobStore(workspace)
    try:
        if name=='media.jobs':
            ready=planning.health(store,config,time.time())['ready'] if config else False
            return dict(execution_enabled=ready,batches=[planning.summary(b) for b in store.listing()],
                        internal_reviews=ReviewQueue(store).pending(),
                        note='queued no es completed; simulation no acredita una conversión real.')
        if name=='media.job':
            job=store.get(args['id'])
            return {k:job.get(k) for k in ('id','batch_id','state','revision','mode','source','attempt','due',
                'observation','error','publication','validation','review_kind','copy_progress','verification_progress')}
        if name=='media.control':
            return planning.summary(store.control(args['batch_id'],args['operation'],time.time()))
        raise ValueError('Herramienta multimedia desconocida')
    finally:store.close()
