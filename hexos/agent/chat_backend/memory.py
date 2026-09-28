"""Perfil HERA, extracción de hechos y recuperación literal del historial."""
from __future__ import annotations

import json
import re
import time
from .. import web
from ..native_transport import TurnCancelled
from ..work import now, string
from ..continuity import history_tool
from .state import Environment


# Portón barato: solo si el mensaje tiene forma de afirmación sobre uno mismo se
# gasta una generación en extraer hechos. Un «vale» o un «revisa el NAS» no la
# gastan, así que la conversación normal no paga nada por esto.
AFIRMACION = re.compile(
    r'\b(me llamo|mi nombre es|me puedes llamar|llámame'
    r'|soy (?:de |el |la |un |una )?\w'
    r'|vivo en|resido en|estoy en'
    r'|trabajo (?:de|en|como)|me dedico a|soy programador|soy \w+ de profesión'
    r'|mi \w+ se llama|a mi \w+ le llamo'
    r'|prefiero|me gusta|no me gusta|odio|suelo'
    # Cómo quiere que se le trate, y su corrección cuando no le gusta. Sus frases
    # reales —«me gustaría que seas más cercano», «que lo recuerdes»— no pasaban:
    # «me gusta» no encaja con «me gustaría», y el turno no guardaba nada.
    r'|me gustar[ií]a|prefiero que|quiero que (?:seas|me)'
    r'|tr[aá]tame|h[aá]blame|no me (?:hables|trates|contestes|respondas)'
    r'|no seas|s[eé] m[aá]s|te pido que'
    r'|recuerda que|apunta que|no olvides que|que lo recuerdes'
    # Pedírselo con todas las letras. «memoriza que tengo dos hijos» no pasaba:
    # el portón solo conocía «recuerda» y «apunta».
    r'|memoriza|memor[íi]zalo|guarda que|gu[áa]rdalo|que sepas que|ten en cuenta que'
    # «tengo dos hijos», «tengo 3 gatos». Con número a propósito: «tengo un
    # problema con el NAS» no es un dato suyo y no debe gastar una generación.
    r'|tengo (?:dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|\d+)\s'
    r'|en realidad me llamo|no me llamo)\b', re.I)

# La pregunta pide un dato de AHORA, que el modelo no puede tener: su
# entrenamiento se quedó en una fecha. Se busca por él, igual que se busca en el
# archivo cuando mira al pasado. La puerta de recovery.py cubre «buscó y no abrió
# fuente»; esta cubre lo anterior: no buscar. Contestó de memoria que no sabía
# qué Ubuntu es la actual, teniendo la web delante.
ACTUALIDAD = re.compile(
    r'\b[úu]ltim[ao]\s+versi[óo]n\b|\bversi[óo]n\s+m[áa]s\s+(?:reciente|actual|nueva)\b'
    r'|\bqu[ée]\s+versi[óo]n\b.{0,24}\b(?:actual|hoy|ahora)\b'
    r'|\bcu[áa]nto\s+(?:cuesta|vale)\b'
    r'|\bnovedades\b|\bqu[ée]\s+hay\s+de\s+nuevo\b|\bya\s+(?:sali[óo]|est[áa]\s+disponible)\b'
    r'|\b[úu]ltimas?\s+noticias\b', re.I)
# «Precio de…» también aparece en frases hechas: «no puedo pagar el precio del
# contexto» lanzó el 28/09 una búsqueda web con el mensaje entero. Solo cuenta
# cuando el mensaje pregunta.
PRECIO = re.compile(r'\bprecio\s+(?:de|del|actual)\b', re.I)
PREGUNTA = re.compile(r'[?¿]|^\s*(?:cu[áa]l|qu[ée]|cu[áa]nto|d[óo]nde|a\s+cu[áa]nto)\b', re.I)
# …salvo cuando habla de lo suyo: sus equipos y sus notas no están en internet.
ES_LOCAL = re.compile(
    r'\bnotas?\b|\bcontenedor|\bdocker\b|\bnas\b|\bsynology\b|\bservidorsrv|\bnimos\b'
    r'|\bdisco\b|\bsd[a-z]\b|\bhelios\b|\bhexos\b|\braid\b', re.I)


def pide_dato_de_ahora(text):
    """La pregunta pide un dato de ahora que está en internet, no en sus equipos."""
    text = text or ''
    if ES_LOCAL.search(text):
        return False
    return bool(ACTUALIDAD.search(text) or (PRECIO.search(text) and PREGUNTA.search(text)))


RECUERDO = re.compile(
    r'\b(te acuerdas|recuerdas|acordarte|te acordabas|me acuerdo'
    r'|qu[eé] te (?:dije|ped[ií]|cont[eé]|coment[eé]|pregunt[eé])'
    r'|ya te (?:dije|lo dije|ped[ií]|coment[eé])'
    r'|hablamos (?:de|del|sobre)|comentamos|dijimos|quedamos en'
    r'|anoche|ayer|el otro d[ií]a|la otra vez|la primera vez|en su momento'
    r'|la [uú]ltima vez|antes te dije)\b', re.I)

# Palabras que no distinguen un mensaje de otro: buscarlas devuelve media
# conversación. Incluye las del propio portón, que salen en toda pregunta.
PALABRAS_VACIAS = frozenset(
    'acuerdas acordarte anoche ante antes aquel aquella asi aunque ayer cada '
    'coment comentamos como con contigo cosa cosas cual cuando cuanto decir '
    'dije dijimos dijo donde ella ellos ento entonces esa ese eso esta este '
    'esto estos hablamos hace hacer hasta luego mas mismo mucho muy nada '
    'nunca otra otro para pedi pero poco por porque pregunte primera pues que '
    'quedamos quien recuerdas segun ser sido siempre sobre solo somos son soy '
    'tambien tampoco tanto tener tengo tiene todo todos ultima una unos vez '
    'algo alguna alguno ahora tuve tuya suyo mio nuestro vuestro '
    # De tres letras: «sda» o «nas» sí distinguen, «los» o «del» no.
    'que los las del por con una uno les nos sus mis tus fue son era hay ver '
    'dio ese esa eso tal aun asi hoy dia'.split())


def sin_tildes(palabra):
    tabla = str.maketrans('áéíóúüàèìòùâêîôû', 'aeiouuaeiouaeiou')
    return palabra.translate(tabla)


def recall_terms(text, limite=3):
    """Las palabras de la pregunta que sirven para buscar: las más largas primero,
    porque «contenedores» encuentra el mensaje y «cosa» encuentra media noche."""
    vistas, terminos = set(), []
    for palabra in re.findall(r"[\wáéíóúüñÁÉÍÓÚÜÑ]{3,}", (text or '').casefold()):
        plano = sin_tildes(palabra)
        if plano in PALABRAS_VACIAS or plano in vistas:
            continue
        vistas.add(plano)
        terminos.append(palabra)
    terminos.sort(key=len, reverse=True)
    return terminos[:limite]

def frase_del_hecho(clave, valor):
    """La frase que verá el modelo en el perfil. HERA imprime este texto literal,
    así que es aquí donde el sujeto tiene que quedar dicho: «Su hermana se llama
    Lucía», no «Su nombre es Lucía», que valdría igual para la hermana que para
    el ordenador."""
    sujeto, _, atributo = clave.partition('/')
    if sujeto == 'yo':
        return 'Su ' + atributo + ' es ' + valor
    if atributo == 'nombre':
        return 'Su ' + sujeto + ' se llama ' + valor
    return 'De su ' + sujeto + ', ' + atributo + ': ' + valor


def validated_fact(args, quote):
    """Validación sin escritura, compartida por extracción y guardado explícito."""
    key = string(args.get('key'), 'key', 60).strip().casefold()
    value = string(args.get('value'), 'value', 200).strip()
    if not re.fullmatch(r'[a-záéíóúñü0-9_ -]{1,30}(/[a-záéíóúñü0-9_ -]{1,30})?', key):
        raise ValueError('key debe ser una etiqueta simple como nombre, o sujeto/atributo como gato/nombre')
    if value.casefold() not in quote.casefold():
        raise ValueError('Ese valor no aparece en el mensaje de la persona. Guarda solo lo que '
                         'acaba de decir, con sus palabras; no lo que deduzcas ni recuerdes de antes.')
    return (key if '/' in key else 'yo/' + key), value


class MemoryService:
    def __init__(self, env: Environment):
        self.env = env

    def remember_fact(self, store, args, turn_id, *, automatic=False):
        """Guarda en el perfil un dato que la persona acaba de decir de sí misma.

        La evidencia es su mensaje de este turno, no una cita que aporte el modelo,
        y el valor tiene que aparecer en él: así no puede confirmar lo que deduzca.
        """
        if not self.env.profile:
            raise ValueError('Esta sesión no tiene perfil HERA; el dato no se ha guardado en ninguna parte')
        row = store.db.execute("SELECT text FROM conversation WHERE id=? AND role='user'",
                               (turn_id,)).fetchone() if turn_id else None
        if not row:
            raise ValueError('No hay mensaje de este turno del que tomar la evidencia')
        quote = row['text']
        clave, value = validated_fact(args, quote)
        # El perfil que lee el modelo es esta frase, literal: HERA imprime `texto`
        # tal cual. Sin el sujeto, hermana/nombre y ordenador/nombre se leen los dos
        # como «Su nombre es…» y el perfil se contradice solo.
        texto = frase_del_hecho(clave, value)
        # Corregir y guardar son la misma intención vista desde fuera; lo que
        # cambia es si ya había un hecho vigente. HERA reemplaza de forma atómica
        # y conserva la cadena en `hera historial <clave>`.
        confirmados = self.env.profile.keys()
        anterior = confirmados.get(clave)
        if anterior is None and getattr(self.env.profile, 'unreadable', None):
            # Tratar un hecho ilegible como ausente lo duplicaría en vez de
            # corregirlo. Mejor no escribir que escribir dos veces lo mismo.
            raise ValueError('El perfil tiene ' + str(len(self.env.profile.unreadable)) +
                             ' hecho(s) que no se pueden leer, así que no se puede saber si ' +
                             repr(clave) + ' ya estaba. No se guarda para no duplicarlo.')
        if anterior is None:
            self.env.profile.remember(clave, value, texto, quote[:1000])
        elif anterior == value:
            return dict(saved=False, unchanged=True, key=clave, value=value,
                        note='Ya estaba guardado con ese mismo valor; no se ha tocado nada.')
        else:
            if automatic and anterior.casefold() not in quote.casefold():
                raise ValueError('Conflicto de memoria: una extracción automática no puede '
                                 'reemplazar otro hecho sin una referencia literal al valor anterior. '
                                 'Usa una clave específica para un asunto distinto.')
            self.env.profile.correct(clave, value, texto, quote[:1000])
        return dict(saved=True, corrected=anterior is not None, previous=anterior,
                    key=clave, value=value, source='user_statement',
                    note='Confirmado en el perfil HERA; estará disponible en los próximos turnos '
                         'aunque se limpie el contexto. Guardar no lo hace cierto: lo respalda su mensaje.')

    def recall_web(self, text):
        """Buscar en la web pública cuando la pregunta pide un dato de ahora.

        Misma figura que recall_history: lo consulta HexOS, entra como dato, y un
        fallo aquí —sin red, sin salida— no puede tumbar el turno. No lee las
        fuentes: solo deja los resultados delante para que el modelo abra la que
        le sirva con web_read, que es la puerta que ya existe.
        """
        if not pide_dato_de_ahora(text):
            return None
        empezado = time.monotonic()
        try:
            encontrados = web.search(text.strip()[:200])
        except Exception as exc:
            return dict(tool='web.search', arguments=dict(query=text.strip()[:200]),
                        effect='read', changes_state=False, ts=now(),
                        seconds=round(time.monotonic() - empezado, 3), failed=True,
                        result=dict(error=str(exc)[:200], requested_by='hexos'))
        # `encontrados` ya trae {query, items, count, note}: se conserva tal cual y
        # solo se añade quién lo pidió, para que la traza no invente otra forma.
        return dict(tool='web.search', arguments=dict(query=text.strip()[:200]),
                    effect='read', changes_state=False, ts=now(),
                    seconds=round(time.monotonic() - empezado, 3), failed=False,
                    result=dict(encontrados, requested_by='hexos',
                                note='Lo buscó HexOS al ver que la pregunta pide un dato de ahora; '
                                     'el modelo no lo pidió. Son titulares y fragmentos: para '
                                     'afirmar algo hay que abrir la fuente con web_read.'))

    def recall_history(self, store, text, turn_id):
        """Buscar en el archivo cuando la pregunta apunta al pasado, sin esperar a
        que el modelo lo pida. Devuelve la entrada de traza, o None si no aplica.

        Se busca término a término y se ordena por cuántos coinciden: quien
        aparece con «contenedores» y «synology» a la vez pesa más que quien solo
        trae uno. Un fallo aquí no puede tumbar el turno.
        """
        if not RECUERDO.search(text or ''):
            return None
        terminos = recall_terms(text)
        if not terminos:
            return None
        empezado = time.monotonic()
        try:
            hallazgos, aciertos, consultas = {}, {}, []
            for termino in terminos:
                variantes = [termino]
                # «contraseñas» no encuentra «contraseña»: LIKE es literal. Probar
                # el singular cuesta una pasada de 400 filas, o sea nada.
                if len(termino) > 5 and termino.endswith('es'):
                    variantes.append(termino[:-2])
                elif len(termino) > 4 and termino.endswith('s'):
                    variantes.append(termino[:-1])
                for consulta in variantes:
                    consultas.append(consulta)
                    encontrado = [fila for fila in
                                  history_tool(store, 'history.search', {'query': consulta})['matches']
                                  # El propio mensaje de este turno siempre casa consigo mismo.
                                  if fila['id'] != turn_id]
                    if encontrado:
                        for fila in encontrado:
                            hallazgos[fila['id']] = fila
                            aciertos[fila['id']] = aciertos.get(fila['id'], 0) + 1
                        break
        except Exception:
            return None
        mejores = sorted(hallazgos.values(),
                         key=lambda fila: (aciertos[fila['id']], fila['ts']), reverse=True)[:6]
        mejores.sort(key=lambda fila: fila['ts'])
        return dict(tool='history.recall', arguments=dict(terms=terminos, queries=consultas),
                    effect='read', changes_state=False, ts=now(),
                    seconds=round(time.monotonic() - empezado, 3), failed=False,
                    result=dict(matches=mejores, historical_data=True,
                                search_type='literal_substring',
                                requested_by='hexos', order='oldest_to_newest',
                                note='Lo buscó HexOS al ver que la pregunta miraba al pasado; '
                                     'el modelo no lo pidió. Cero coincidencias no demuestra '
                                     'ausencia: history_search con otra palabra puede encontrarlo.'))

    def harvest_facts(self, store, text, turn_id, trace=None):
        """Guardar lo que la persona acaba de contar de sí misma, sin que lo pida.

        Tres filtros en cascada: el patrón decide si merece una generación, la
        extracción propone, y remember_fact exige que el valor esté literalmente
        en su mensaje. HERA aplica encima sus reglas de sujeto, valor y polaridad.
        Nada de esto interrumpe el turno: un fallo aquí no puede tumbar la respuesta.
        """
        if not self.env.profile or not hasattr(self.env.runtime, 'extract_facts'):
            return ''
        if not AFIRMACION.search(text or ''):
            return ''
        empezado = time.monotonic()
        try:
            candidatos = self.env.runtime.extract_facts(text)
        except TurnCancelled:
            raise
        except Exception:
            return ''
        # Queda registrada como cualquier otra generación: sin esto su coste es invisible.
        generacion = getattr(self.env.runtime, 'last_extraction_generation', None)
        if generacion is not None:
            store.db.execute('INSERT INTO generation_events(turn_id,ts,body) VALUES (?,?,?)',
                             (turn_id, now(), json.dumps(generacion, ensure_ascii=False)))
            store.db.commit()
        anotado = []
        guardados = []
        # Una extracción no es una secuencia de correcciones de la persona.
        # Dos candidatos para la misma clave no deben pisarse por orden de salida.
        row = store.db.execute("SELECT text FROM conversation WHERE id=? AND role='user'",
                               (turn_id,)).fetchone() if turn_id else None
        if not row:
            return ''
        grupos = {}
        for hecho in candidatos:
            if not isinstance(hecho, dict):
                continue
            try:
                key, value = validated_fact(hecho, row['text'])
            except (ValueError, TypeError):
                continue  # Un candidato inválido no debe desplazar a uno respaldado.
            if value.casefold() in ('no me gusta', 'me gusta', 'eso', 'así', 'asi'):
                continue
            grupos.setdefault(key, []).append(dict(key=key, value=value))
        candidatos = []
        for hechos in grupos.values():
            completo = max(hechos, key=lambda h: len(h['value']))
            if all(h['value'].casefold() in completo['value'].casefold() for h in hechos):
                candidatos.append(completo)
            # Valores incompatibles: no elegir una corrección arbitraria.
        for hecho in candidatos:
            try:
                resultado = self.remember_fact(store, hecho, turn_id, automatic=True)
            except (ValueError, TypeError):
                continue      # no estaba en su mensaje, o HERA lo rechazó
            if not resultado.get('saved'):
                continue
            sujeto, _, atributo = resultado['key'].partition('/')
            # Con «yo» basta el atributo; con otro sujeto hay que nombrarlo, o
            # hermana/nombre y ordenador/nombre se leen los dos como «nombre».
            etiqueta = atributo if sujeto == 'yo' else resultado['key'].replace('/', ' · ')
            guardados.append(resultado['key'] + ' = ' + resultado['value'])
            anotado.append(('He corregido' if resultado.get('corrected') else 'He anotado')
                           + ' ' + etiqueta + ': ' + resultado['value']
                           + (' (antes ' + resultado['previous'] + ')'
                              if resultado.get('previous') else ''))
        # Queda en la traza como cualquier otra escritura. Sin esto, el turno decía
        # «he anotado tu trato» con la traza vacía y el cierre lo marcaba como
        # afirmación sin respaldo: el hecho estaba en HERA, pero no constaba.
        if guardados and trace is not None:
            trace.append(dict(tool='profile.remember', arguments=dict(count=len(guardados)),
                              effect='write', changes_state=True, ts=now(),
                              seconds=round(time.monotonic() - empezado, 3), failed=False,
                              verification='confirmada',
                              evidence='releído del perfil: ' + ', '.join(guardados),
                              result=dict(saved=guardados, requested_by='hexos',
                                          note='Lo guardó HexOS al ver que la persona contaba algo '
                                               'de sí misma; el modelo no lo pidió. Las palabras son '
                                               'suyas y HERA conserva la frase como evidencia.')))
        # Decirlo siempre: si se equivoca, que se vea en el momento y no dentro de un mes.
        return '· ' + '. '.join(anotado) + '.' if anotado else ''
