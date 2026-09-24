"""Personal facts are retrieved explicitly, never attached wholesale to a turn."""
import unicodedata


def availability(profile):
    return ('MEMORIA PERSONAL: disponible mediante profile_recall con una consulta concreta. '
            'No es una fuente del informe técnico salvo que el encargo necesite ese dato.\n'
            if profile else '')


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
