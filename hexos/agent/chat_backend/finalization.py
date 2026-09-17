"""Clasificación, efectos de interfaz heredados y persistencia del cierre."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import uuid4
from .. import notes
from ..work import KINDS, now, string, strings
from .completion import FUGA_AVISO
from .references import PEDIR_CERRAR, PEDIR_VER, NOTA_MENCIONADA
from .recovery import RETRY
from .state import TurnState

if TYPE_CHECKING:
    from .agent import Agent


class TurnFinalizer:
    def __init__(self, agent: Agent):
        self.agent = agent

    def classify(self, store, turn: TurnState, output: dict, clarification):
        proposed = output['work']
        if clarification:
            self.agent.tool(store, 'task.focus', clarification, turn_id=turn.uid)
        job = None
        if proposed is not None:
            if not isinstance(proposed, dict) or set(proposed) != {'title','kind','scope','tags','reason'}:
                if turn.retries.schema_retries == 0:
                    turn.retries.schema_retries += 1
                    turn.messages = [dict(role='user', content=
                        'Respuesta rechazada por esquema: work debe ser null o una clasificación '
                        'con title,kind,scope,tags,reason. No se ha ejecutado ninguna acción '
                        'por esa respuesta. Para ejecutar una herramienta devuelve tool y arguments; '
                        'para responder devuelve reply y work. Corrige el formato.')]
                    return RETRY
                raise ValueError('Clasificación propuesta inválida')
            if proposed['kind'] not in KINDS:
                raise ValueError('Tipo propuesto inválido')
            string(proposed['title'], 'title', 200)
            string(proposed['scope'], 'scope', 200)
            strings(proposed['tags'], 'tags')
            string(proposed['reason'], 'reason')
            job = store.dispatch(dict(op='create', title=proposed['title'],
                request=turn.prompt_text, source_ref='turn:' + turn.uid), actor='user')
            job = store.dispatch(dict(op='classify', id=job['id'], revision=job['revision'],
                **{k:v for k,v in proposed.items() if k != 'title'}), actor='model')
        return job

    def finish(self, store, turn: TurnState, output: dict, job) -> dict:
        # Señaló una nota, HexOS la resolvió, y el modelo respondió sin
        # abrirla —preguntando a cuál se refería, con el id delante—. No hay
        # nada que insistirle: no afirmó nada. Así que la abre HexOS y lo
        # dice, igual que busca en el archivo cuando la pregunta mira atrás.
        cerrar = bool(PEDIR_CERRAR.search(turn.text or ''))
        ya_actuado = any(paso.get('tool') in ('note.show', 'note.hide') for paso in turn.trace)
        # «Cierra la nota» no señala a ninguna en concreto, y no hace
        # falta: cerrar sin id cierra las abiertas, que es lo que pide.
        # Abrir sí necesita saber cuál, así que ahí no hay atajo.
        if cerrar and not turn.pointed_note and not ya_actuado and NOTA_MENCIONADA.search(turn.text or ''):
            turn.trace.append(dict(tool='note.hide', arguments={}, effect='read',
                              changes_state=False, ts=now(), seconds=0.0, failed=False,
                              verification='no_requerida',
                              result=dict(hidden='todas', requested_by='hexos',
                                          note='Las cerró HexOS: pidió cerrar y el turno '
                                               'iba a terminar preguntando cuál.')))
            store.db.execute('INSERT INTO tool_events(turn_id,ts,body) VALUES (?,?,?)',
                             (turn.uid, now(), json.dumps(turn.trace[-1], ensure_ascii=False)))
            store.db.commit()
            output['reply'] = (output['reply'].rstrip() +
                               '\n\n· No hacía falta preguntar: he cerrado lo que estaba abierto.')
            ya_actuado = True
        if (turn.pointed_note and (cerrar or PEDIR_VER.search(turn.text or ''))
                and not ya_actuado):
            hecho = ('cerró' if cerrar else 'abrió')
            resultado = (dict(hidden=turn.pointed_note['id']) if cerrar else
                         dict(notes.get(store, turn.pointed_note['id']), shown=True))
            turn.trace.append(dict(tool='note.hide' if cerrar else 'note.show',
                              arguments=dict(id=turn.pointed_note['id']),
                              effect='read', changes_state=False, ts=now(), seconds=0.0,
                              failed=False, verification='no_requerida',
                              result=dict(resultado, requested_by='hexos',
                                          note='La ' + hecho + ' HexOS al ver que la persona '
                                               'señalaba una nota concreta y el turno iba a '
                                               'cerrarse sin hacerlo.')))
            store.db.execute('INSERT INTO tool_events(turn_id,ts,body) VALUES (?,?,?)',
                             (turn.uid, now(), json.dumps(turn.trace[-1], ensure_ascii=False)))
            store.db.commit()
            output['reply'] = (output['reply'].rstrip() +
                               '\n\n· No hacía falta preguntar: he ' +
                               ('cerrado' if cerrar else 'abierto') + ' «' +
                               turn.pointed_note.get('title', '') + '» en tu pantalla.')
        # El aviso es maquinaria interna y la persona no tiene por qué leerlo.
        # Pasó: tras un aviso contestó «Tomo nota de este aviso de HexOS»
        # en vez de responderle a ella. Si la respuesta habla del aviso,
        # se descarta y se conserva la de antes, que al menos iba dirigida
        # a la persona; el reparo del cierre ya dirá lo que no se sostiene.
        if turn.previous_reply is not None and FUGA_AVISO.search(output['reply']):
            output['reply'] = turn.previous_reply
        # Salió bien y lo cuenta como que no pudo: se dice lo que consta.
        hechas = self.agent.denied_success(output['reply'], turn.trace)
        if hechas:
            detalle = ', '.join(dict.fromkeys(
                paso['tool'] + (' (' + str((paso.get('result') or {}).get('saved')
                                           or (paso.get('result') or {}).get('name')
                                           or (paso.get('result') or {}).get('identified') or '') + ')'
                                if isinstance(paso.get('result'), dict) else '')
                for paso in hechas))
            output['reply'] = (output['reply'].rstrip() +
                               '\n\n· Aun así, esto sí quedó hecho: ' + detalle + '.')
        recordado = self.agent.harvest_facts(store, turn.text, turn.uid, turn.trace)
        if recordado:
            output['reply'] = output['reply'].rstrip() + '\n\n' + recordado
        store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
            (uuid4().hex, now(), 'assistant', output['reply'], output['reply']))
        store.db.commit()
        # El siguiente bloque ya tiene este turno archivado: el traspaso solo
        # existe para cruzar el corte o sobrevivir a un reinicio a mitad de turno.
        self.agent.context.consume_handoff(store, turn.handoff)
        corte_avisado, self.agent.context_cut = self.agent.context_cut, None
        return dict(reply=output['reply'], work=job, document=turn.document, tools=turn.trace, context_sources=turn.context_sources, progress=self.agent.progress,
            context_cut=corte_avisado, closure=self.agent.closure(turn.trace, output['reply']),
            diagnostics=dict(format_retries=turn.retries.format_retries, schema_retries=turn.retries.schema_retries,
                             recovery_requests=turn.retries.recovery_requests))
