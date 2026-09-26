"""Coordinación del turno. Las políticas y efectos viven en componentes separados."""
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4
from ..native_transport import TurnCancelled, GenerationInterrupted
from ..work import now
from ..work import string
from .finalization import TurnFinalizer
from .recovery import RecoveryController, RETRY
from ..native_transport import AudioClip
from .settings import MAX_INPUT, IMAGEN_SIN_TEXTO, AUDIO_SIN_TEXTO, MAX_TURN_ITERATIONS
from .state import TurnState
from .tools import ToolExecutor
from .listing_followups import listing_followup
from .file_responses import file_listing_reply
from .document_reading import check_completion
from .reading_budget import exhausted, iterations, READ_TOOLS
from .settings import MAX_TRACE_EVENTS

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
            text = AUDIO_SIN_TEXTO if isinstance(image, AudioClip) else IMAGEN_SIN_TEXTO
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
                    initial_tool = listing_followup(store, turn.uid, turn.text)
                    turn.listing_followup = initial_tool is not None
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
                if turn.listing_followup:
                    while len(turn.trace) < MAX_TRACE_EVENTS:
                        page = turn.trace[-1].get('result') or {}
                        if 'error' in page or page.get('next_offset') is None or not page.get('snapshot_id'):
                            break
                        call = dict(tool='nas.directory_page', arguments=dict(
                            snapshot_id=page['snapshot_id'], offset=page['next_offset'], limit=100))
                        self.agent.check_cancelled()
                        if hasattr(self.agent.runtime, 'begin_tool'):
                            self.agent.runtime.begin_tool(turn.messages, call)
                            turn.messages = []
                        self.executor.execute(store, turn, call)
                    reply = file_listing_reply(turn.text, turn.trace, continuation=True)
                    if reply is not None:
                        return self.finalizer.finish(store, turn, dict(reply=reply, work=None), None)
                iteration = 0
                while iteration < iterations(turn):
                    iteration += 1
                    self.agent.check_cancelled()
                    output = self.recovery.generate(store, turn)
                    self.agent.check_cancelled()
                    if output is RETRY:
                        continue
                    output, clarification = self.normalize_decision(output)
                    if 'tool' in output:
                        if output['tool'] in READ_TOOLS and exhausted(turn, output['tool']):
                            final = dict(reply='Lectura pausada por el límite de llamadas, tiempo o falta de avance. La cobertura queda registrada; no se ha programado una reanudación automática.', work=None)
                            check_completion(store, turn, final)
                            return self.finalizer.finish(store, turn, final, None)
                        self.executor.execute(store, turn, output)
                        continue
                    if set(output) != {'reply', 'work'} or not isinstance(output['reply'], str):
                        raise ValueError('Respuesta estructurada inválida: campos ' + ', '.join(output))
                    if check_completion(store, turn, output):
                        continue
                    if not turn.document_read_corrected and self.recovery.before_completion(store, turn, output):
                        continue
                    job = self.finalizer.classify(store, turn, output, clarification)
                    if job is RETRY:
                        continue
                    return self.finalizer.finish(store, turn, output, job)
                raise RuntimeError('Se alcanzó el límite de consultas del turno; lo hecho hasta '
                                   'aquí queda en la traza y no se ha comprobado lo que faltaba')
        except GenerationInterrupted as exc:
            partial = exc.text
            # Close only the display fence so the status is not mistaken for
            # generated source code. The raw completion remains in the trace.
            if partial.count('```') % 2:
                partial += '\n```'
            reason = ('se llenó la ventana de contexto' if exc.reason == 'context_full'
                      else 'se alcanzó el límite de continuación' if exc.reason == 'output_limit'
                      else 'falló la continuación del motor')
            reply = (partial + '\n\n' if partial else '') + (
                '[Respuesta incompleta: ' + reason + '. Lo generado queda guardado; '
                'no se ha dado la implementación por terminada. Puedes pedirme que continúe.]')
            if turn and turn.uid:
                with self.agent.store() as store:
                    store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                        (uuid4().hex, now(), 'assistant', reply, reply))
                    store.db.commit()
            self.agent.runtime.call({'type': 'reset'})
            return dict(reply=reply, tools=turn.trace if turn else [], incomplete=True,
                        interruption_reason=exc.reason)
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
