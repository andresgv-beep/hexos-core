"""Servicio de vencimientos del proceso HexOS; SQLite conserva el trabajo al salir."""
import json
import threading
import time
from ..internal_tasks.queue import ReviewQueue
from .configuration import load
from .nas_encoder import NasEncoderTransport, NasHandBrake
from .nas_files_adapter import NasFiles
from .nas_files_transport import NasFilesTransport
from .planning import ensure
from .runner import Runner
from .store import JobStore, Conflict


class MediaWorker:
    def __init__(self, workspace, runtime, *, chat_busy=lambda: False):
        self.workspace,self.runtime,self.chat_busy=workspace,runtime,chat_busy
        self.stop_event=threading.Event()
        self.thread=None
        self.last_error=None

    def start(self):
        self.thread=threading.Thread(target=self.run,daemon=True,name='hexos-media-jobs')
        self.thread.start()
        return self

    def run(self):
        while not self.stop_event.is_set():
            try:self.tick()
            except Exception as exc:self.last_error=str(exc)
            self.stop_event.wait(1)

    def tick(self):
        config=load(self.workspace)
        if not config:return
        store=JobStore(self.workspace)
        try:
            ensure(store.db)
            ready=bool(getattr(self.runtime,'progressive',False) and hasattr(self.runtime,'internal_decision'))
            state=dict(ready=ready,config_digest=config['digest'],error=self.last_error)
            store.db.execute('INSERT OR REPLACE INTO media_service VALUES (?,?,?)',
                             (config['resource'],time.time(),json.dumps(state)))
            if not ready:return
            encoder=NasHandBrake(NasEncoderTransport(self.workspace,config['device'],config['container']),config['preset_version'])
            files=NasFiles(NasFilesTransport(self.workspace,config['device']),config['files'],self.workspace)
            runner=Runner(store,files,encoder,time.time,config_digest=config['digest'])
            try:runner.tick(config['resource'])
            except Conflict:pass  # Una cancelación o lease nuevo invalida el resultado antiguo.
            reviews=ReviewQueue(store)
            if self.chat_busy() or self.stop_event.is_set():return
            claimed=reviews.claim(time.time())
            if not claimed:return
            request,token=claimed
            try:
                result=self.runtime.internal_decision(request)
                reviews.finish(request,token,time.time(),decision=result.get('decision'),
                               deferred=result.get('status')=='deferred')
            except Exception as exc:
                from ..chat_backend.model_lifecycle import ModelUnavailable
                try:reviews.finish(request,token,time.time(),error=str(exc),unavailable=isinstance(exc,ModelUnavailable))
                except ValueError:pass
                self.last_error=str(exc)
        finally:store.close()

    def close(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=25)
        try:
            config=load(self.workspace)
            if config:
                store=JobStore(self.workspace)
                try:
                    ensure(store.db)
                    store.db.execute('INSERT OR REPLACE INTO media_service VALUES (?,?,?)',
                        (config['resource'],time.time(),json.dumps(dict(ready=False,config_digest=config['digest'],error='Servicio detenido'))))
                finally:store.close()
        except (ValueError, KeyError, OSError):pass
