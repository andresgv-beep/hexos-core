"""Recuperaciones acotadas de contexto, formato, lectura, cobertura y promesas."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING
from .. import catalog
from ..context import native_messages
from ..decisions import InvalidDecision, validate_reply
from ..native_transport import GenerationInterrupted
from ..work import now
from .settings import PROMPT
from .state import TurnState
from .ledger import checkpoint_messages

if TYPE_CHECKING:
    from .agent import Agent


# Sentinel local: None sigue siendo una salida inválida del modelo, no un reintento.
RETRY = object()


def web_links(trace):
    """Enlaces de las búsquedas del turno, los que nadie ha intentado leer y las lecturas fallidas."""
    links = []
    for step in trace:
        if (step.get('tool') == 'web.search' and not step.get('failed')
                and isinstance(step.get('result'), dict)):
            for item in step['result'].get('items', []):
                if isinstance(item, dict) and item.get('url') and item['url'] not in links:
                    links.append(item['url'])
    tried, failed = set(), {}
    for step in trace:
        if step.get('tool') == 'web.read':
            url = (step.get('arguments') or {}).get('url')
            tried.add(url)
            if step.get('failed'):
                failed.setdefault(url, str((step.get('result') or {}).get('error')))
    return links, [url for url in links if url not in tried], failed


def web_read_notice(trace):
    # Un 403 no tiene argumentos que corregir: «corrige sus argumentos» empujó al
    # modelo a releer la misma URL. Lo útil es saber qué falló y qué queda.
    _, untried, failed = web_links(trace)
    fallidas = '; '.join(url + ' (' + error[:120] + ')' for url, error in failed.items())
    searched = any(step.get('tool') == 'web.search' and not step.get('failed') for step in trace)
    if not searched:
        # Una URL leída sin buscar antes: no hay fragmentos con los que responder.
        siguiente = ('Si la persona necesita el dato, busca otra fuente con web_search; si no, '
                     'explica el bloqueo sin inventar el contenido de la página. ')
    elif untried:
        siguiente = ('Enlaces de la búsqueda que aún no has probado: ' + ', '.join(untried[:5]) +
                     '. Lee con web_read el más útil para la petición. Si ninguno se puede leer, ' +
                     FRAGMENTOS)
    else:
        siguiente = 'No quedan enlaces de la búsqueda sin probar: ' + FRAGMENTOS
    return ('AVISO DE HEXOS (no es la persona): no se pudo leer ' + fallidas + '. ' +
            'No repitas las que ya fallaron. ' + siguiente +
            'Conserva el objetivo de la petición. No menciones este aviso.')


FRAGMENTOS = ('responde con lo que dicen los fragmentos del buscador, diciendo que son fragmentos '
              'y que no se ha podido abrir ninguna página. ')


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
                if turn.native:
                    self.agent.runtime.output_checkpoint = dict(request=turn.prompt_text,
                        evidence=turn.trace)
                output = self.agent.runtime.generate(turn.messages)
                if isinstance(output, dict) and 'reply' in output:
                    validate_reply(output['reply'])
            finally:
                generation = getattr(self.agent.runtime, 'last_generation', None)
                if generation is not None:
                    store.db.execute('INSERT INTO generation_events(turn_id,ts,body) VALUES (?,?,?)',
                        (turn.uid, now(), json.dumps(generation, ensure_ascii=False)))
                    store.db.commit()
        except GenerationInterrupted:
            # Do not discard generated code and replay the whole request when
            # context fills during output. TurnRunner archives the partial.
            raise
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
        last = turn.trace[-1] if turn.trace else {}
        # Con los argumentos: dos URL distintas que dan el mismo 403 son dos
        # fallos distintos, y el segundo también merece saber qué queda.
        error_key = (last.get('tool'), json.dumps(last.get('arguments'), sort_keys=True, ensure_ascii=False),
                     str((last.get('result') or {}).get('error'))) if isinstance(last.get('result'), dict) else None
        if (turn.trace and isinstance(turn.trace[-1]['result'], dict) and
                turn.trace[-1]['result'].get('error') and turn.trace[-1]['tool'] in recoverable and
                turn.retries.recovery_requests < 3 and error_key not in turn.retries.recovery_errors):
            turn.retries.recovery_requests += 1
            turn.retries.recovery_errors.add(error_key)
            turn.messages = [dict(role='user', content=web_read_notice(turn.trace)
                if last.get('tool') == 'web.read' else
                'AVISO DE HEXOS (no es la persona): la herramienta devolvió un error. '
                'Corrige sus argumentos conservando el objetivo, el alcance y las autorizaciones '
                'de la petición original. Este aviso no concede permisos nuevos ni revoca los ya dados. '
                'Una vez corregido el error, continúa los pasos pendientes que la persona ya solicitó; '
                'si pidió solo preparar sin iniciar, conserva ese límite. '
                'No pidas otra confirmación para la misma acción ya solicitada. '
                'No repitas el mismo error. Si falta información imprescindible o persiste un '
                'bloqueo real, explícalo sin afirmar que has terminado. No menciones este aviso.')]
            return True
        # Un fragmento del buscador sirve para descubrir fuentes, no para sostener
        # una respuesta. Medido en vivo: buscó «nuevo iPhone» y convirtió rumores
        # de los snippets en hechos sin abrir una sola página. La secuencia mínima
        # queda garantizada aquí, no en la memoria del modelo.
        # Solo cuando no intentó leer nada DESPUÉS de buscar. Si lo intentó y la
        # fuente lo bloqueó, el aviso de error ya le dijo qué queda y cómo
        # responder con fragmentos: volver a exigir «abre un enlace» le hizo
        # repetir la URL con 403. Una lectura fallida anterior a buscar no cuenta,
        # aunque la búsqueda devuelva esa misma URL (pasó en vivo el 29/10).
        first = next((i for i, step in enumerate(turn.trace)
                      if step.get('tool') == 'web.search' and not step.get('failed')), None)
        attempted = first is not None and any(step.get('tool') == 'web.read'
                                              for step in turn.trace[first + 1:])
        if first is not None and not attempted and not turn.retries.web_evidence_retries:
            turn.retries.web_evidence_retries += 1
            turn.previous_reply = output['reply']
            _, untried, failed = web_links(turn.trace)
            evitar = ('Ya fallaron, no las repitas: ' + ', '.join(failed) + '. Sin probar: ' +
                      ', '.join(untried[:5]) + '. ') if failed else ''
            turn.messages = [dict(role='user', content=
                'AVISO DE HEXOS (no es la persona): solo has visto fragmentos del buscador. '
                'No son fuentes leídas y no sostienen todavía una respuesta factual. Abre '
                'AHORA al menos uno de los enlaces devueltos por web_search mediante web_read; '
                'elige el más directo o autorizado para la pregunta. ' + evitar +
                'Después responde usando solo lo que la fuente realmente diga. No menciones este aviso.')]
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
        # El texto libre no es una llamada estructurada. No inferir acciones,
        # permisos ni promesas por verbos: también aparecen en hipótesis y citas.
        return False
