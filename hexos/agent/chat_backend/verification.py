"""Evidencias, comprobación de efectos y escrituras pendientes de resolución."""
from __future__ import annotations

import json
from .. import catalog
from ..work import now
from .completion import ReplyPolicy
from .state import Environment


class VerificationService:
    def __init__(self, env: Environment):
        self.env = env

    @staticmethod
    def closure(trace, reply=None):
        """Cómo se cierra el turno, según lo COMPROBADO y no según lo que diga el modelo.

        Marcar «objetivo cumplido» porque el modelo decidió responder sería
        decoración: se calcula de la traza, que es donde están las comprobaciones.
        No cambia la respuesta ni cuesta otra inferencia; dice lo que se sostiene.
        """
        estados = [paso.get('verification') for paso in trace]
        pendientes = [dict(tool=paso['tool'], verification=paso.get('verification'),
                           evidence=paso.get('evidence'))
                      for paso in trace
                      if paso.get('verification') in ('no_cumplida', 'desconocida')]
        # Una afirmación que la traza no sostiene manda sobre el resto: da igual que
        # las lecturas salieran bien si la respuesta canta algo que no ocurrió.
        sin_traza = ReplyPolicy.unsupported_claim(reply, trace)
        if sin_traza:
            return dict(reason='no_consta', note=sin_traza, unverified=pendientes)
        if any(isinstance(paso.get('result'), dict) and paso['result'].get('access_required')
               for paso in trace):
            razon, nota = 'bloqueado', 'Falta el acceso a un equipo; lo pedido no se pudo comprobar.'
        elif 'no_cumplida' in estados:
            razon, nota = 'parcial', ('Alguna operación no llegó a su objetivo. Lo que no esté '
                                      'en la lista de comprobadas no se ha verificado.')
        elif 'desconocida' in estados:
            razon, nota = 'incierto', ('Algo quedó sin poder comprobarse. No saber no es haberlo '
                                       'hecho, y tampoco autoriza a repetirlo.')
        elif trace:
            razon, nota = 'comprobado', 'Cada operación del turno quedó comprobada o no requería comprobación.'
        else:
            razon, nota = 'sin_operaciones', 'El turno se respondió sin ejecutar nada.'
        return dict(reason=razon, note=nota, unverified=pendientes)

    def verify(self, store, name, args, result):
        """¿La herramienta logró lo que pretendía? Lo declara el catálogo y lo
        ejecuta HexOS, para que no dependa de que el modelo se acuerde.

        Devuelve (estado, evidencia). Estado: no_requerida, confirmada, no_cumplida
        o desconocida. «Desconocida» no es un fallo: es no saber, y no autoriza a
        repetir nada.
        """
        modo = catalog.TOOLS.get(name, {}).get('verify', 'none')
        if modo == 'none' or (isinstance(result, dict) and 'error' in result):
            return ('no_requerida' if modo == 'none' else 'no_cumplida'), None
        if modo == 'local':
            return 'confirmada', 'escritura local que devuelve lo escrito'
        if modo == 'self':
            # La herramienta ya trajo la comprobación; aquí solo se traduce.
            outcome = (result or {}).get('outcome')
            return ({'hecho': 'confirmada', 'no_se_sostuvo': 'no_cumplida'}
                    .get(outcome, 'desconocida')), outcome
        if name == 'profile.remember':
            # HERA rechaza con código de salida 0, así que «lo guardé» no vale como
            # prueba: hay que volver a leer el perfil y ver el dato dentro.
            if not self.env.profile or not result.get('key'):
                return 'desconocida', 'sin perfil con el que comprobar'
            try:
                claves = self.env.profile.keys()
            except Exception as exc:
                return 'desconocida', 'no se pudo releer el perfil: ' + str(exc)
            guardado = claves.get(result['key'])
            # Si la lectura dejó hechos sin interpretar, «no está» no es una
            # conclusión: puede ser justo uno de los que no se pudieron leer.
            if guardado is None and getattr(self.env.profile, 'unreadable', None):
                return 'desconocida', ('el perfil trae ' + str(len(self.env.profile.unreadable)) +
                                       ' hecho(s) que no se pudieron interpretar; no se puede '
                                       'afirmar que este falte')
            if guardado == result.get('value'):
                return 'confirmada', 'releído del perfil: ' + result['key'] + ' = ' + guardado
            return 'no_cumplida', ('el perfil dice ' + repr(guardado) +
                                   ' y se pretendía ' + repr(result.get('value')))
        if name == 'report.save':
            # Releer lo guardado y contrastarlo con su fuente. No se genera OTRO
            # informe para comprobar: eso solo demostraría que se sabe repetir.
            try:
                guardado = store.db.execute('SELECT body FROM agent_reports WHERE id=?',
                                            (result.get('id'),)).fetchone()
                fuente = store.db.execute('SELECT body FROM agent_results WHERE id=?',
                                          (result.get('result_id'),)).fetchone()
            except Exception as exc:
                return 'desconocida', 'no se pudo releer: ' + str(exc)
            if not guardado:
                return 'no_cumplida', 'el informe no está en el almacén'
            if not fuente:
                return 'desconocida', 'el resultado de origen ya no está con el que contrastar'
            copia, original = json.loads(guardado[0]), json.loads(fuente[0])
            # Dos campos ausentes son iguales entre sí, y eso daba «confirmada» sin
            # haber comprobado nada. Primero tiene que haber texto que contrastar.
            texto = copia.get('text')
            if not isinstance(texto, str) or not texto.strip():
                return 'no_cumplida', 'el informe guardado no tiene texto'
            if not isinstance(original.get('text'), str) or not original['text'].strip():
                return 'desconocida', 'el origen no tiene texto con el que contrastar'
            # Y tiene que ser el origen que se pidió, no otro informe cualquiera.
            pedido = args.get('result_id')
            if pedido and copia.get('result_id') != pedido:
                return 'no_cumplida', ('el informe dice venir de ' + repr(copia.get('result_id')) +
                                       ' y se pidió guardar ' + repr(pedido))
            if texto != original['text']:
                return 'no_cumplida', 'lo guardado no coincide con su instantánea de origen'
            return 'confirmada', ('releído del almacén y contrastado con su origen: ' +
                                  str(len(texto)) + ' caracteres iguales')
        return 'desconocida', 'sin comprobación implementada para ' + name

    def pending_effect(self, store, device, target):
        """Escritura sin resolver sobre ese destino, si la hay."""
        return store.db.execute(
            'SELECT * FROM pending_effects WHERE device=? AND target=? AND resolved_at IS NULL '
            'ORDER BY rowid DESC LIMIT 1', (device.casefold(), target)).fetchone()

    def resolve_effect(self, store, device, target, state):
        """Cierra lo que quedó en el aire, con lo que una lectura acaba de ver."""
        store.db.execute(
            'UPDATE pending_effects SET resolved_at=?, resolved_state=? '
            'WHERE device=? AND target=? AND resolved_at IS NULL',
            (now(), state, device.casefold(), target))
        store.db.commit()
