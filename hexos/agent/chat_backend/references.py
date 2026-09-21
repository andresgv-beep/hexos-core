"""Resolución de referencias a equipos/notas y cobertura del encargo."""
from __future__ import annotations

import json
import re
from .. import hosts, notes
from .state import Environment
from .file_requests import explicit_directory_read, explicit_share_read


# `ver` pedía un límite: con `ver\w*` casaba con «versión», y «la última versión
# de iOS» abría una nota del NAS en mitad de una búsqueda web. Los verbos que
# admiten pronombre lo llevan explícito; los demás cierran en el límite.
PEDIR_VER = re.compile(
    r'\b(?:[áa]bre(?:la|lo|las|los|me)?|abrir|mu[eé]?stra(?:me|la|lo|las|los|mela)?|mostrar|'
    r'ens[eé]?[ñn]a(?:me|la|lo|mela)?|ense[ñn]ar|saca(?:la|lo|me)?|sacar|'
    r'ver(?:la|lo|las|los)?|verme|veo)\b', re.I)
# Aparte, porque el atajo tiene que llamar a la herramienta que toca: con las dos
# juntas «ciérrala» abría la nota, que es peor que no hacer nada.
# Habla de notas, aunque no señale a ninguna: «cierra la nota», «cierra todo».
NOTA_MENCIONADA = re.compile(r'\b(?:notas?|todo|todas)\b', re.I)


PEDIR_CERRAR = re.compile(
    r'\b(?:cierra|cerrar|ci[ée]rra|oculta|ocultar|quita|quitar|recoge|recoger)\w*\b', re.I)


class ReferenceResolver:
    def __init__(self, env: Environment):
        self.env = env

    # Lo que la persona pide de cada equipo, por la palabra con la que lo pide.
    # No es clasificar por ella: está escrito en su mensaje.
    SECCIONES = ((re.compile(r'\bdiagn[oó]st[ií]c\w*|\bsalud\b|\bestado\s+(?:general|del\s+sistema)\b', re.I), 'diagnosis'),
                 (re.compile(r'\bcontenedor|\bdocker\b', re.I), 'containers'),
                 (re.compile(r'\bespacio\b|\bcu[áa]nto\s+(?:queda|cabe)\b|\bllen[oa]s?\b', re.I), 'space'))
    # Referencia inequívoca al equipo del turno inmediatamente anterior. No vale
    # un «él» suelto ni se busca arbitrariamente hacia atrás: solo estas formas y
    # solo si el último turno de la persona registró un servidor con éxito.
    DEVICE_DEIXIS = re.compile(
        r'\ba\s+(?:[ée]l|ese|este)\b|\b(?:ese|este)\s+(?:servidor|equipo)\b|'
        r'\b(?:diagnost[ií]ca|revisa|comprueba|conecta)(?:lo|le)\b', re.I)

    # Señalar sin nombrar: «ábrela», «esa», «la 3», «la última». Es deixis, y el
    # modelo no la resuelve —pide aclaración a algo que él mismo acaba de nombrar—.
    # Pero HexOS sí sabe de qué se está hablando: lo tiene en la traza del turno
    # anterior. Se le da resuelto COMO DATO; decidir sigue siendo suyo.
    # Dos familias, y la diferencia importa. Los pronombres pegados al verbo
    # —«ábrela», «ciérrala»— solo pueden referirse a algo ya nombrado: valen
    # solos. Los señaladores genéricos —«la última», «la 3»— son ambiguos: «la
    # última versión de iOS» abrió una nota del NAS en mitad de una búsqueda web.
    # Esos solo cuentan si CIERRAN la frase, porque un señalador seguido de
    # sustantivo no señala: es el determinante de ese sustantivo.
    PRONOMBRE = re.compile(
        r'\b(?:[áa]brel[oa]|ci[ée]rral[oa]|mu[eé]?stramela|mu[ée]strala|ens[eé]?[ñn]amela|'
        r'ens[ée][ñn]ala|d[ée]jamela|qu[íi]tala)\b', re.I)
    GENERICO = re.compile(
        r'\b(?:esa\s+nota|esta\s+nota|la\s+nota\s+esa|la\s+[úu]ltima|la\s+primera|'
        r'la\s+anterior|la\s+de\s+antes|la\s+(\d{1,2}))'
        r'\s*(?:[.,;:!?)\]]|$|\s+(?:por\s+favor|porfa|ahora|ya|gracias)\b)', re.I)

    @classmethod
    def senala(cls, texto):
        """El señalador del mensaje, o None. Devuelve también su ordinal si lo trae."""
        hallado = cls.PRONOMBRE.search(texto or '')
        if hallado:
            return hallado, None
        hallado = cls.GENERICO.search(texto or '')
        return (hallado, hallado.group(1)) if hallado else (None, None)

    def device_in_message(self, store, turn_id):
        """El equipo guardado que la persona nombró en este turno, si es solo uno.

        Devolver el nombre no es elegir por ella: está escrito en su mensaje. Con
        dos nombrados o ninguno se devuelve None y el flujo normal pregunta.
        """
        if not turn_id:
            return None
        fila = store.db.execute("SELECT text FROM conversation WHERE id=? AND role='user'",
                                (turn_id,)).fetchone()
        if not fila:
            return None
        texto = fila['text'].casefold()
        # El más largo primero: 'synology 2' antes que 'synology', que está dentro.
        # Y se compara POR POSICIÓN, no por nombre: descartar 'synology' solo por
        # aparecer dentro de 'synology 2' hacía que «compara synology y synology 2»
        # eligiera uno callado, cuando ahí nombró los dos y hay que preguntar.
        guardados = sorted(hosts.load(self.env.workspace), key=len, reverse=True)
        hallados, ocupado = [], []
        for nombre in guardados:
            desde = 0
            while True:
                donde = texto.find(nombre, desde)
                if donde < 0:
                    break
                fin = donde + len(nombre)
                if not any(donde < b and a < fin for a, b in ocupado):
                    ocupado.append((donde, fin))
                    hallados.append(nombre)
                    break
                desde = donde + 1
        return hallados[0] if len(hallados) == 1 else None

    def devices_named(self, store, turn_id):
        """Todos los equipos guardados que la persona nombró, no solo el único.

        Misma cuenta posicional que device_in_message —el nombre más largo primero,
        y sin solapar— pero devolviendo la lista entera: para saber si un turno
        cubrió lo que se le pidió hay que saber cuántos se pidieron.
        """
        if not turn_id:
            return []
        fila = store.db.execute("SELECT text FROM conversation WHERE id=? AND role='user'",
                                (turn_id,)).fetchone()
        if not fila:
            return []
        texto = fila['text'].casefold()
        hallados, ocupado = [], []
        for nombre in sorted(hosts.load(self.env.workspace), key=len, reverse=True):
            desde = 0
            while True:
                donde = texto.find(nombre, desde)
                if donde < 0:
                    break
                fin = donde + len(nombre)
                if not any(donde < b and a < fin for a, b in ocupado):
                    ocupado.append((donde, fin))
                    hallados.append(nombre)
                    break
                desde = donde + 1
        return hallados

    def explicit_read(self, store, turn_id, text):
        """Traduce una lectura inequívoca escrita por la persona.

        No clasifica una intención abierta: exige exactamente un equipo guardado
        nombrado y una sección literal, o un mandato simple de directorios o
        recursos compartidos reconocido por file_requests.
        Esas consultas piden estado actual, así que un resultado histórico no las
        satisface. Ejecutarlas aquí evita que el modelo responda de memoria.
        """
        equipos = self.devices_named(store, turn_id)
        directory_read = explicit_directory_read(text, equipos) or explicit_share_read(text, equipos)
        if directory_read:
            return directory_read
        if not equipos and self.DEVICE_DEIXIS.search(text or ''):
            actual = store.db.execute('SELECT rowid FROM conversation WHERE id=?',
                                      (turn_id,)).fetchone()
            anterior = store.db.execute(
                "SELECT id FROM conversation WHERE role='user' AND rowid<? "
                'ORDER BY rowid DESC LIMIT 1', (actual['rowid'],)).fetchone() if actual else None
            evento = store.db.execute(
                'SELECT body FROM tool_events WHERE turn_id=? ORDER BY seq DESC LIMIT 1',
                (anterior['id'],)).fetchone() if anterior else None
            if evento:
                try:
                    paso = json.loads(evento['body'])
                except (TypeError, ValueError):
                    paso = {}
                resultado = paso.get('result') or {}
                nombre = (paso.get('arguments') or {}).get('name')
                existe = False
                if isinstance(nombre, str):
                    try:
                        hosts.resolve(self.env.workspace, nombre)
                        existe = True
                    except ValueError:
                        pass
                if (paso.get('tool') == 'device.remote' and not paso.get('failed')
                        and isinstance(resultado, dict) and resultado.get('saved') is True
                        and existe):
                    equipos = [nombre.casefold()]
        secciones = list(dict.fromkeys(
            nombre for patron, nombre in self.SECCIONES if patron.search(text or '')))
        if len(equipos) != 1 or len(secciones) != 1:
            return None
        return {'tool':'nas.read',
                'arguments':{'device':equipos[0], 'section':secciones[0]}}

    @classmethod
    def uncovered(cls, pedidos, trace, texto='', limit=6):
        """Lo que la persona pidió y el turno no llegó a leer, equipo por equipo.

        Dos dimensiones: qué equipos nombró, y qué quiso de ellos. Pidió dos y leyó
        uno, o pidió contenedores y solo trajo el diagnóstico: no se quedó sin sitio
        ni sin herramientas, es que no lleva la cuenta. Devuelve pares (equipo,
        sección) que faltan, con sección None cuando no se leyó nada de ese equipo.
        """
        if not pedidos or len(trace) >= limit:
            return []
        secciones = [nombre for patron, nombre in cls.SECCIONES if patron.search(texto or '')]
        if len(pedidos) < 2 and not secciones:
            return []
        leido = {((paso.get('arguments') or {}).get('device', '').casefold(),
                  (paso.get('arguments') or {}).get('section'))
                 for paso in trace if paso.get('tool', '').startswith('nas.')}
        equipos_leidos = {d for d, _ in leido}
        faltan = []
        for nombre in pedidos:
            clave = nombre.casefold()
            if clave not in equipos_leidos:
                faltan.append((nombre, None))
                continue
            for seccion in secciones:
                if (clave, seccion) not in leido:
                    faltan.append((nombre, seccion))
        return faltan

    def pointed_note(self, store, text, turn_id):
        """A qué nota señala sin nombrarla, mirando lo último que se listó o abrió.

        Devuelve la nota o None. No elige por la persona: solo traduce su «la 3» al
        id que ella vio en pantalla hace un turno, igual que se traduce «srv1» al
        equipo guardado. Si no hay a qué señalar, no se inventa ninguna.
        """
        hallado, ordinal = self.senala(text)
        if not hallado:
            return None
        # Lo último que se enseñó o listó, de más reciente a más antiguo.
        filas = store.db.execute(
            'SELECT e.body FROM tool_events e JOIN conversation c ON c.id=e.turn_id '
            'WHERE c.id<>? ORDER BY e.seq DESC LIMIT 12', (turn_id,)).fetchall()
        for fila in filas:
            paso = json.loads(fila['body'])
            resultado = paso.get('result') or {}
            if not isinstance(resultado, dict):
                continue
            if paso.get('tool') == 'note.list':
                # Las filas de la lista ya no llevan id —no se le enseñan al modelo
                # para que no los vuelque—, así que la posición se resuelve contra el
                # almacén, que es de donde salió la lista.
                notas = resultado.get('notes') or []
                elegida = None
                if ordinal and 1 <= int(ordinal) <= len(notas):
                    elegida = notas[int(ordinal) - 1]
                elif not ordinal and len(notas) == 1:
                    elegida = notas[0]
                if elegida is None:
                    continue
                if elegida.get('id'):
                    return elegida
                posicion = elegida.get('n')
                filas = notes.listing(store, limit=200)
                if isinstance(posicion, int) and 1 <= posicion <= len(filas):
                    return filas[posicion - 1]
                continue
                # Con varias y sin ordinal, la lista no señala a ninguna en concreto.
                continue
            if paso.get('tool') in ('note.show', 'note.get', 'note.save') and resultado.get('id'):
                return resultado
        return None
