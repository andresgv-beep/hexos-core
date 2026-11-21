"""Buscar en el archivo de conversaciones: qué palabras de una frase sirven y qué mensajes
casan mejor con ellas.

Lo usan las dos maneras de mirar atrás: el recuerdo que HexOS pone solo cuando la pregunta
apunta al pasado (chat_backend/memory.py) y la herramienta history.search que el modelo llama
por su cuenta (continuity.py). Antes cada una buscaba a su manera, y la herramienta seguía con
la cadena literal: si el modelo escribía tres palabras, o estaban las tres seguidas en un
mensaje o no encontraba nada.
"""
from datetime import datetime
import re
import sqlite3

# Lo dicho hace menos de esto no es un recuerdo: el modelo lo tiene delante. También es el
# plazo en que una pregunta corta hereda las palabras de la anterior (memory.py).
SEGUNDOS_DE_SEGUIMIENTO = 600


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


def por_rareza(store, terminos, salvo=None, limite=6, ahora=None):
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
    «Ahora» es la hora del mensaje `salvo` (el del
    turno); quien no tenga ese mensaje a mano pasa `ahora`.

    El índice se hace en memoria para cada búsqueda, con lo que hay en la ventana: con
    unos miles de mensajes son milisegundos, y así no hay tabla nueva que mantener ni
    que migrar. Si este SQLite no trae FTS5, sqlite3.OperationalError: quien llama
    busca como antes.
    """
    filas = store.db.execute('SELECT rowid, id, ts, role, text FROM esta_ventana').fetchall()
    este = next((fila for fila in filas if fila['id'] == salvo), None)
    if este is not None:
        ahora = datetime.fromisoformat(este['ts'])
    recientes = set()
    if ahora is not None:
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
