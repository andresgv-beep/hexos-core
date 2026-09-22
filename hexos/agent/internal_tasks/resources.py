"""Exclusión de inferencia y prioridad del chat; no promete preempción CUDA."""
from contextlib import contextmanager
import threading


class InferenceSlot:
    def __init__(self):
        self.condition = threading.Condition()
        self.busy = False
        self.chat_waiting = 0

    @contextmanager
    def chat(self):
        with self.condition:
            self.chat_waiting += 1
            try:
                while self.busy:
                    self.condition.wait()
                self.busy = True
            finally:
                self.chat_waiting -= 1
        try:
            yield
        finally:
            self._release()

    @contextmanager
    def internal(self):
        with self.condition:
            acquired = not self.busy and not self.chat_waiting
            if acquired:
                self.busy = True
        try:
            yield acquired
        finally:
            if acquired:
                self._release()

    def _release(self):
        with self.condition:
            self.busy = False
            self.condition.notify_all()
