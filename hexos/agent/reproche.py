"""«Me has pillado»: cuando la persona le echa en cara algo, primero se comprueba.

Sin esto, ante un «pero no me habías dicho…» el modelo se disculpa y le da la
razón aunque no la tenga, y luego se inventa un motivo para cuadrar las dos
versiones («el espacio ha disminuido desde la última vez»). En el banco de
temperatura pasó con un dato falso de 5 TB, y en uso real con Venom.

La indicación entra como dato del turno, igual que el recuerdo del archivo: no
es un AVISO DE HEXOS porque no corrige un fallo del modelo, lo previene. Y el
turno arranca en una lectura (NativeRuntime.require_check): con solo el aviso,
el 12B decía «he vuelto a comprobar la carpeta» sin llamar a nada.
"""
import re

REPROCHE = re.compile(
    r'\b(?:(?:pero\s+)?(?:t[uú]\s+)?me\s+(?:has\s+dicho|dijiste|hab[ií]as\s+dicho|dec[ií]as)'
    r'|(?:antes|ayer|hace\s+un\s+rato)\s+(?:me\s+)?(?:dijiste|has\s+dicho|dec[ií]as)'
    r'|no\s+es\s+(?:verdad|cierto|as[ií])|eso\s+es\s+mentira|me\s+(?:mientes|has\s+mentido)'
    r'|no\s+puede\s+ser'
    r'|te\s+(?:has\s+)?(?:equivocado|equivocas|equivocaste|contradices|contradicho|contradijiste|liado|l[ií]as|colado)'
    r'|est[aá]s\s+segur[oa]|no\s+era\s+as[ií]|no\s+cuadra)\b', re.I)

BLOQUE = (
    '\nREPROCHE DE LA PERSONA (indicación de HexOS, no orden de la persona): dice que dijiste o '
    'hiciste otra cosa. Puede tener razón o no. Antes de responder:\n'
    '1. Comprueba primero con una lectura: el dato actual con su herramienta (NAS, compresiones, '
    'notas, dispositivos) o, si solo se trata de lo que se dijo, history_search. No digas que lo '
    'has comprobado si no has llamado a ninguna.\n'
    '2. Si lo que dijiste era correcto, no te disculpes ni admitas un error que no cometiste: '
    'explica qué dijiste y de dónde salía.\n'
    '3. Si de verdad te equivocaste, reconócelo una sola vez y da el dato correcto.\n'
    '4. No inventes un motivo para que cuadren las dos versiones. Si no puedes comprobarlo, dilo.\n'
    '5. Resuelve lo que quede pendiente.\n')


def bloque(texto):
    """La indicación si el mensaje es un reproche; cadena vacía si no."""
    return BLOQUE if REPROCHE.search(texto or '') else ''
