"""«…y te lo guardas en una nota:» cuando todavía no ha dicho el qué.

La persona escribe a veces en dos mensajes: primero el encargo, acabado en dos puntos, y
después el contenido. El 20/11, a «Mira, para que lo tengas claro y te lo guardas en una
nota y lo marcas como favorito:» el 26B no esperó: se inventó el contenido (guardó su
propio contexto) y lo ancló. La orden era de verdad, pero lo que había que apuntar aún
no había llegado.

Es una señal de forma, no de lo que el modelo conteste: el mensaje pide una nota y acaba
en dos puntos. En ese turno no se guarda nada y se le dice que espere; el mensaje
siguiente se le presenta como el contenido de esa nota.
"""
import re

# Pide apuntar, no solo nombra las notas: «te doy unas notas sobre el viaje:» no es esto.
PIDE_NOTA = re.compile(
    r'\b(?:en (?:una|la|tu|tus|esa|otra) notas?|como nota|toma(?:r)? nota|ap[uú]nt\w*|an[oó]t\w*'
    r'|memor[ií]z\w*|gu[aá]rd\w*(?:\W+\w+){0,6}\W+notas?)\b', re.I)
ANCLAR = re.compile(r'\b(?:favorit\w*|ancl\w*|estrella|siempre presente|tenlo siempre|que no se te olvide)\b', re.I)
# Un mensaje largo que acaba en dos puntos ya trae contenido dentro: no es un encargo suelto.
MAXIMO = 300

ESPERA = ('\nNOTA SIN CONTENIDO (dato de HexOS): pide una nota, pero su mensaje acaba en dos puntos: lo que '
          'hay que apuntar llega en su siguiente mensaje. No guardes ni ancles nada ahora y no rellenes '
          'tú el contenido: dile en una frase que te lo pase.\n')
RECHAZO = ('Todavía no ha dicho qué apuntar: su mensaje acaba en dos puntos y el contenido llega en el '
           'siguiente. No se ha guardado nada. Dile en una frase que te lo pase.')


def sin_contenido(texto):
    """¿Es un encargo de nota cuyo contenido aún no ha llegado?"""
    texto = (texto or '').strip()
    return bool(texto) and len(texto) <= MAXIMO and texto.endswith(':') and bool(PIDE_NOTA.search(texto))


def encargo(texto):
    """Lo que hay que recordar del encargo hasta que llegue el contenido."""
    texto = (texto or '').strip()
    return dict(orden=texto[:MAXIMO], anclar=bool(ANCLAR.search(texto)))


def bloque_contenido(pendiente):
    """La indicación para el turno en que llega lo que había que apuntar."""
    return ('\nCONTENIDO DE LA NOTA (dato de HexOS): en su mensaje anterior pidió una nota y dejó el contenido '
            'para este: «' + pendiente['orden'] + '». Si este mensaje es ese contenido, guárdalo ahora con '
            'note_save, con sus palabras y un título corto'
            + (', y después ánclala con note_mark (favorite sí), que es lo que pidió' if pendiente.get('anclar') else '')
            + '. Si en cambio te dice otra cosa (que lo dejes, una pregunta), atiende a eso y no guardes nada.\n')
