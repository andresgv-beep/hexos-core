"""Perfil HERA, extracción de hechos y recuperación literal del historial."""
from __future__ import annotations

from datetime import datetime
import json
import re
import sqlite3
import time
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
    r'|vivo en|resido en|me he mudado a|estoy en'
    r'|trabajo (?:de|en|como)|me dedico a|soy programador|soy \w+ de profesión'
    r'|mi \w+ se llama|a mi \w+ le llamo'
    r'|prefiero|me gusta|no me gusta|odio|suelo'
    # Cómo quiere que se le trate, y su corrección cuando no le gusta. Sus frases
    # reales —«me gustaría que seas más cercano», «que lo recuerdes»— no pasaban:
    # «me gusta» no encaja con «me gustaría», y el turno no guardaba nada.
    r'|me gustar[ií]a|prefiero que|quiero que (?:seas|me)'
    r'|tr[aá]tame|h[aá]blame|no me (?:hables|trates|contestes|respondas)'
    r'|no seas|s[eé] m[aá]s|te pido que'
    r'|recuerda que|recuerda mi|apunta que|no olvides que|que lo recuerdes'
    # Cómo quiere que SEA Helios. «necesito que recuerdes que eres compañero, no un
    # asistente» y «recuerda no ofrecerte como asistente» no pasaban: el portón solo
    # miraba frases sobre la persona, contestó «sí, lo he recordado» y no guardó nada.
    r'|eres|recuerd[ae]s?|necesito que|quiero que|no te (?:ofrezcas|presentes|comportes|portes)'
    r'|comp[oó]rtate|deja de|no hace falta que|no (?:uses|pongas|digas|termines|acabes)'
    # Pedírselo con todas las letras. «memoriza que tengo dos hijos» no pasaba:
    # el portón solo conocía «recuerda» y «apunta».
    r'|memoriza|memor[íi]zalo|guarda que|gu[áa]rdalo|que sepas que|ten en cuenta que'
    # «tengo dos hijos», «tengo 3 gatos». Con número a propósito: «tengo un
    # problema con el NAS» no es un dato suyo y no debe gastar una generación.
    r'|tengo (?:dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|\d+)\s'
    r'|en realidad me llamo|no me llamo'
    # Por raíz y no por frase. El 13/11 no pasaron «puedes llamarme Andrés» (se conocía
    # «me puedes llamar» y «llámame») ni «guárdate mi nombre» (se conocía «guarda que» y
    # «guárdalo»): cada variante que faltaba se había ido añadiendo a mano, y siempre
    # faltaba otra. Helios contestó «he guardado» sin guardar nada. Pedir memoria con
    # cualquier forma de estos verbos, o decir cómo se llama uno, pasa el portón; si
    # luego no hay ningún dato, el extractor devuelve vacío y no se guarda nada.
    r'|llam(?:arme|adme|arte)|ll[aá]m[ae]me'
    r'|gu[aá]rd(?:a|e|ar|ad)(?:te|me|lo|la|los|las|melo|telo|mela|tela)?'
    r'|memor[ií]z\w+|ap[uú]nt(?:a|e|ar)(?:te|me|lo|la|melo|telo)'
    r'|(?:no|que no) (?:se )?(?:te |me )?olvid\w+|acu[eé]rd(?:a|e)te|qu[eé]date con'
    r'|mi \w+ (?:es|son|era|ser[aá])\b|mis \w+ son\b)\b', re.I)

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

# El portón de arriba solo conoce quien avisa de que recuerda («te acuerdas», «ayer»). La
# primera noche con la búsqueda nueva (2026-11-20) tres de cuatro preguntas de memoria ni
# buscaron: «que vapeador tengo?», «no recuerdas nada?» y «como se llamaba?». Tres formas
# más de mirar atrás, medidas sobre los 731 mensajes reales del archivo: de buscar en 9
# se pasa a buscar en 15, y los seis nuevos venían a cuento.

# 1. Lo que se dijeron: «¿qué modelo me dijiste que era?», «¿en qué zona te dije que estaba?».
#    Solo formas de pasado: «me cuentas» o «te pido» son de ahora.
DICHO = re.compile(
    r'\b(?:(?:me|te|nos)(?:\s+l[oa]s?)?\s+(?:dijiste|dije|dijimos|contaste|cont[eé]|comentaste|coment[eé]'
    r'|recomendaste|ense[ñn]aste|ense[ñn][eé]|explicaste|expliqu[eé]|preguntaste|pregunt[eé]|pediste|ped[ií]'
    r'|diste|mandaste|mand[eé]|propusiste|sugeriste|bajaste|buscaste)|dijiste)\b', re.I)

# 2. Una pregunta por algo suyo: «¿qué vapeador tengo?», «¿qué pantalla tiene mi esp32?». Eso
#    solo puede salir de lo que contó. Tiene que empezar preguntando (qué, cuál, cómo…) y ser
#    corta: «¿puedes revisar los procesos de mi equipo?» es un encargo, y «¿por qué no uso
#    otro programa?» pide una opinión.
EMPIEZA_PREGUNTANDO = re.compile(
    r'(?:^|[.!?¿,;]\s*)\s*(?:y\s+|oye\s+|pero\s+|entonces\s+)?(?:(?:de|en|a|con|para|sobre)\s+)?'
    r'(?:qu[eé]|cu[aá]l(?:es)?|c[oó]mo|d[oó]nde|cu[aá]nt[oa]s?|qui[eé]n(?:es)?|cu[aá]ndo)\b', re.I)
LO_SUYO = re.compile(r'\b(?:mi|mis|m[ií][oa]s?|tengo|ten[ií]a|yo|llevaba|usaba|quer[ií]a)\b', re.I)
PALABRAS_DE_PREGUNTA_PROPIA = 14

# 3. La pregunta de seguimiento: «¿cómo se llamaba?» no dice de qué habla; lo dijo la anterior.
#    Si es corta y la persona acaba de preguntar por el pasado, se busca con las palabras de
#    aquella. Vale también para «¿no recuerdas nada?», que pasa el portón sin traer palabras.
PALABRAS_DE_SEGUIMIENTO = 6
SEGUNDOS_DE_SEGUIMIENTO = 600


def pregunta_por_lo_suyo(text):
    return ('?' in text and len(text.split()) <= PALABRAS_DE_PREGUNTA_PROPIA
            and bool(EMPIEZA_PREGUNTANDO.search(text)) and bool(LO_SUYO.search(text)))


def mira_al_pasado(text):
    """¿Pide el mensaje, por sí solo, algo que solo puede estar en el archivo?"""
    text = text or ''
    return bool(RECUERDO.search(text) or DICHO.search(text) or pregunta_por_lo_suyo(text))


def pregunta_corta(text):
    text = text or ''
    return len(text.split()) <= PALABRAS_DE_SEGUIMIENTO and ('?' in text or bool(EMPIEZA_PREGUNTANDO.search(text)))


def preguntas_recientes(store, turn_id, cuantas=3):
    """Lo último que escribió la persona en esta ventana justo antes de este turno, de lo más
    reciente a lo más antiguo. Lo que HexOS apunta en su nombre («[La persona aprobó…») no cuenta."""
    este = store.db.execute('SELECT rowid, ts FROM esta_ventana WHERE id=?', (turn_id,)).fetchone()
    if este is None:
        return []
    ahora, recientes = datetime.fromisoformat(este['ts']), []
    for fila in store.db.execute("SELECT ts, text FROM esta_ventana WHERE role='user' AND rowid<? "
                                 'ORDER BY rowid DESC LIMIT 8', (este['rowid'],)):
        if fila['text'].startswith('['):
            continue
        if (ahora - datetime.fromisoformat(fila['ts'])).total_seconds() > SEGUNDOS_DE_SEGUIMIENTO:
            break
        recientes.append(fila['text'])
    return recientes[:cuantas]


def terminos_de_recuerdo(store, text, turn_id):
    """Con qué palabras buscar en el archivo, o ninguna si el mensaje no mira atrás.

    Devuelve (términos, heredados): heredados son los que vienen de la pregunta anterior,
    cuando esta es un seguimiento.
    """
    text = text or ''
    propios, directo = recall_terms(text, limite=None), mira_al_pasado(text)
    if directo and propios:
        return propios, []
    if not (directo or pregunta_corta(text)):
        return [], []
    for anterior in preguntas_recientes(store, turn_id):
        suyos = recall_terms(anterior, limite=None)
        if mira_al_pasado(anterior) and suyos:
            vistos = {sin_tildes(t) for t in suyos}
            return suyos + [t for t in propios if sin_tildes(t) not in vistos], suyos
        if not pregunta_corta(anterior):
            break                       # entre medias se habló de otra cosa
    return [], []


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


# Relleno de conversación: no es de ningún tema, pero tampoco sale en todas partes, así que
# una búsqueda por rareza le da peso. La primera noche, a «okey no pasa nada, recuerdas de un
# libro que estaba escribiendo?» le ganó «okey»: cuatro de los seis mensajes traídos eran un
# «Okey» suelto. Sacadas de las palabras que más repite la persona en su archivo. Va aparte
# de PALABRAS_VACIAS, que también decide qué líneas de trato se parecen.
RELLENO = frozenset(
    'okey okay vale venga bueno buena buenos buenas bien mal mejor peor claro gracias hola adios '
    'socio oye mira dale ostia osea esque verdad realmente bastante igual todavia ahi alli aqui '
    'tan menos sin puedes puede puedo podria podrias podemos sabes sabe saber crees creo veo ves '
    'parece dime quiero quieres necesito gustaria has han hemos habia eres estoy estas estaba '
    'estabas estaban estabamos tienes tenia tenias seria sea echo hecho hice hiciste pasa paso '
    'pasar sigue seguir'.split())
RISA = re.compile(r'(?:[jh][aeiou]+)+[jh]?')        # jaja, jajaj, jeje, haha


def sin_tildes(palabra):
    tabla = str.maketrans('áéíóúüàèìòùâêîôû', 'aeiouuaeiouaeiou')
    return palabra.translate(tabla)


def recall_terms(text, limite=3):
    """Las palabras de la pregunta que sirven para buscar: las más largas primero,
    porque «contenedores» encuentra el mensaje y «cosa» encuentra media noche.
    Con `limite=None`, todas."""
    vistas, terminos = set(), []
    for palabra in re.findall(r"[\wáéíóúüñÁÉÍÓÚÜÑ]{3,}", (text or '').casefold()):
        plano = sin_tildes(palabra)
        if plano in PALABRAS_VACIAS or plano in RELLENO or RISA.fullmatch(plano) or plano in vistas:
            continue
        vistas.add(plano)
        terminos.append(palabra)
    terminos.sort(key=len, reverse=True)
    return terminos[:limite] if limite else terminos


def raiz(termino):
    """«contraseñas» también es «contraseña»: el plural no debe esconder el mensaje."""
    if len(termino) > 5 and termino.endswith('es'):
        return termino[:-2]
    if len(termino) > 4 and termino.endswith('s'):
        return termino[:-1]
    return termino


def formas(termino):
    """La palabra y su plural o su singular, nada más. Como principio de cualquier otra
    («pasa» → «pasado») traía mensajes que no tenían que ver."""
    base = raiz(termino)
    return list(dict.fromkeys((termino, base, base + 's', base + 'es')))


def por_rareza(store, terminos, salvo=None, limite=6):
    """Los mensajes de esta ventana que mejor casan con esas palabras, el mejor primero, y
    cuántos de los que casaban se dejaron fuera por ser de hace un momento.

    Texto completo de SQLite (FTS5) ordenado por BM25: pesa más la palabra rara que la
    que sale en media conversación, cuentan todas las palabras de la pregunta y no gana
    lo más reciente por serlo. La búsqueda anterior cogía las 20 coincidencias más
    nuevas de cada palabra, y lo antiguo quedaba enterrado: «¿te acuerdas del libro?»
    dejó de traer el libro en cuanto la palabra volvió a salir veinte veces. Medido en
    helios-memoria (2026-11-20) con las preguntas que pasan el portón: de 10 a 17 de 22.

    Lo de los últimos minutos no es un recuerdo: el modelo ya lo tiene delante. Sin
    quitarlo, a «¿no recuerdas nada?» le llegaban la pregunta que acababa de hacer la
    persona y la respuesta en que Helios decía no saberlo.

    El índice se hace en memoria para cada búsqueda, con lo que hay en la ventana: con
    unos miles de mensajes son milisegundos, y así no hay tabla nueva que mantener ni
    que migrar. Si este SQLite no trae FTS5, sqlite3.OperationalError: quien llama
    busca como antes.
    """
    filas = store.db.execute('SELECT rowid, id, ts, role, text FROM esta_ventana').fetchall()
    este = next((fila for fila in filas if fila['id'] == salvo), None)
    recientes = set()
    if este is not None:
        ahora = datetime.fromisoformat(este['ts'])
        recientes = {fila['rowid'] for fila in filas if fila['id'] != salvo
                     and abs((ahora - datetime.fromisoformat(fila['ts'])).total_seconds()) <= SEGUNDOS_DE_SEGUIMIENTO}
    indice = sqlite3.connect(':memory:')
    try:
        # Sin tildes ni mayúsculas: «diagnostico» encuentra «diagnóstico».
        indice.execute("CREATE VIRTUAL TABLE pasajes USING fts5(text, tokenize='unicode61 remove_diacritics 2')")
        # El propio mensaje de este turno siempre casa consigo mismo: no entra.
        indice.executemany('INSERT INTO pasajes(rowid, text) VALUES (?,?)',
                           ((fila['rowid'], fila['text']) for fila in filas if fila['id'] != salvo))
        consulta = ' OR '.join('"%s"' % forma.replace('"', '') for termino in terminos for forma in formas(termino))
        ordenados = [fila[0] for fila in indice.execute(
            'SELECT rowid FROM pasajes WHERE pasajes MATCH ? ORDER BY bm25(pasajes) LIMIT ?',
            (consulta, limite + len(recientes)))]
    finally:
        indice.close()
    por_rowid = {fila['rowid']: fila for fila in filas}
    mejores = [n for n in ordenados if n not in recientes][:limite]
    return ([dict(id=por_rowid[n]['id'], ts=por_rowid[n]['ts'], role=por_rowid[n]['role'],
                  excerpt=por_rowid[n]['text'][:500]) for n in mejores],
            sum(1 for n in ordenados if n in recientes))


def por_coincidencia_literal(store, terminos, salvo=None, limite=6):
    """La búsqueda de antes, para un SQLite sin FTS5: término a término con LIKE, las 20
    coincidencias más recientes de cada uno, y manda quien casa con más términos.
    Devuelve los mensajes y las consultas que hizo."""
    hallazgos, aciertos, consultas = {}, {}, []
    for termino in terminos:
        # «contraseñas» no encuentra «contraseña»: LIKE es literal. Probar
        # el singular cuesta una pasada de 400 filas, o sea nada.
        for consulta in dict.fromkeys((termino, raiz(termino))):
            consultas.append(consulta)
            encontrado = [fila for fila in
                          history_tool(store, 'history.search', {'query': consulta})['matches']
                          if fila['id'] != salvo]
            if encontrado:
                for fila in encontrado:
                    hallazgos[fila['id']] = fila
                    aciertos[fila['id']] = aciertos.get(fila['id'], 0) + 1
                break
    mejores = sorted(hallazgos.values(),
                     key=lambda fila: (aciertos[fila['id']], fila['ts']), reverse=True)[:limite]
    return mejores, consultas

# Cuántas líneas distintas caben en el trato de la ficha. Pocas a propósito: va delante en cada turno.
MAX_TRATOS = 4


def _raices(texto):
    return {sin_tildes(p)[:6] for p in re.findall(r"[\wáéíóúüñ]{4,}", (texto or '').casefold())
            if sin_tildes(p) not in PALABRAS_VACIAS}


def hueco_del_trato(confirmados, nuevo):
    """En qué hueco va una petición de trato, para que la ficha no acumule repeticiones.

    Lo mismo dicho con otras palabras sustituye a su línea: «no eres un asistente
    comercial» y «eres un compañero, no un asistente» eran dos entradas y son una
    intención. Lo que es otra cosa («no uses emojis») ocupa hueco nuevo, hasta el tope;
    lleno, no entra solo: la persona dice cuál cambia. HERA sigue guardando una cita
    literal por hueco, y cada cambio queda en su historial.
    """
    from .profile_context import tratos
    vigentes = tratos(confirmados)
    for clave, valor in vigentes:
        if valor.casefold() == ' '.join(nuevo.split()).casefold():
            return clave
    raices = _raices(nuevo)
    for clave, valor in vigentes:
        suyas = _raices(valor)
        comunes = raices & suyas
        if len(comunes) >= 2 or (comunes and len(comunes) == min(len(raices), len(suyas))):
            return clave
    if len(vigentes) >= MAX_TRATOS:
        raise ValueError('La ficha ya tiene %d líneas de trato y esta no sustituye a ninguna: ' % MAX_TRATOS
                         + '; '.join('«%s»' % valor for _, valor in vigentes)
                         + '. No se ha guardado. Dile cuáles son y que elija cuál cambia.')
    usados = {clave for clave, _ in vigentes}
    # Un hueco retirado (repetía a otro) se aprovecha antes de abrir uno más.
    huecos = ['yo/trato'] + ['yo/trato %d' % n for n in range(2, 40)]
    return next(h for h in huecos if h not in usados)


# Segunda persona dentro de un dato: se refiere a quien escucha, que es Helios.
A_HELIOS = re.compile(r'\b(?:tu|tus|tú|ti|te|contigo|tuyo|tuya|tuyos|tuyas)\b', re.I)


def frase_del_hecho(clave, valor):
    """La frase que verá el modelo en el perfil. HERA imprime este texto literal,
    así que es aquí donde el sujeto tiene que quedar dicho: «Su hermana se llama
    Lucía», no «Su nombre es Lucía», que valdría igual para la hermana que para
    el ordenador."""
    sujeto, _, atributo = clave.partition('/')
    # El valor son sus palabras, y las dijo hablándole a Helios: «soy tu creador» se
    # guardaba como «Su rol es tu creador» y al leerlo contestó «como tu creador,
    # espero que…». Las comillas y la aclaración dejan dicho a quién se lo decía.
    if sujeto == 'yo' and atributo.startswith('trato'):
        # Lo que pidió sobre el trato, con sus palabras. En la ficha va en su propio bloque.
        return 'Te pidió: «' + valor + '»'
    if A_HELIOS.search(valor):
        valor = '«' + valor + '» (lo dijo hablándote a ti, Helios)'
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


# Solo afirmaciones completas en primera persona permiten corregir estos datos sin
# nombrar el valor anterior. Una pregunta, un supuesto o una cita no son correcciones.
ATRIBUTOS_PERSONALES = {
    'yo/ciudad': r'(?:vivo en|resido en|me he mudado a)',
    'yo/nombre': r'(?:me llamo|mi nombre es)',
    'yo/apodo': r'(?:mi apodo es|llámame)',
}


def respalda_correccion(clave, valor, anterior, mensaje):
    inicio = ATRIBUTOS_PERSONALES.get(clave)
    if not inicio:
        # Otros atributos pueden tener varios valores. Conserva la regla anterior.
        return anterior.casefold() in mensaje.casefold()
    patron = r'(?:yo |ahora |ahora mismo |en realidad |actualmente )*' + inicio + r'\s+' + re.escape(valor)
    # Cada frase debe afirmar el valor entero. No cortar en «?» ni en signos de cita.
    # «Ya no vivo en Cuenca, ahora vivo en Teruel» contiene las dos partes.
    antes = r'(?:(?:ya )?no ' + inicio + r'\s+' + re.escape(anterior) + r',\s*)?'
    return any(re.fullmatch(antes + patron, frase.strip(), re.I)
               for frase in re.split(r'[.!;\n]', mensaje))


def pide_extraccion(text):
    # «¿Cómo me llamo?» pide recordar. En «¿Cómo me llamo? Me llamo Lidia»
    # queda una afirmación y sí corresponde pasar el mensaje al extractor.
    sin_pregunta_nombre = re.sub(r'\bc[oó]mo me llamo\s*\?', '', text or '', flags=re.I)
    return bool(AFIRMACION.search(sin_pregunta_nombre))


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
        # El trato de la ficha son pocas líneas sin repetir (hueco_del_trato). «háblame como
        # un colega» y después «no uses emojis» son dos peticiones y conviven; la misma dicha
        # de otra forma sustituye a la que había. Antes cada una abría hueco nuevo (trato 2,
        # trato 3…) y el perfil acababa con la misma idea tres veces.
        del_trato = clave == 'yo/trato'
        if del_trato:
            try:
                clave = hueco_del_trato(confirmados, value)
            except ValueError as exc:
                if not automatic:
                    raise
                return dict(saved=False, unchanged=True, key=clave, value=value, note=str(exc))
            texto = frase_del_hecho(clave, value)
        anterior = confirmados.get(clave)
        if anterior is None and getattr(self.env.profile, 'unreadable', None):
            # Tratar un hecho ilegible como ausente lo duplicaría en vez de
            # corregirlo. Mejor no escribir que escribir dos veces lo mismo.
            raise ValueError('El perfil tiene ' + str(len(self.env.profile.unreadable)) +
                             ' hecho(s) que no se pueden leer, así que no se puede saber si ' +
                             repr(clave) + ' ya estaba. No se guarda para no duplicarlo.')
        if anterior is None:
            self.env.profile.remember(clave, value, texto, quote[:1000])
        elif anterior == value or (del_trato and anterior.casefold() == value.casefold()):
            return dict(saved=False, unchanged=True, key=clave, value=value,
                        note='Ya estaba guardado con ese mismo valor; no se ha tocado nada.')
        else:
            if automatic and not del_trato and not respalda_correccion(clave, value, anterior, quote):
                return dict(saved=False, conflict=True, key=clave, previous=anterior, value=value,
                            note='El dato propuesto entra en conflicto con el perfil vigente.')
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
            # Pide un dato de ahora: lo del último año, no lo que el buscador ponga arriba.
            encontrados = self.env.dependencies.web_search(text.strip()[:200], recency='año')
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

        Qué cuenta como mirar atrás lo decide terminos_de_recuerdo. Se busca con todas
        las palabras útiles y se ordena por rareza (por_rareza). Un fallo aquí no puede
        tumbar el turno.
        """
        empezado = time.monotonic()
        try:
            terminos, heredados = terminos_de_recuerdo(store, text, turn_id)
            if not terminos:
                return None
            try:
                (mejores, de_ahora), consultas = por_rareza(store, terminos, salvo=turn_id), [raiz(t) for t in terminos]
                tipo = 'full_text_bm25'
                if not mejores and de_ahora:
                    # Solo casa lo que se acaba de decir: está en la conversación, no en el
                    # archivo. Un «sin coincidencias» encima haría dudar de lo que tiene delante.
                    return None
            except sqlite3.OperationalError:
                # Este SQLite no trae FTS5: se busca como antes, con las tres palabras más largas.
                mejores, consultas = por_coincidencia_literal(store, sorted(terminos, key=len, reverse=True)[:3], salvo=turn_id)
                tipo = 'literal_substring'
        except Exception:
            return None
        mejores.sort(key=lambda fila: fila['ts'])
        return dict(tool='history.recall', arguments=dict(terms=terminos, queries=consultas, inherited=heredados),
                    effect='read', changes_state=False, ts=now(),
                    seconds=round(time.monotonic() - empezado, 3), failed=False,
                    result=dict(matches=mejores, historical_data=True,
                                search_type=tipo,
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
        if not pide_extraccion(text):
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
        guardados, conflictos, sin_cambios = [], [], []
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
            if resultado.get('conflict'):
                conflictos.append(dict(key=resultado['key'], previous=resultado['previous'],
                                       proposed=resultado['value']))
                anotado.append('Sigue guardado ' + resultado['key'] + ' = ' + resultado['previous']
                               + '. Para cambiarlo, indica el nuevo valor de ese dato')
                continue
            if not resultado.get('saved'):
                if resultado.get('unchanged'):
                    sin_cambios.append(resultado['key'])
                continue
            sujeto, _, atributo = resultado['key'].partition('/')
            # Con «yo» basta el atributo; con otro sujeto hay que nombrarlo, o
            # hermana/nombre y ordenador/nombre se leen los dos como «nombre».
            etiqueta = (atributo.rstrip(' 0123456789') if sujeto == 'yo'
                        else resultado['key'].replace('/', ' · '))
            guardados.append(resultado['key'] + ' = ' + resultado['value'])
            anotado.append(('He corregido' if resultado.get('corrected') else 'He anotado')
                           + ' ' + etiqueta + ': ' + resultado['value']
                           + (' (antes ' + resultado['previous'] + ')'
                              if resultado.get('previous') else ''))
        # Queda en la traza como cualquier otra escritura. Sin esto, el turno decía
        # «he anotado tu trato» con la traza vacía y el cierre lo marcaba como
        # afirmación sin respaldo: el hecho estaba en HERA, pero no constaba.
        if guardados or conflictos or sin_cambios:
            event = dict(tool='profile.remember', arguments=dict(count=len(candidatos)),
                         effect='write', changes_state=bool(guardados), ts=now(),
                         seconds=round(time.monotonic() - empezado, 3), failed=bool(conflictos),
                         verification='no_cumplida' if conflictos else 'confirmada',
                         evidence='confirmado por HERA: ' + ', '.join(guardados) if guardados else None,
                         result=dict(saved=guardados, conflicts=conflictos, unchanged=sin_cambios,
                                     requested_by='hexos'))
            store.db.execute('INSERT INTO tool_events(turn_id,ts,body) VALUES (?,?,?)',
                             (turn_id, event['ts'], json.dumps(event, ensure_ascii=False)))
            store.db.commit()
            if trace is not None:
                trace.append(event)
        # Decirlo siempre: si se equivoca, que se vea en el momento y no dentro de un mes.
        return '· ' + '. '.join(anotado) + '.' if anotado else ''
