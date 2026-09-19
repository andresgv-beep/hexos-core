"""Coordinación del turno. Las políticas y efectos viven en componentes separados."""
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4
from ..native_transport import TurnCancelled
from ..work import now
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

    def run(self, text, image=None, initial_tool=None, display_text=None, request_id=None):
        if not isinstance(text, str) or len(text.encode()) > MAX_INPUT:
            raise ValueError('Mensaje vacío o mayor de 8 MiB; no se ha guardado')
        if display_text is not None and (not isinstance(display_text, str)
                or not display_text.strip() or len(display_text.encode()) > MAX_INPUT):
            raise ValueError('Texto visible vacío o mayor de 8 MiB; no se ha guardado')
        # Adjuntar una foto y no escribir nada es un turno con sentido: la pregunta
        # está implícita. Se rellena aquí y no en cada cliente, que es como acabaron
        # la interfaz nueva y chat.html discrepando —una la ponía, la otra daba 409.
        if not text.strip():
            if image is None:
                raise ValueError('Mensaje vacío o mayor de 8 MiB; no se ha guardado')
            text = IMAGEN_SIN_TEXTO
        visible = display_text if display_text is not None else text
        if not self.agent.lock.acquire(blocking=False):
            raise RuntimeError('Ya hay un turno en curso')
        self.agent.state = 'thinking'
        self.agent.active_tools = []
        turn = None
        try:
            self.agent.begin_generation(request_id)
            with self.agent.store() as store:
                turn = TurnState(text=visible, image=image, model_request=text)
                self.agent.context.prepare(store, turn)
                self.agent.check_cancelled()
                # Diagnóstico/contenedores/espacio + un único equipo nombrado
                # es una lectura inequívoca y pide estado actual. No se permite
                # que el modelo la responda reutilizando un resultado histórico.
                if initial_tool is None:
                    initial_tool = self.agent.explicit_read(store, turn.uid, turn.text)
                # Reanudar tras el modal no vuelve a preguntar al modelo qué
                # quería hacer: ejecuta la operación que abrió ese modal. El
                # resultado sí vuelve al modelo para que lo interprete.
                if initial_tool is not None:
                    self.agent.check_cancelled()
                    # El protocolo nativo exige que el resultado siga a una
                    # llamada. Se repone esa llamada estructuralmente, sin pedir
                    # al modelo que vuelva a decidir ni ejecutar dos veces.
                    if hasattr(self.agent.runtime, 'begin_tool'):
                        self.agent.runtime.begin_tool(turn.messages, initial_tool)
                        turn.messages = []
                    self.executor.execute(store, turn, initial_tool)
                for _ in range(MAX_TURN_ITERATIONS):
                    self.agent.check_cancelled()
                    output = self.recovery.generate(store, turn)
                    self.agent.check_cancelled()
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
        except TurnCancelled:
            snapshot = self.agent.generation_snapshot() or {}
            partial = snapshot.get('text', '').strip()
            reply = (partial + '\n\n' if partial else '') + '[Respuesta interrumpida por la persona.]'
            # Rebuild the next prompt from the archive and tool ledger, not an
            # incomplete assistant prefix or half a tool call.
            self.agent.runtime.call({'type': 'reset'})
            if turn and turn.uid:
                with self.agent.store() as store:
                    store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                        (uuid4().hex, now(), 'assistant', reply, reply))
                    store.db.commit()
            return dict(reply=reply, tools=turn.trace if turn else [], cancelled=True)
        finally:
            if hasattr(self.agent.runtime, 'pending_image'):
                self.agent.runtime.pending_image = None
            self.agent.end_generation()
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
