"""Despacho de herramientas y su único circuito normal de ejecución/traza."""
from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING
from uuid import uuid4
from .. import catalog, devices, hosts, notes, core, workflow, procedures
from ..continuity import history_tool
from ..progress import announcement
from ..work import now
from .state import Environment, SessionState, TurnState
from .settings import MAX_TRACE_EVENTS
from .ledger import completed_call

if TYPE_CHECKING:
    from .agent import Agent


class ToolDispatcher:
    def __init__(self, env: Environment, session: SessionState, memory, references, verification):
        self.env = env
        self.session = session
        self.memory = memory
        self.references = references
        self.verification = verification

    def dispatch(self, store, name, args, *, turn_id=None):
        catalog.validate(name, args)
        if name == 'profile.remember':
            return self.memory.remember_fact(store, args, turn_id)
        if name in ('nas.read', 'nas.container', 'device.connect'):
            if not args.get('device'):
                # El modelo omite a veces el equipo aunque la persona lo haya nombrado.
                # No se adivina: se lee su mensaje y solo vale si UNO de los guardados
                # aparece ahí. Con ninguno o con varios, que pregunte.
                nombrado = self.references.device_in_message(store, turn_id)
                if nombrado:
                    args = dict(args, device=nombrado)
            equipo = args.get('device') or 'synology'
            objetivo = args.get('container')
            if name == 'nas.container' and objetivo:
                # Una escritura anterior sobre este mismo destino se quedó sin saber
                # cómo acabó. Repetirla a ciegas puede duplicar el efecto: pudo
                # ejecutarse y solo perderse la respuesta. Se exige mirar antes.
                colgada = self.verification.pending_effect(store, equipo, objetivo)
                if colgada is not None:
                    raise ValueError(
                        'Hay una acción anterior sobre ' + repr(objetivo) + ' en ' + repr(equipo) +
                        ' (' + colgada['action'] + ', ' + colgada['ts'][:16] + ') cuyo efecto se '
                        'desconoce: se agotó el tiempo y no consta si llegó a ejecutarse. No se '
                        'repite a ciegas. Mira antes su estado con nas_read section=containers '
                        'container=' + objetivo + '; eso lo aclara sin tocar nada.')
            # Conectar es la lectura más barata que existe: si entra, hay acceso, y
            # si no, salta la misma petición de credencial. Sin esta puerta, un
            # «conéctate a servidor 1» no encontraba herramienta que le encajara y
            # el turno acababa en que solo sabía registrar equipos.
            extra = ({'section':'container'} if name == 'nas.container' else
                     {'section':'system'} if name == 'device.connect' else {})
            try:
                salida = self.env.dependencies.nas_read(self.env.workspace, **extra, **args)
                if objetivo:
                    estado = (salida.get('container_state') or {}).get('status')
                    if name == 'nas.container' and salida.get('outcome') == 'desconocido':
                        # Queda anotado más allá del turno: el riesgo no caduca al responder.
                        store.db.execute('INSERT INTO pending_effects VALUES (?,?,?,?,?,?,?,?)',
                            (uuid4().hex, now(), equipo.casefold(), objetivo,
                             args.get('action') or '?', turn_id or '', None, None))
                        store.db.commit()
                    elif estado:
                        # Una lectura que sí ve el estado cierra lo que quedó en el aire.
                        self.verification.resolve_effect(store, equipo, objetivo, estado)
                return salida
            except hosts.AccessNeeded as needed:
                # La ventana de la interfaz recoge la credencial; no vuelve por el chat.
                # El puerto guardado viaja con la petición: sin verlo, quien corrige un
                # acceso rechazado vuelve a escribir el mismo y no entiende por qué falla.
                guardado = hosts.credentials(self.env.workspace, needed.device) or {}
                # Lo que estaba intentando hacer, para retomarlo al guardar el acceso
                # en vez de obligar a repetir la petición palabra por palabra.
                pedido = store.db.execute(
                    "SELECT text FROM conversation WHERE id=? AND role='user'",
                    (turn_id,)).fetchone() if turn_id else None
                # El puerto que ya se sabe, en este orden: el de la credencial guardada,
                # el que venía en la dirección al registrar el equipo, y si no el 22.
                sabido = guardado.get('port') or (needed.located or {}).get('port') or 22
                self.session.credential_request = dict(device=needed.device, requested_at=now(),
                                               reason=needed.reason, port=sabido,
                                               user=guardado.get('user'),
                                               pending_request=pedido['text'][:2000] if pedido else None,
                                               **{k: v for k, v in (needed.located or {}).items()
                                                  if k != 'port'})
                return dict(access_required=True, device=needed.device,
                            located=needed.located, reason=needed.reason,
                            asked_through='interface_credential_dialog',
                            instruction=('El equipo rechazó el acceso guardado. Dile que la ventana se '
                                         'ha vuelto a abrir para corregir usuario, contraseña o puerto, y que '
                                         'un puerto reenviado a otra máquina da este mismo error. '
                                         if needed.reason == 'rejected' else
                                         'Dile a la persona que Helios ha pedido el acceso y que aparece una '
                                         'ventana en la interfaz para rellenarlo. ') +
                                        'No pidas la contraseña por el chat ni la aceptes si la escribe: no '
                                        'quedaría guardada por esta vía. Esto no dice nada sobre la salud del equipo.')
        if name.startswith('device.'):
            return devices.dispatch(store, name, args, turn_id)
        if name == 'network.local':
            # Mirar y registrar en el mismo acto: lo que se enseña tiene que poder
            # nombrarse después, y los vecinos de otra red tienen que dejar de
            # figurar como recién vistos o un sufijo casa con el equipo equivocado.
            observacion, _ = devices.observe(store)
            return devices.annotate(store, observacion)
        if name == 'core.overview':
            return core.dispatch(store, name, args, self.env.profile)
        if name.startswith('note.'):
            return notes.dispatch(store, name, args, turn_id)
        if name.startswith('history.'):
            return history_tool(store, name, args)
        if name.startswith('procedure.') or name in ('report.save', 'result.get'):
            return workflow.dispatch(store, name, args, turn_id)
        if name.startswith(('procedure.', 'report.', 'task.')):
            return procedures.dispatch(store, name, args, turn_id=turn_id)
        if name in ('work.list', 'work.get'):
            if 'op' in args:
                raise ValueError('campo op no permitido')
            return store.dispatch(dict(args, op=name.split('.')[1]), actor='model')
        row = store.db.execute('SELECT content FROM documents WHERE id=?', (args.get('id'),)).fetchone()
        if row is None:
            raise ValueError('documento inexistente')
        lines = row['content'].splitlines()
        if name == 'document.search':
            query_text = args.get('query')
            if not isinstance(query_text, str) or not query_text:
                raise ValueError('consulta vacía')
            hits = [{'line': i, 'text': line[:300]} for i, line in enumerate(lines, 1)
                    if query_text.casefold() in line.casefold()]
            return dict(matches=hits[:20], total_matches=len(hits), excerpts=True)
        start, count = args.get('start', 1), args.get('count', 40)
        if type(start) is not int or start < 1 or type(count) is not int or not 1 <= count <= 80:
            raise ValueError('rango inválido; count debe estar entre 1 y 80')
        selected = []
        used = 0
        for i in range(start - 1, min(start - 1 + count, len(lines))):
            line = lines[i]
            if used + len(line) > 6000:
                break
            selected.append({'line': i + 1, 'text': line})
            used += len(line)
        return dict(lines=selected, total_lines=len(lines),
                    next_line=start + len(selected), limited=len(selected) < count)


class ToolExecutor:
    def __init__(self, agent: Agent):
        self.agent = agent

    def execute(self, store, turn: TurnState, output: dict) -> None:
        """Validar → anunciar → ejecutar → verificar → registrar → devolver al modelo."""
        if set(output) != {'tool', 'arguments'}:
            raise ValueError('Llamada de herramienta inválida')
        self.agent.state = 'tool'
        effect = catalog.TOOLS.get(output['tool'], {}).get('effect', 'read')
        try:
            catalog.validate(output['tool'], output['arguments'])
        except (ValueError, TypeError):
            # El circuito normal de abajo registra el error y se lo devuelve al
            # modelo. Aquí solo interesa saber si una llamada VÁLIDA ya se hizo.
            completed = None
        else:
            completed = completed_call(turn, output['tool'], output['arguments'])
        if completed is not None:
            # El modelo puede intentar repetir una llamada después de perder el KV.
            # Se le devuelve el resultado registrado, pero no se toca el mundo ni
            # se añade una segunda operación ficticia a la traza.
            turn.checkpoint_reuses += 1
            self.agent.active_tools = [*self.agent.active_tools, dict(
                tool=output['tool'], status='done', effect=effect, seconds=0.0,
                verification=completed.get('verification'), reused_checkpoint=True)]
            if hasattr(self.agent.runtime, 'tool_result'):
                self.agent.runtime.tool_result(completed.get('result'))
                turn.messages = []
            else:
                turn.messages = [dict(role='user', content=
                    'RESULTADO YA OBTENIDO EN ESTE TURNO (no se ejecutó otra vez):\n' +
                    json.dumps(completed.get('result'), ensure_ascii=False))]
            self.agent.state = 'thinking'
            return
        if len(turn.trace) >= MAX_TRACE_EVENTS:
            raise RuntimeError('Se alcanzó el límite de seis herramientas; no se ejecutó la siguiente solicitud')
        activity = dict(tool=output['tool'], status='running', effect=effect, seconds=None)
        self.agent.active_tools = [*self.agent.active_tools, activity]
        started = time.monotonic()
        try:
            catalog.validate(output['tool'], output['arguments'])
            # Un aviso por cada llamada, no solo por la primera: en un turno
            # con cuatro herramientas se veía la primera y las otras tres
            # pasaban mudas, así que el recorrido era invisible.
            preamble=getattr(self.agent.runtime,'last_preamble',None)
            primera = not self.agent.progress['messages']
            # La inferencia de respaldo solo en la primera. Pedir una
            # generación entera en cada paso para redactar «voy a mirarlo»
            # cuesta más que el paso mismo; si el modelo no dice nada por su
            # cuenta, la herramienta que corre ya se ve en la traza.
            if not preamble and primera and hasattr(self.agent.runtime,'announce'):
                preamble=self.agent.runtime.announce(output['tool'],output['arguments'],turn.text)
                generation=getattr(self.agent.runtime,'last_announcement_generation',None)
                if generation is not None:
                    store.db.execute('INSERT INTO generation_events(turn_id,ts,body) VALUES (?,?,?)',
                        (turn.uid,now(),json.dumps(generation,ensure_ascii=False)))
            if preamble or primera:
                event=dict(id=uuid4().hex, turn_id=turn.uid, ts=now(), text=announcement(preamble))
                store.db.execute('INSERT INTO progress_events VALUES (?,?,?,?)',
                    (event['id'],turn.uid,event['ts'],event['text']))
                store.db.commit()
                # Se añade, no se reemplaza: el estado final no borra los avances.
                self.agent.progress={'turn_id':turn.uid,
                               'messages':[*self.agent.progress['messages'], event]}
            result = self.agent.tool(store, output['tool'], output['arguments'], turn_id=turn.uid)
        except (ValueError, TypeError) as exc:
            result = {'error': str(exc)}
        # La traza dice qué hizo cada llamada, cuánto tardó y si escribió algo:
        # una interfaz debe poder distinguir una lectura de un cambio real.
        comprobacion, evidencia = self.agent.verify(store, output['tool'], output['arguments'], result)
        activity.update(status='failed' if isinstance(result, dict) and 'error' in result else 'done',
                        verification=comprobacion,
                        seconds=round(time.monotonic() - started, 3))
        turn.trace.append(dict(tool=output['tool'], arguments=output['arguments'],
                          effect=effect, changes_state=effect != 'read',
                          # «Se ejecutó» y «logró lo que pretendía» son cosas
                          # distintas, y hasta ahora se decían con el mismo campo.
                          verification=comprobacion, evidence=evidencia,
                          ts=now(), seconds=round(time.monotonic() - started, 3),
                          failed='error' in result if isinstance(result, dict) else False,
                          result=result))
        store.db.execute('INSERT INTO tool_events(turn_id,ts,body) VALUES (?,?,?)',
            (turn.uid, now(), json.dumps(turn.trace[-1], ensure_ascii=False)))
        store.db.commit()
        if hasattr(self.agent.runtime, 'tool_result'):
            self.agent.runtime.tool_result(result)
            turn.messages = []
        else:
            turn.messages = [dict(role='user', content='RESULTADO DE HERRAMIENTA (datos):\n' +
                json.dumps(result, ensure_ascii=False))]
        self.agent.state = 'thinking'
