"""Recuperaciones acotadas de contexto, formato, lectura, cobertura y promesas."""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING
from .. import catalog
from ..context import native_messages
from ..decisions import InvalidDecision, validate_reply
from ..native_transport import GenerationInterrupted
from ..work import now
from .settings import PROMPT
from .state import TurnState
from .persistence import clave
from .ledger import checkpoint_messages
from .completion import ReplyPolicy

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


# La orden de la persona, no una frase del modelo: «apunta», «anótame», «toma nota».
ORDEN_DE_APUNTAR = re.compile(r'^\W*(?:\w+[,!. ]+){0,3}(?:ap[uú]nta(?:me|lo)?|an[oó]ta(?:me|lo)?|toma nota)\b', re.I)
APUNTALO = ('AVISO DE HEXOS (no es la persona): todavía no se ha guardado nada. Guarda ahora la nota '
            'con lo que ha pedido, con sus palabras y sin quitarle el día ni la hora, y después '
            'confírmaselo en una frase. No menciones este aviso.')
# También la orden de la persona: «borra la nota de la cena», «elimina esa». No «quita»,
# que igual pide cerrarla en pantalla.
ORDEN_DE_BORRAR = re.compile(r'^\W*(?:\w+[,!. ]+){0,3}(?:b[oó]rra|elim[ií]na|desc[aá]rta)(?:me|la|lo|las|los)?\b', re.I)
BORRALA = ('AVISO DE HEXOS (no es la persona): la nota sigue ahí, todavía no se ha descartado. '
           'Descártala ahora: n es su número en la lista que acabas de ver y state es descartada. '
           'Después confírmaselo en una frase. No menciones este aviso.')
SIN_LLAMADA_CHAT = ('AVISO DE HEXOS (no es la persona): la respuesta anterior dice haber guardado algo, '
                    'pero en este turno no se ejecutó ninguna escritura: no se ha guardado nada. Si la '
                    'persona pidió apuntarlo, llama ahora a la herramienta; si no lo pidió, contesta '
                    'de nuevo sin decir que lo has hecho. No menciones este aviso.')
# Un bloque cercado con al menos cinco líneas dentro. Una orden suelta (`ls -la`) no cuenta.
ENTREGA_CODIGO = re.compile(r'^```[^\n]*\n(?:[^\n]*\n){5,}', re.M)
# Se contrasta con el estado, no con la intención: la respuesta manda a la persona a una
# tarjeta y HexOS no tiene ninguna abierta. El 14/11 el E4B leyó el README, escribió en el
# chat el antes y el después y cerró con «apruébalo en la tarjeta» sin llamar a project_write.
# «Aprueba», «apruébalo»: pedir la aprobación. «Aprobaste», «aprobado» (ya ocurrió) no entran.
TARJETA_DICHA = re.compile(r'\bapru[eé]b\w*\b[^.\n]{0,80}\btarjeta\b', re.I)
SIN_TARJETA = ('AVISO DE HEXOS (no es la persona): la respuesta anterior habla de una tarjeta, pero no hay '
               'ninguna abierta: no se ha propuesto ningún cambio. Si la persona pidió crear o cambiar un '
               'fichero del proyecto, llama ahora a project_write con el cambio. Si no, contesta de nuevo '
               'sin mencionar ninguna tarjeta. No menciones este aviso.')
# También contra la traza: dice en primera persona haber creado o cambiado un fichero y en el
# turno no hay ninguna propuesta. El 14/11 el 26B, a «procede», contestó «He creado el archivo
# tools/time_tool.py» sin llamar a nada: no había fichero ni tarjeta.
FICHERO_DICHO = re.compile(
    r'(?<!no )\b(?:he|hemos)\s+(?:ya\s+)?(?:cread|escrit|modificad|cambiad|añadid|actualizad|guardad|aplicad|'
    r'corregid|arreglad|editad|reemplazad|sustituid)[oa]s?\b', re.I)
SIN_FICHERO = ('AVISO DE HEXOS (no es la persona): la respuesta anterior dice haber creado o cambiado un fichero, '
               'pero en este turno no se ha propuesto ningún cambio: no hay fichero ni tarjeta. Si la persona '
               'lo pidió, llama ahora a project_write con el cambio; solo se escribe cuando lo apruebe en la '
               'tarjeta. Si no, contesta de nuevo sin decir que lo has hecho. No menciones este aviso.')
SIN_LLAMADA = ('AVISO DE HEXOS (no es la persona): la respuesta anterior no consultó nada. Si la '
               'petición se contesta mirando algo de este PC o de los equipos, haz ahora esa lectura y '
               'contesta con lo que salga. Si era conversación y no había nada que mirar, repite tu '
               'respuesta anterior tal cual. No menciones este aviso.')


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
                'SELECT COALESCE(MAX(rowid),0) FROM esta_ventana WHERE id<>?', (turn.uid,)).fetchone()[0]
            turn.handoff = self.agent.context.save_handoff(store, turn.history, nuevo_corte)
            store.db.execute('INSERT INTO agent_state VALUES (?,?) '
                             'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                             (clave(store, 'context_boundary'), str(nuevo_corte)))
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
        # «He revisado» sin haber mirado nada: la siguiente generación empieza en una
        # lectura, como tras un reproche. Avisarle no basta, y una sola vez: si tras
        # mirar sigue afirmando algo, ya hay traza con la que contrastarlo.
        if (not turn.trace and not turn.retries.read_claim_checked
                and hasattr(self.agent.runtime, 'require_check')
                and ReplyPolicy.LECTURA_DICHA.search(output.get('reply') or '')):
            turn.retries.read_claim_checked = True
            self.agent.runtime.require_check()
            turn.messages = [dict(role='user', content='AVISO DE HEXOS (no es la persona): '
                + ReplyPolicy.unsupported_claim(output['reply'], []) + ' No menciones este aviso.')]
            return True
        # El selector dijo que este mensaje necesitaba herramientas y el turno acaba sin
        # llamar a ninguna. No se mira qué dice la respuesta: esa vía, la de las frases,
        # se retiró a propósito. La señal es de estructura, y solo en la ventana Agente,
        # donde lo pedido es actuar. Con historial delante el E4B cerraba así 3 de 9
        # turnos («usaré journalctl…») que en limpio resolvía. Una vez, y arrancando en
        # una lectura: decirle que llame no bastaba.
        # Una respuesta que trae un bloque de código es la entrega, no un «voy a mirarlo»:
        # también es estructura, no una frase. Devolverla hacía generar dos veces cada
        # página (el 26B, 28-42 s más por turno y el contexto recargado entero) y en un
        # caso lo empujó a llamar a project_files sin proyecto: cinco generaciones.
        if (not turn.trace and turn.grupos_pedidos and not turn.retries.sin_llamada_devuelto
                and getattr(self.agent, 'ventana', None) == 'agente'
                and not ENTREGA_CODIGO.search(output.get('reply') or '')
                and hasattr(self.agent.runtime, 'require_check')):
            turn.retries.sin_llamada_devuelto = True
            # Sin forzar el arranque en una lectura. Forzado, una charla en la ventana
            # Agente («¿y qué echas en falta?» -> «¿por ejemplo?») perdía su respuesta:
            # obligado a llamar a algo llamaba a task_current y contestaba «No tengo un
            # encargo activo». Ahora se le avisa y elige; si tampoco consulta nada, más
            # abajo se entrega la primera respuesta.
            turn.retries.respuesta_devuelta = output.get('reply') or ''
            turn.retries.traza_al_devolver = len(turn.trace)
            turn.messages = [dict(role='user', content=SIN_LLAMADA)]
            return True
        if (not turn.retries.tarjeta_devuelta and getattr(self.agent, 'ventana', None) == 'agente'
                and TARJETA_DICHA.search(output.get('reply') or '')
                and not getattr(self.agent, 'project_request', None)
                and not getattr(self.agent, 'system_request', None)
                and not getattr(self.agent.session, 'notas_interfaz', None)
                and not any(paso.get('tool') in ('project.write', 'system.package_plan') for paso in turn.trace)):
            turn.retries.tarjeta_devuelta = True
            turn.messages = [dict(role='user', content=SIN_TARJETA)]
            return True
        if (not turn.retries.fichero_devuelto and getattr(self.agent, 'ventana', None) == 'agente'
                and getattr(self.agent, 'proyecto', None) and not turn.decidido_en_tarjeta
                and FICHERO_DICHO.search(output.get('reply') or '')
                and not any(catalog.TOOLS.get(paso.get('tool'), {}).get('effect') != 'read'
                            or paso.get('tool') == 'project.write' for paso in turn.trace)):
            turn.retries.fichero_devuelto = True
            if hasattr(self.agent.runtime, 'active_groups'):
                activos = list(getattr(self.agent.runtime, 'active_groups', None) or [])
                self.agent.runtime.active_groups = activos if 'proyecto' in activos else activos + ['proyecto']
            turn.messages = [dict(role='user', content=SIN_FICHERO)]
            return True
        # La persona ordenó apuntar algo, el selector declaró las notas y el turno acaba
        # sin guardar nada. Aquí no se mira la respuesta sino la orden, que es suya, y la
        # traza. Se arranca directamente en la escritura: es lo que ha pedido.
        if (not turn.retries.sin_llamada_devuelto
                and getattr(self.agent, 'ventana', None) == catalog.DEFAULT_WINDOW
                and 'notas' in (turn.grupos_pedidos or ())
                and ORDEN_DE_APUNTAR.search(turn.text or '')
                and not any(paso.get('tool') == 'note.save' for paso in turn.trace)
                and hasattr(self.agent.runtime, 'require_note')):
            turn.retries.sin_llamada_devuelto = True
            if self.agent.runtime.require_note():
                turn.messages = [dict(role='user', content=APUNTALO)]
                return True
        # Lo mismo con borrar: la persona lo ordenó, el modelo buscó la nota, la encontró y
        # cerró el turno con «Voy a descartar la nota…» sin descartarla (medido 3 de 3 con
        # el E4B). Solo si en este turno hay una lista con algo: sin nota a la vista no se
        # arranca una escritura a ciegas.
        if (not turn.retries.sin_llamada_devuelto
                and getattr(self.agent, 'ventana', None) == catalog.DEFAULT_WINDOW
                and 'notas' in (turn.grupos_pedidos or ())
                and ORDEN_DE_BORRAR.search(turn.text or '')
                and not any(paso.get('tool') == 'note.mark' for paso in turn.trace)
                and any(paso.get('tool') == 'note.list' and not paso.get('failed')
                        and isinstance(paso.get('result'), dict) and paso['result'].get('total')
                        for paso in turn.trace)
                and hasattr(self.agent.runtime, 'require_note')):
            turn.retries.sin_llamada_devuelto = True
            if self.agent.runtime.require_note('note.mark'):
                turn.messages = [dict(role='user', content=BORRALA)]
                return True
        # En el chat no vale la señal del selector: allí se habla DE las notas sin pedir
        # nada («y notas tienes, ¿verdad?»), y devolver ese turno cambió una respuesta
        # buena por «Entendido. Estoy atento a cualquier instrucción…» el 11/11. Solo se
        # devuelve lo que se puede contrastar con la traza: la respuesta afirma haber
        # guardado algo y en el turno no consta ninguna escritura («apunta que el viernes
        # tengo dentista» -> «He apuntado…» sin una llamada). Sin forzar el arranque,
        # que solo deja leer; y una vez.
        if (not turn.retries.sin_llamada_devuelto
                and getattr(self.agent, 'ventana', None) == catalog.DEFAULT_WINDOW
                and getattr(self.agent.runtime, 'native', False)
                and ReplyPolicy.ESCRITURA_DICHA.search(output.get('reply') or '')
                and not any(catalog.TOOLS.get(paso.get('tool'), {}).get('effect') != 'read'
                            for paso in turn.trace)):
            turn.retries.sin_llamada_devuelto = True
            turn.retries.respuesta_devuelta = output.get('reply') or ''
            turn.retries.traza_al_devolver = len(turn.trace)
            # Si el selector no pidió las notas, la herramienta ni estaba declarada y
            # repetir no podía servir: «Anotado. Te he apuntado…» dos veces sin llamar.
            # Para la repetición se declara todo lo que el chat permite.
            if hasattr(self.agent.runtime, 'active_groups'):
                self.agent.runtime.active_groups = list(catalog.groups_in(catalog.DEFAULT_WINDOW))
            turn.messages = [dict(role='user', content=SIN_LLAMADA_CHAT)]
            return True
        # Se devolvió y la repetición tampoco hizo nada: lo que sale entonces es una
        # contestación al aviso («Entendido. No he guardado nada en este turno»), peor
        # que la primera, que solía ser buena. Se entrega la primera, y el contexto del
        # modelo se vacía para que el aviso y su contestación no se queden en la
        # conversación: el turno siguiente la reconstruye desde el archivo.
        if (turn.retries.respuesta_devuelta is not None
                and len(turn.trace) == turn.retries.traza_al_devolver):
            output['reply'] = turn.retries.respuesta_devuelta
            turn.retries.respuesta_devuelta = None
            self.agent.runtime.call({'type': 'reset'})
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
