"""Ephemeral generation snapshots; the archived final reply remains authoritative."""
import threading
import math


class LiveGeneration:
    def __init__(self, request_id, cancellable):
        self.request_id = request_id
        self.decode_tokens = 0
        self.decode_ms = 0
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.data = dict(request_id=request_id, phase='preparing', text='', processed=0,
                         total=0, cancellable=cancellable, cancelling=False)

    def update(self, values):
        with self.lock:
            values = dict(values)
            sample = values.pop('decode_sample', None)
            if isinstance(sample, dict):
                tokens, ms = sample.get('tokens'), sample.get('milliseconds')
                if (type(tokens) is int and tokens >= 0 and
                        type(ms) in (int, float) and math.isfinite(ms) and ms > 0):
                    self.decode_tokens += tokens
                    self.decode_ms += ms
                    self.data['tokens_per_second'] = self.decode_tokens * 1000 / self.decode_ms
            self.data.update(values)

    def snapshot(self):
        with self.lock:
            return dict(self.data)
