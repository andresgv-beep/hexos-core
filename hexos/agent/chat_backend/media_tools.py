"""Herramientas multimedia: selección observada, cola durable y consultas acotadas."""
from pathlib import Path
import time
from ..media_jobs.store import JobStore
from ..media_jobs.configuration import load
from ..media_jobs import planning
from ..media_jobs import presence
from ..internal_tasks.queue import ReviewQueue
from ..media_jobs.nas_encoder import NasHandBrake, NasEncoderTransport
from ..media_jobs.contracts import SharedFailure, UncertainEffect


def job_snapshot(workspace, config, job):
    result = {k:job.get(k) for k in ('id','batch_id','state','revision','mode','source','attempt','due',
        'observation','completion','publication','validation','review_kind','copy_progress','verification_progress')}
    # Error de la tarea != fallo al consultar la ficha.
    result['task_error'] = job.get('error')
    result['observation_source'] = 'stored'
    result['file_presence'] = dict(source='not_checked')
    if job.get('mode') == 'live' and any(job.get(k) for k in ('completion','validation','publication')):
        try:
            result['file_presence'] = presence.observe(workspace, config, job)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            result['file_presence'] = dict(source='unavailable', warning=str(exc))
    if job.get('mode') == 'live' and job.get('state') == 'running' and config:
        try:
            if job['source']['device'] != config['device'] or job.get('config_digest') != config['digest']:
                raise ValueError('Configuración distinta de la tarea; no consultar otro destino')
            encoder = NasHandBrake(NasEncoderTransport(workspace, config['device'], config['container']),
                                   config['preset_version'])
            sample = encoder.observe(job)
            if sample.get('run_id') != job.get('run_id'):
                raise ValueError('Observación de otra ejecución')
            result['observation'] = sample
            result['observation_source'] = 'live'
        except (SharedFailure, UncertainEffect, OSError, ValueError) as exc:
            result['observation_warning'] = str(exc)
    result['note'] = ('state es el estado durable de la tarea; observation es la observación del encoder. '
                      'Si observation_source=stored, no es una lectura actual: indica su antigüedad. '
                      'completion y validation son recibos históricos, NO presencia actual. '
                      'live significa ejecución real, no conversión activa. awaiting_review espera una decisión, no está convirtiendo. '
                      'destination es el destino previsto de publicación, no la salida temporal del encoder. '
                      'Solo file_presence comprueba existencia actual; unavailable no significa ausente. '
                      'La consulta no ejecuta, verifica, publica ni modifica la tarea.')
    observed = (result.get('observation') or {}).get('observed_at')
    result['observation_age_seconds'] = max(0, time.time()-observed) if isinstance(observed, (int,float)) else None
    return result


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
            batches = store.listing()
            summaries = [planning.summary(b) for b in batches]
            checked = 0
            for batch, summary in zip(batches, summaries):
                for job, brief in zip(batch['jobs'], summary['jobs']):
                    brief.update(completion_recorded=bool(job.get('completion')),
                                 validation_recorded=bool(job.get('validation')),
                                 publication_recorded=bool(job.get('publication')),
                                 file_presence=dict(source='not_checked'))
                    if checked < 5 and job.get('mode') == 'live' and any(job.get(k) for k in ('completion','validation','publication')):
                        brief['file_presence'] = job_snapshot(workspace,config,job)['file_presence']
                        checked += 1
            return dict(execution_enabled=ready,batches=summaries,
                        internal_reviews=ReviewQueue(store).pending(),
                        note='live=ejecución real, NO en progreso. awaiting_review=espera revisión, NO convirtiendo. '
                        'Recibos históricos no acreditan presencia actual: mira file_presence; not_checked/unavailable no prueban ausencia. '
                        'Se comprueban hasta cinco fichas con recibos; usa media.job para las demás. '
                        'destination=destino final previsto, no salida temporal. Un error de internal_reviews es de la revisión, '
                        'no demuestra fallo del vídeo o del disco. Consulta media.job para completion, validation y rutas actuales.')
        if name=='media.job':
            job=store.get(args['id'])
            return job_snapshot(workspace, config, job)
        if name=='media.control':
            return planning.summary(store.control(args['batch_id'],args['operation'],time.time()))
        raise ValueError('Herramienta multimedia desconocida')
    finally:store.close()
