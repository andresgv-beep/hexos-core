"""Recuperaciones acotadas de contexto, formato, lectura, cobertura y promesas."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING
from .. import catalog
from ..context import native_messages
from ..decisions import InvalidDecision, validate_reply
from ..work import now
from .settings import PROMPT
from .state import TurnState
from .ledger import checkpoint_messages

if TYPE_CHECKING:
    from .agent import Agent


# Sentinel local: None sigue siendo una salida inválida del modelo, no un reintento.
RETRY = object()


class RecoveryController:
    def __init__(self, agent: Agent):
        self.agent = agent

    def generate(self, store, turn: TurnState):
        try:
            try:
                output = self.agent.runtime.generate(turn.messages)
                if isinstance(output, dict) and 'reply' in output:
                    validate_reply(output['reply'])
            finally:
                generation = getattr(self.agent.runtime, 'last_generation', None)
                if generation is not None:
                    store.db.execute('INSERT INTO generation_events(turn_id,ts,body) VALUES (?,?,?)',
                        (turn.uid, now(), json.dumps(generation, ensure_ascii=False)))
                    store.db.commit()
        except RuntimeError as exc:
            # El motor dice que no cabe. Antes moría aquí y el turno se
            # quedaba colgado: la ventana mide la conversación, pero el
            # resultado de una herramienta entra a mitad de turno y no
            # cuenta para ese presupuesto. Se corta de verdad —KV incluido—
            # y se reintenta una vez desde limpio.
            if 'context_full' not in str(exc) or turn.retries.context_retries:
                raise
            turn.retries.context_retries += 1
            turn.checkpointed_steps = len(turn.trace)
            self.agent.runtime.call({'type': 'reset'})
            nuevo_corte = store.db.execute(
                'SELECT COALESCE(MAX(rowid),0) FROM conversation WHERE id<>?', (turn.uid,)).fetchone()[0]
            turn.handoff = self.agent.context.save_handoff(store, turn.history, nuevo_corte)
            store.db.execute("INSERT INTO agent_state VALUES ('context_boundary',?) "
                             'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                             (str(nuevo_corte),))
            store.db.commit()
            self.agent.context_cut = dict(at=now(), messages=len(turn.history),
                                    characters=sum(len(f['text']) for f in turn.history),
                                    reason='context_full')
            turn.history = []
            if turn.native:
                turn.metadata += self.agent.context.handoff_text(turn.handoff)
                turn.messages = native_messages([], turn.metadata, turn.prompt_text, {},
                                           turn.memory_evidence, budget=turn.budget)
                # Lo ya ejecutado vuelve como llamadas y respuestas nativas. Un
                # resumen en prosa no conserva causalidad y permitió que el modelo
                # registrara y diagnosticara el mismo equipo dos veces.
                turn.messages.extend(checkpoint_messages(
                    turn.trace[:turn.checkpointed_steps]))
                turn.messages.append({'role': 'user', 'content':
                    'AVISO DE HEXOS (no es la persona): continúa el mismo turno desde '
                    'el checkpoint anterior. Las operaciones exitosas que aparecen '
                    'arriba ya se ejecutaron: usa sus resultados y no las repitas. '
                    'Corrige únicamente las que consten como fallidas y termina el encargo.'})
            else:
                turn.messages = [dict(role='system', content=PROMPT),
                            dict(role='user', content='PETICIÓN ACTUAL:\n' + turn.prompt_text)]
            return RETRY
        except InvalidDecision as exc:
            if turn.retries.format_retries:
                raise InvalidDecision('No se pudo obtener una respuesta válida tras un reintento. ' + str(exc)) from exc
            turn.retries.format_retries += 1
            # Si el rechazo trae su propia instrucción, esa manda: al que se
            # dejó la lista sin escribir no le sirve que le hablen de JSON.
            repair = getattr(exc, 'repair', None) or getattr(
                self.agent.runtime, 'repair_instruction', 'Formato de decisión inválido. '
                'Devuelve solo un objeto JSON válido: reply y work:null para la respuesta, '
                'o tool y arguments para una herramienta. No repitas operaciones ya completadas.')
            turn.messages = [dict(role='user', content=repair)]
            return RETRY
        return output

    def before_completion(self, store, turn: TurnState, output: dict) -> bool:
        """True pide otra generación; no ejecuta acciones por su cuenta."""
        recoverable = {name for name, definition in catalog.TOOLS.items()
                       if definition['effect'] in ('read', 'result')}
        if (turn.trace and isinstance(turn.trace[-1]['result'], dict) and
                'error' in turn.trace[-1]['result'] and turn.trace[-1]['tool'] in recoverable and
                turn.retries.recovery_requests == 0):
            turn.retries.recovery_requests += 1
            turn.messages = [dict(role='user', content=
                'La operación solicitada no se completó. Puedes corregir los argumentos '
                'de la consulta o usar otra herramienta local de lectura con el mismo objetivo, '
                'sin pedir permiso para reintentar. No cambies el encargo. '
                'Si falta información imprescindible o el error no es recuperable, explica '
                'el bloqueo brevemente. Queda un intento de recuperación.')]
            return True
        # Nombró dos equipos y solo se leyó uno. No es falta de sitio:
        # es no llevar la cuenta de lo que se le pidió.
        faltan = self.agent.uncovered(self.agent.devices_named(store, turn.uid), turn.trace, turn.text)
        # Se insiste MIENTRAS AVANCE. Con un solo aviso pasó de cero
        # lecturas a dos y se quedó ahí: la cuenta seguía incompleta y ya
        # no había con qué recordárselo. Si un aviso no trae una lectura
        # nueva, no se repite: eso ya sería porfiar sin razón nueva.
        if faltan and turn.retries.coverage_retries < 3 and len(turn.trace) > turn.retries.coverage_mark:
            turn.retries.coverage_retries += 1
            turn.retries.coverage_mark = len(turn.trace)
            pendiente = ', '.join(n + (' (' + s + ')' if s else ' (no se ha leído nada)')
                                  for n, s in faltan)
            turn.messages = [dict(role='user', content=
                'AVISO DE HEXOS (no es la persona): en este turno falta por leer ' +
                pendiente + '. Un resumen que lo dé por revisado sería falso. Léelo ahora '
                'con nas_read. Si no puedes con alguno, dilo nombrándolo y di por qué. '
                'Queda un intento.')]
            return True
        # «Dijo que lo hacía y no lo hizo», en tres vistas de lo mismo:
        # anunció una herramienta concreta, prometió una acción inmediata,
        # o cantó una escritura. Un solo aviso por turno: son el mismo
        # fallo y avisar tres veces solo gasta generaciones.
        aviso = None
        anuncio = self.agent.announced_without_call(output['reply'], turn.trace)
        if anuncio:
            frase, herramienta = anuncio
            nativo_nombre = herramienta.replace('.', '_')
            aviso = ('tu respuesta dice ' + repr(frase) + ' y en este turno no se ha '
                     'ejecutado ' + nativo_nombre + '. Decirlo no lo hace: para ella no ha '
                     'cambiado nada. Llama a ' + nativo_nombre + ' AHORA con el id que '
                     'corresponda; si no lo tienes, búscalo primero en el mismo turno.')
        elif self.agent.unfulfilled_promise(output['reply'], turn.trace):
            aviso = ('tu respuesta dice ' + repr(self.agent.unfulfilled_promise(output['reply'], turn.trace)) +
                     ' y el turno iba a terminar ahí, sin haberlo hecho. Anunciarlo no lo hace, '
                     'y la persona se queda esperando algo que no va a llegar. Ejecútalo AHORA '
                     'con la herramienta que corresponda.')
        elif self.agent.unsupported_claim(output['reply'], turn.trace):
            aviso = ('en tu respuesta afirmas haber guardado o cambiado algo, pero en este '
                     'turno no se ha ejecutado ninguna operación de escritura. Decirlo no lo '
                     'guarda, y tu propia respuesta anterior no es prueba de que se hiciera. '
                     'Si había que hacerlo, hazlo AHORA con la herramienta que corresponda.')
        if aviso and not turn.retries.said_retries:
            turn.retries.said_retries += 1
            turn.previous_reply = output['reply']
            turn.messages = [dict(role='user', content=
                'AVISO DE HEXOS (no es la persona): ' + aviso +
                ' Si no hacía falta, responde de nuevo sin anunciarlo. Queda un intento. '
                'Este aviso es de la máquina: no lo menciones ni lo comentes. '
                'Responde a la persona como si no existiera.')]
            return True
        return False
