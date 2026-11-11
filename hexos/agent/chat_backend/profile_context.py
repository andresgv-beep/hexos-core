"""Personal facts are retrieved explicitly, never attached wholesale to a turn."""
import unicodedata


SIEMPRE_DELANTE = 1500


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
        texto = profile.read()
    except Exception:
        return A_DEMANDA                # ilegible ahora: que al menos sepa que existe
    if not texto:
        return ('MEMORIA PERSONAL: todavía no hay nada guardado de la persona. '
                'Lo que cuente de sí misma lo guarda HexOS al cerrar el turno.\n')
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
    facts = [dict(key=key, value=value) for key, value in profile.keys().items()
             if term in normalized(key) or term in normalized(str(value))]
    return dict(available=True, query=query, facts=facts[:10], total=len(facts),
                truncated=len(facts) > 10, source='HERA',
                note='Datos personales recuperados, no observaciones del NAS ni del informe.')
