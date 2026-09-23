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
        # Evitar generar y mostrar una respuesta basada solo en fragmentos para
        # descartarla después. No elige URL ni ejecuta herramientas fuera del
        # bucle: el modelo completa la llamada y el ejecutor la valida como siempre.
        # El catálogo permanece estable para conservar el prefijo KV.
        if (turn.native and not turn.retries.web_read_guided
                and hasattr(self.agent.runtime, 'require_read')
                and not any(s.get('tool') == 'web.read' for s in turn.trace)):
            has_links = any(s.get('tool') == 'web.search' and not s.get('failed')
                and isinstance(s.get('result'), dict)
                and any(isinstance(i, dict) and i.get('url')
                        for i in s['result'].get('items', [])) for s in turn.trace)
            if has_links:
                turn.retries.web_read_guided = self.agent.runtime.require_read('web.read')
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
            # y se reconstruye desde operaciones registradas. Puede recuperarse
            # de nuevo si avanzó la traza; nunca insiste sin avance ni más de 3 veces.
            if ('context_full' not in str(exc) or turn.retries.context_retries >= 3 or
                    (turn.retries.context_retries and len(turn.trace) <= turn.checkpointed_steps)):
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
                # Recuperar el encargo y sus operaciones, no reinyectar perfil,
                # recuerdos y traspasos acumulados que llenaron la ventana.
                turn.messages = native_messages([], '', turn.prompt_text, {},
                                           [], budget=turn.budget)
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
            if not getattr(exc, 'repair', None):
                repair = ('AVISO DE HEXOS (no es la persona). Error concreto: ' + str(exc) + '\n' + repair)
            turn.messages = [dict(role='user', content=repair)]
            return RETRY
        return output

    def before_completion(self, store, turn: TurnState, output: dict) -> bool:
        """True pide otra generación; no ejecuta acciones por su cuenta."""
        recoverable = {name for name, definition in catalog.TOOLS.items()
                       if definition['effect'] in ('read', 'result')}
        if (turn.trace and isinstance(turn.trace[-1]['result'], dict) and
                turn.trace[-1]['result'].get('error') and turn.trace[-1]['tool'] in recoverable and
                turn.retries.recovery_requests == 0):
            turn.retries.recovery_requests += 1
            turn.messages = [dict(role='user', content=
                'La operación solicitada no se completó. Puedes corregir los argumentos '
                'de la consulta o usar otra herramienta local de lectura con el mismo objetivo, '
                'sin pedir permiso para reintentar. No cambies el encargo. '
                'Si falta información imprescindible o el error no es recuperable, explica '
                'el bloqueo brevemente. Queda un intento de recuperación.')]
            return True
        # Un fragmento del buscador sirve para descubrir fuentes, no para sostener
        # una respuesta. Medido en vivo: buscó «nuevo iPhone» y convirtió rumores
        # de los snippets en hechos sin abrir una sola página. La secuencia mínima
        # queda garantizada aquí, no en la memoria del modelo.
        searched = any(step.get('tool') == 'web.search' and not step.get('failed')
                       for step in turn.trace)
        read_sources = [step for step in turn.trace
                        if step.get('tool') == 'web.read' and not step.get('failed')
                        and isinstance(step.get('result'), dict)
                        and step['result'].get('url') and step['result'].get('text')]
        if searched and not read_sources and not turn.retries.web_evidence_retries:
            turn.retries.web_evidence_retries += 1
            turn.previous_reply = output['reply']
            turn.messages = [dict(role='user', content=
                'AVISO DE HEXOS (no es la persona): solo has visto fragmentos del buscador. '
                'No son fuentes leídas y no sostienen todavía una respuesta factual. Abre '
                'AHORA al menos uno de los enlaces devueltos por web_search mediante web_read; '
                'elige el más directo o autorizado para la pregunta. Después responde usando '
                'solo lo que la fuente realmente diga. No menciones este aviso.')]
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
                'con la herramienta que corresponda a la petición original: nas_find para buscar '
                'archivos, nas_directories para buscar carpetas, nas_shares para listar compartidas, '
                'nas_browse para listar una carpeta, nas_read para diagnóstico o estado. '
                'Conserva los filtros pedidos; no sustituyas buscar archivos por consultar espacio libre. '
                'Si no puedes con alguno, dilo nombrándolo y di por qué. '
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
