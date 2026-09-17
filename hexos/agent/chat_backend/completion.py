"""Heurísticas originales de respuesta: reglas, no ejecución de herramientas."""
from __future__ import annotations

import re
from .. import catalog


# Portón del recuerdo. La política ya le pide mirar el historial antes de decir
# que no, y aun así responde «no tengo registro» sin llamar a nada —medido: de
# tres preguntas sobre el pasado buscó en una, y en otra escribió «revisando el
# historial» sin haberlo revisado. Así que lo busca HexOS, no el modelo.
# Pedir que se abra, se enseñe o se cierre. Separado de SENALA porque señalar no
# es pedir: «la 3 es la del disco» nombra, no manda abrir nada.
# Con sus erratas: escribe «mustrame» y «mustrala», sin la e. Lo que pide está
# igual de claro, y un patrón que solo acepta la ortografía correcta convierte un
# desliz de teclado en «no te entiendo».
# La respuesta habla del aviso interno en vez de a la persona.
FUGA_AVISO = re.compile(r'\baviso\s+de\s+hexos\b|\beste\s+aviso\b|\bhexos\b', re.I)


class ReplyPolicy:
    # Lo que el modelo dice haber hecho, en primera persona y en pasado. No es
    # comprensión del texto: es la forma de la frase con la que este modelo canta
    # una escritura. Si no hubo escritura en el turno, eso hay que decirlo.
    HECHO = ('guardad|anotad|apuntad|cread|registrad|reiniciad|parad|arrancad|'
             'encendid|apagad|detenid|borrad|eliminad|actualizad|ajustad|memorizad')
    ESCRITURA_DICHA = re.compile(
        # PRIMERA persona y nada más. Con «ha» valía también «el sistema ha registrado
        # múltiples eventos», que describe lo que hizo el NAS y no lo que hizo Helios:
        # saltaba la red en una revisión donde no había nada que guardar.
        # «había» es ambiguo entre yo y él, así que solo cuenta con un pronombre
        # delante —«te había preparado y guardado»—, que es como falló de verdad.
        # Y «no he guardado nada» no es una afirmación de haber guardado.
        r'(?<!no )\b(?:he|hemos|hab[íi]amos)\b(?:\s+\w+)?(?:\s+y)?\s+(?:' + HECHO + r')[oa]s?\b'
        r'|\b(?:me|te|le|lo|la|se)\s+hab[íi]a\b(?:\s+\w+)?(?:\s+y)?\s+(?:' + HECHO + r')[oa]s?\b'
        r'|\bqued[óo]\s+(?:guardad|anotad|apuntad)[oa]s?\b'
        # «he tomado nota» no lleva participio de los de arriba y es de las formas
        # más comunes con las que este modelo da por hecho lo que no hizo.
        r'|(?<!no )\b(?:he|hemos)\s+tomado\s+nota\b'
        r'|\b(?:guardad|anotad|apuntad)[oa]s?\s+en\s+una\s+nota\b', re.I)

    # Lo que dice que va a hacer AHORA y deja sin hacer. Solo verbos que tienen
    # herramienta detrás: «voy a explicarte» no es una promesa incumplida.
    PROMESA = re.compile(
        r'\b(?:voy\s+a|paso\s+a|procedo\s+a|vamos\s+a)\s+(?:\w+\s+){0,2}?'
        r'(?:revisar|consultar|mirar|comprobar|leer|ejecutar|reiniciar|parar|arrancar|'
        r'guardar|anotar|apuntar|buscar|analizar|diagnosticar|listar)\b'
        r'|\bahora\s+(?:mismo\s+)?(?:reviso|consulto|miro|compruebo|leo|ejecuto|busco|analizo)\b'
        r'|\bdame\s+un\s+momento\b|\benseguida\s+te\s+(?:digo|cuento)\b', re.I)

    # Decir que no se pudo cuando sí se pudo. Es el espejo de ESCRITURA_DICHA: esa
    # evita creerse lo que no pasó, y esta evita descreer lo que sí pasó, que hace
    # el mismo daño. Ocurre cuando una llamada buena va seguida de otra inventada:
    # la guarda rechaza la segunda y el modelo cuenta ESE fallo como el del turno.
    NEGACION = re.compile(
        r'\bno\s+(?:he\s+podido|pude|puedo|se\s+ha\s+podido|fue\s+posible|he\s+conseguido|'
        r'consegu[íi]|he\s+logrado)\b'
        r'|\bno\s+(?:se\s+)?(?:ha\s+)?(?:qued[óo]|registr[óo]|guard[óo]|complet[óo])\b'
        r'|\bha\s+fallado\b|\bno\s+lo\s+he\s+hecho\b', re.I)

    @classmethod
    def denied_success(cls, reply, trace):
        """¿Dice que no pudo y en la traza hay una escritura que sí salió?

        Devuelve las operaciones que de verdad se hicieron, para poder decirlo. No
        se le reescribe la respuesta: se añade lo que el registro sostiene.
        """
        if not isinstance(reply, str) or not cls.NEGACION.search(reply):
            return []
        return [paso for paso in trace
                if not paso.get('failed')
                and catalog.TOOLS.get(paso.get('tool'), {}).get('effect', 'read').startswith('write')
                and not (isinstance(paso.get('result'), dict) and 'error' in paso['result'])]

    @staticmethod
    def announced_without_call(reply, trace, limit=6):
        """Anuncia una herramienta concreta y ESA no se llamó.

        Más fino que mirar si hubo alguna escritura: «te muestro la nota» solo lo
        cumple note.show, no una lectura cualquiera. Las formas salen del catálogo,
        atadas a su herramienta, para que añadir una no exija acordarse de nada.
        Devuelve (frase, herramienta) o None.
        """
        if not isinstance(reply, str) or len(trace) >= limit:
            return None
        llamadas = {paso.get('tool') for paso in trace if not paso.get('failed')}
        for patron, herramienta in catalog.announcements():
            if herramienta in llamadas:
                continue
            encontrada = patron.search(reply)
            # Una pregunta no es un anuncio: «¿te la abro?» pide permiso.
            if encontrada and '?' not in reply[encontrada.end():encontrada.end() + 40].split('.')[0]:
                return encontrada.group(0), herramienta
        return None

    @classmethod
    def unfulfilled_promise(cls, reply, trace, limit=6):
        """¿Promete una acción inmediata y el turno se acaba sin hacerla?

        No es lo mismo que cantar una escritura: aquí no afirma haber hecho nada,
        dice que lo va a hacer «ahora» y luego cierra. Con margen de herramientas,
        la respuesta es devolverle el turno; sin margen, no hay nada que devolver.
        Una pregunta no es una promesa: «¿quieres que lo revise?» se queda fuera.
        """
        if not isinstance(reply, str) or len(trace) >= limit:
            return None
        cola = reply.strip()[-260:]
        encontrada = cls.PROMESA.search(cola)
        if not encontrada:
            return None
        # La frase donde aparece: si acaba en interrogación, está pidiendo permiso.
        resto = cola[encontrada.end():]
        corte = min((resto.find(c) for c in '.!?\n' if resto.find(c) >= 0), default=len(resto))
        if resto[:corte + 1].endswith('?') or '¿' in cola[:encontrada.start()][-80:]:
            return None
        return encontrada.group(0)

    @classmethod
    def unsupported_claim(cls, reply, trace):
        """¿La respuesta canta una escritura que no consta en la traza?

        No corrige lo que escribió el modelo ni adivina su intención: compara una
        afirmación con el registro de lo ejecutado. Decir «lo he guardado» no
        guarda nada, y quien lea la respuesta no tiene forma de saberlo.
        """
        if not isinstance(reply, str) or not cls.ESCRITURA_DICHA.search(reply):
            return None
        escrituras = [paso['tool'] for paso in trace
                      if catalog.TOOLS.get(paso.get('tool'), {}).get('effect') != 'read']
        if escrituras:
            return None
        return ('La respuesta dice haber guardado o cambiado algo, pero en este turno no se '
                'ejecutó ninguna operación de escritura: ' +
                ('solo lecturas (' + ', '.join(dict.fromkeys(paso['tool'] for paso in trace)) + ').'
                 if trace else 'no se ejecutó ninguna herramienta.') +
                ' Si se guardó, fue antes de este turno; compruébalo en el núcleo antes de darlo '
                'por hecho.')
