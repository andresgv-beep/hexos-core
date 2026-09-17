"""Coordinación del turno. Las políticas y efectos viven en componentes separados."""
from __future__ import annotations

from typing import TYPE_CHECKING
from ..work import string
from .finalization import TurnFinalizer
from .recovery import RecoveryController, RETRY
from .settings import MAX_INPUT, IMAGEN_SIN_TEXTO, MAX_TURN_ITERATIONS
from .state import TurnState
from .tools import ToolExecutor

if TYPE_CHECKING:
    from .agent import Agent


class TurnRunner:
    def __init__(self, agent: Agent):
        self.agent = agent
        self.recovery = RecoveryController(agent)
        self.executor = ToolExecutor(agent)
        self.finalizer = TurnFinalizer(agent)

    def run(self, text, image=None):
        if not isinstance(text, str) or len(text.encode()) > MAX_INPUT:
            raise ValueError('Mensaje vacío o mayor de 8 MiB; no se ha guardado')
        # Adjuntar una foto y no escribir nada es un turno con sentido: la pregunta
        # está implícita. Se rellena aquí y no en cada cliente, que es como acabaron
        # la interfaz nueva y chat.html discrepando —una la ponía, la otra daba 409.
        if not text.strip():
            if image is None:
                raise ValueError('Mensaje vacío o mayor de 8 MiB; no se ha guardado')
            text = IMAGEN_SIN_TEXTO
        if not self.agent.lock.acquire(blocking=False):
            raise RuntimeError('Ya hay un turno en curso')
        self.agent.state = 'thinking'
        self.agent.active_tools = []
        try:
            with self.agent.store() as store:
                turn = TurnState(text=text, image=image)
                self.agent.context.prepare(store, turn)
                for _ in range(MAX_TURN_ITERATIONS):
                    output = self.recovery.generate(store, turn)
                    if output is RETRY:
                        continue
                    output, clarification = self.normalize_decision(output)
                    if 'tool' in output:
                        self.executor.execute(store, turn, output)
                        continue
                    if set(output) != {'reply', 'work'} or not isinstance(output['reply'], str):
                        raise ValueError('Respuesta estructurada inválida: campos ' + ', '.join(output))
                    if self.recovery.before_completion(store, turn, output):
                        continue
                    job = self.finalizer.classify(store, turn, output, clarification)
                    if job is RETRY:
                        continue
                    return self.finalizer.finish(store, turn, output, job)
                raise RuntimeError('Se alcanzó el límite de consultas del turno; lo hecho hasta '
                                   'aquí queda en la traza y no se ha comprobado lo que faltaba')
        finally:
            self.agent.state = 'idle'
            self.agent.lock.release()

    @staticmethod
    def normalize_decision(output):
        if not isinstance(output, dict):
            raise ValueError('El modelo no devolvió un objeto')
        clarification = None
        if 'clarify' in output:
            if set(output) != {'clarify','intent'}:
                raise ValueError('Aclaración inválida')
            string(output['clarify'], 'clarify', 500)
            string(output['intent'], 'intent', 500)
            clarification = {'intent':output['intent'], 'question':output['clarify']}
            output = {'reply':output['clarify'], 'work':None}
        return output, clarification
