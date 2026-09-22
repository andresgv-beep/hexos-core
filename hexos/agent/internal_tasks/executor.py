"""Sesión fresca por intervención; ninguna referencia al runtime de conversación.

factory(binding=...) debe proporcionar un context manager que cree/libere una sesión aislada
con generate(request, max_tokens=..., timeout_seconds=...). El adaptador debe
hacer cumplir el timeout: este módulo no mata hilos ni reinicia runtimes compartidos.
"""
from .requests import validate
from .binding import HANDBRAKE_TRIAL_BINDING


class InternalExecutor:
    def __init__(self, slot, session_factory, current_job):
        self.slot, self.session_factory, self.current_job = slot, session_factory, current_job

    def run(self, request):
        with self.slot.internal() as acquired:
            if not acquired:
                return dict(status='deferred', request_id=request['request_id'])
            with self.session_factory(binding=HANDBRAKE_TRIAL_BINDING) as session:
                decision = session.generate(request, max_tokens=256, timeout_seconds=30)
            validate(request, decision, self.current_job(request['job_id']))
            return dict(status='proposed', decision=decision)
