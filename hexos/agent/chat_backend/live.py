"""Ephemeral generation snapshots; the archived final reply remains authoritative."""
import threading


class LiveGeneration:
    def __init__(self, request_id, cancellable):
        self.request_id = request_id
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.data = dict(request_id=request_id, phase='preparing', text='', processed=0,
                         total=0, cancellable=cancellable, cancelling=False)

    def update(self, values):
        with self.lock:
            self.data.update(values)

    def snapshot(self):
        with self.lock:
            return dict(self.data)
