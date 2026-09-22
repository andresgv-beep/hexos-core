"""Una transición por tick. No espera, no usa LLM y no depende del chat."""
from .contracts import FileFailure, SharedFailure, UncertainEffect
from .policy import check_delay, observe_progress


class Runner:
    def __init__(self, store, files, encoder, clock, *, stall_seconds=1800):
        self.store, self.files, self.encoder, self.clock = store, files, encoder, clock
        self.stall_seconds = stall_seconds

    def tick(self, resource):
        claimed = self.store.claim(resource, self.clock())
        if not claimed:
            return None
        job, token = claimed
        key = f"{job['id']}:{job['attempt']}:{job['state']}"
        self.store.intention(job, token, key, self.clock())
        pause = False
        try:
            if job['mode'] != getattr(self.encoder, 'mode', None) or job['mode'] != getattr(self.files, 'mode', None):
                raise SharedFailure('El adaptador no admite el modo de esta tarea')
            changes = self._step(job, key)
        except SharedFailure as exc:
            changes = dict(state='blocked', resume_state=job['state'], error=str(exc), due=self.clock()+120)
            pause = True
        except FileFailure as exc:
            changes = dict(state='failed', error=str(exc), due=self.clock())
        except (UncertainEffect, OSError, ValueError) as exc:
            # Ni conexión perdida ni una respuesta mal formada prueban fallo o éxito.
            changes = dict(error=str(exc), due=self.clock()+120)
        return self.store.finish(job, token, changes, self.clock(), pause=pause)

    def _step(self, job, key):
        state, now = job['state'], self.clock()
        next_state = dict(due=now, error=None)
        if state == 'queued':
            return dict(next_state, state='copying')
        if state == 'copying':
            receipt = self.files.stage(job, key)
            if receipt.get('pending') is True:
                return dict(next_state, due=now+120, copy_progress=receipt)
            if receipt.get('copied') is not True:
                raise UncertainEffect('Copia no comprobada')
            return dict(next_state, state='ready', staging=receipt)
        if state == 'ready':
            receipt = self.encoder.start(job, key)
            if not isinstance(receipt.get('run_id'), str) or not receipt['run_id']:
                raise UncertainEffect('Falta identidad de ejecución')
            return dict(next_state, state='running', run_id=receipt['run_id'],
                        due=now+check_delay(first=True), observation=None)
        if state == 'running':
            sample = self.encoder.observe(job)
            if sample.get('run_id') != job['run_id']:
                raise UncertainEffect('Observación de otra ejecución')
            if sample.get('status') == 'finished':
                if type(sample.get('exit_code')) is not int:
                    raise UncertainEffect('Falta código final del encoder')
                if sample['exit_code'] != 0:
                    return dict(next_state, state='recovering', error='Encoder terminó con error')
                return dict(next_state, state='verifying', completion=sample)
            if sample.get('status') != 'running':
                raise UncertainEffect('Estado remoto desconocido')
            observation, stalled = observe_progress(job.get('observation'), sample, now,
                                                     stall_seconds=self.stall_seconds)
            return dict(next_state, state='recovering' if stalled else 'running',
                        observation=observation, due=now if stalled else now+check_delay(sample.get('eta_seconds')))
        if state in ('recovering', 'cancel_requested'):
            file_stop = None
            if state == 'cancel_requested' and hasattr(self.files, 'stop') and self.files is not self.encoder:
                file_stop = self.files.stop(job, key+':files-stop')
                if file_stop.get('pending') is True:
                    return dict(next_state, due=now+15, file_stop_receipt=file_stop)
                if file_stop.get('stopped') is not True:
                    raise SharedFailure('No consta parada de las operaciones de archivos')
            # stop debe reconciliar también un start cuyo resultado se perdió.
            stopped = self.encoder.stop(job, key+':stop')
            if stopped.get('pending') is True:
                return dict(next_state, due=now+15, stop_receipt=stopped)
            if stopped.get('stopped') is not True:
                if stopped.get('exclusive') is not True:
                    raise SharedFailure('No consta exclusividad para reiniciar el contenedor')
                stopped = self.encoder.restart(job, key+':restart')
                if stopped.get('stopped') is not True or stopped.get('healthy') is not True:
                    raise UncertainEffect('Reinicio o parada no comprobados')
            if state == 'cancel_requested':
                return dict(next_state, state='cancelled', stop_receipt=stopped, file_stop_receipt=file_stop)
            if job['attempt'] >= 1:
                return dict(next_state, state='failed', error='Agotado el único reintento', stop_receipt=stopped)
            return dict(next_state, state='ready', attempt=job['attempt']+1,
                        run_id=None, observation=None, stop_receipt=stopped)
        if state == 'verifying':
            receipt = self.files.verify(job, key)
            if receipt.get('pending') is True:
                return dict(next_state, due=now+120, verification_progress=receipt)
            if receipt.get('valid') is not True:
                raise FileFailure('Salida rechazada por verificación: ' + str(receipt.get('reason', 'sin evidencia')))
            return dict(next_state, state='publishing', validation=receipt)
        if state == 'publishing':
            receipt = self.files.publish(job, key)
            if receipt.get('pending') is True:
                return dict(next_state, due=now+120, publication_progress=receipt)
            if receipt.get('published') is not True or receipt.get('path') != job['source']['destination']:
                raise UncertainEffect('Publicación no comprobada en el destino esperado')
            return dict(next_state, state='indexing', publication=receipt)
        if state == 'indexing':
            receipt = self.files.index(job, key)
            if receipt.get('pending') is True:
                return dict(next_state, due=now+120, index_progress=receipt)
            if receipt.get('indexed') is not True:
                raise UncertainEffect('Salida publicada; falta actualizar catálogo')
            return dict(next_state, state='completed', index_receipt=receipt)
        raise ValueError('Transición no ejecutable: ' + state)
