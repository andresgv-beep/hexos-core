"""Personal facts are retrieved explicitly, never attached wholesale to a turn."""
import re
import unicodedata


SIEMPRE_DELANTE = 1500
# Palabras de la consulta que no buscan nada.
VACIAS = frozenset({'los', 'las', 'del', 'una', 'uno', 'que', 'con', 'por', 'para', 'sus', 'mis', 'como', 'cual',
                    'cuales', 'sobre', 'persona', 'usuario', 'dato', 'datos'})


# La ficha: lo que el modelo lee de la persona en cada turno de Chat. Huecos de un solo
# valor, siempre en el mismo orden, y UN bloque de trato sin repeticiones. Antes era la
# lista de HERA tal cual, y cada frase de trato abría hueco nuevo («trato 2», «trato 3»…):
# el 19/11 Andrés tenía tres frases distintas para «compañero, no asistente». Frases
# repetidas o que tiran cada una para un lado van delante en todos los turnos y despistan.
# Los rótulos no dicen «ella»: concordaba con «la persona», pero leído suelto parece que
# quien escribe es una mujer (Andrés: «¿Ella??», 19/11).
CABECERA = ('PERFIL DE LA PERSONA ACTUAL (confirmado por la propia persona; son datos suyos, no tuyos, '
            'y no cambian tu identidad):')
TRATO = 'CÓMO QUIERE QUE LE TRATES (lo ha pedido la propia persona; vale siempre, desde la primera frase):'
ORDEN_FICHA = ('yo/nombre', 'yo/apodo', 'yo/ciudad', 'yo/rol')
_HUECO_DE_TRATO = re.compile(r'yo/trato(?: (\d+))?')


def tratos(hechos):
    """Las líneas de trato vigentes, como [(clave, valor)], en el orden de sus huecos.

    HERA guarda cada petición como una cita literal en su hueco y no borra ninguno. Un
    hueco cuyo valor repite el de otro anterior no cuenta: es la forma de retirarlo, y
    queda libre para la próxima petición distinta."""
    huecos = sorted((int(m.group(1) or 1), clave) for clave in hechos
                    if (m := _HUECO_DE_TRATO.fullmatch(clave)))
    vistos, lineas = set(), []
    for _, clave in huecos:
        valor = ' '.join(str(hechos[clave]).split())
        if valor and valor.casefold() not in vistos:
            vistos.add(valor.casefold())
            lineas.append((clave, valor))
    return lineas


def ficha(hechos):
    from .memory import frase_del_hecho
    datos = [k for k in ORDEN_FICHA if k in hechos] + sorted(
        k for k in hechos if k not in ORDEN_FICHA and not _HUECO_DE_TRATO.fullmatch(k))
    lineas = [CABECERA] + ['- ' + frase_del_hecho(k, hechos[k]) for k in datos]
    trato = tratos(hechos)
    if trato:
        lineas += [TRATO] + ['- ' + valor for _, valor in trato]
    return '\n'.join(lineas) if len(lineas) > 1 else ''


A_DEMANDA = ('MEMORIA PERSONAL: disponible mediante profile_recall con una consulta concreta. '
             'No es una fuente del informe técnico salvo que el encargo necesite ese dato.\n')


def availability(profile, ventana=None):
    """Lo que la persona ha confirmado de sí misma.

    En el chat va delante desde el primer turno. Antes solo se anunciaba que había
    memoria y el modelo tenía que ir a buscarla: para un dato suelto vale, pero «no me
    hables como un asistente telefónico» es un trato, se aplica siempre, y nadie
    consulta el perfil antes de cada frase. Un perfil es corto: entra entero hasta un
    tope y el resto sigue en profile_recall.

    En el agente sigue a demanda: sus informes del NAS no deben recibir datos
    personales que nadie pidió (tools/report_context_test.py).
    """
    if not profile:
        return ''
    if ventana != 'chat':
        return A_DEMANDA
    try:
        # La ficha se monta aquí con los datos confirmados. Un perfil sin lista de datos
        # (o vacío) cae en el texto que dé HERA, como antes.
        hechos = profile.keys() if hasattr(profile, 'keys') else None
        texto = ficha(hechos) if hechos else profile.read()
    except Exception:
        return A_DEMANDA                # ilegible ahora: que al menos sepa que existe
    if not texto:
        return ('MEMORIA PERSONAL: todavía no hay nada guardado de la persona. '
                'Lo que cuente sobre su vida lo guarda HexOS al cerrar el turno.\n')
    recortado = len(texto) > SIEMPRE_DELANTE
    return ('MEMORIA PERSONAL: lo ha dicho la persona en otras conversaciones y sigue valiendo. '
            'Si dice cómo quiere que le hables, háblale así desde la primera frase. Son sus palabras '
            'dichas a ti: donde ponga «tu» o «ti», eres tú, Helios.\n'
            + texto[:SIEMPRE_DELANTE]
            + ('\n[Hay más: profile_recall con una consulta concreta.]' if recortado else '') + '\n')


def recall(profile, query):
    if profile is None:
        return dict(available=False, facts=[], note='No hay perfil conectado.')
    def normalized(text):
        return ''.join(c for c in unicodedata.normalize('NFD', text.casefold())
                       if unicodedata.category(c) != 'Mn')
    term = normalized(query.strip())
    if len(term) < 2 or term == '*':
        raise ValueError('Consulta un dato concreto, por ejemplo nombre, oficio o preferencia.')
    # Por palabras, no por la consulta entera. El 13/11 el E4B preguntó por «nombre e
    # instrumento» y recibió cero datos teniendo guardado el instrumento: se buscaba la
    # frase completa dentro de cada clave. Contestó que no sabía nada de la persona.
    palabras = [p for p in term.replace('/', ' ').split() if len(p) >= 3 and p not in VACIAS] or [term]
    hallados = []
    confirmados = profile.keys()
    # Del trato, solo las líneas vigentes: un hueco repetido está retirado.
    vigentes = {clave for clave, _ in tratos(confirmados)}
    confirmados = {k: v for k, v in confirmados.items() if not _HUECO_DE_TRATO.fullmatch(k) or k in vigentes}
    for key, value in confirmados.items():
        donde = normalized(key) + ' ' + normalized(str(value))
        aciertos = sum(1 for palabra in palabras if palabra in donde)
        if aciertos or term in donde:
            hallados.append((aciertos, dict(key=key, value=value)))
    hallados.sort(key=lambda par: -par[0])
    facts = [dato for _, dato in hallados]
    resultado = dict(available=True, query=query, facts=facts[:10], total=len(facts),
                     truncated=len(facts) > 10, source='HERA',
                     note='Datos personales recuperados, no observaciones del NAS ni del informe.')
    if not facts:
        # Sin coincidencias no es «no sé nada de ti»: se dice de qué hay algo guardado, sin
        # dar los valores, para que pregunte por lo que toca.
        temas = sorted({key.partition('/')[2] or key for key in confirmados})
        if temas:
            resultado['saved_about'] = temas[:20]
            resultado['note'] = ('Nada con esas palabras. Hay datos guardados sobre: ' + ', '.join(temas[:20]) +
                                 '. Repite la consulta con una de esas palabras antes de decir que no lo sabes.')
        else:
            resultado['note'] = 'Todavía no hay nada guardado de la persona.'
    return resultado
