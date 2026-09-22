"""Quién autoriza un cambio de estado. No el modelo: la persona, en su mensaje.

Lo demás de este backend ya desconfía del modelo de forma mecánica —el cierre se
calcula de la traza, la comprobación la ejecuta HexOS, un destino no se inventa—.
La única herramienta que para o levanta un servicio real estaba protegida por una
frase en su descripción pidiéndole que no lo hiciera por iniciativa propia. Eso es
pedírselo por prompt, y con este modelo no basta.

Aquí la regla es la misma que en `file_requests`, aplicada a lo que sí rompe: se
lee el mensaje REAL de la persona y la llamada no pasa si no hay orden.

ANTE LA DUDA NO AUTORIZA, que es al revés que en el resto del sistema. Cuando se
duda de si consultar al modelo, se consulta: preguntar de más cuesta una
inferencia. Aquí equivocarse de más para un servicio. Así que un mandato escrito
de forma rara se queda fuera y la persona lo repite; eso cuesta un turno, y
autorizar de más cuesta una caída.
"""
from __future__ import annotations

import re

# Efectos cuya ejecución exige una orden explícita del turno. Lista cerrada y a
# mano a propósito: añadir aquí un efecto es una decisión de seguridad, y nadie
# debería heredarla sin querer por llamar a su herramienta `write_algo`.
EFECTOS_QUE_EXIGEN_ORDEN = frozenset({'write_container'})

# Formas imperativas por familia de acción. Con enclítico pegado, que es como se
# escribe en un chat —«párala», «reinícialo»—, y en las dos ortografías, porque
# nadie pone las tildes al pedir que se reinicie algo.
#
# Ojo con dos trampas del español que estuvieron a punto de colarse:
#   · «para» a secas es una PREPOSICIÓN («mira el estado para saber si…») y
#     aceptarla autorizaría paradas que nadie pidió. Solo entra con enclítico,
#     en infinitivo o delante de un sustantivo de servicio.
#   · «inicia» está dentro de «reinicia». Lo resuelve `\b`: entre la `e` y la `i`
#     no hay frontera de palabra, así que `\binicia` no casa dentro de «reinicia».
_SERVICIO = r'(?:el\s+|la\s+)?(?:contenedor|servicio|docker|stack|c[oó]ntainer)\b'
ACCIONES = {
    'stop': re.compile(
        r'\b(?:p[áa]ra(?:lo|la|los|las|me(?:lo|la)?)|parar|detener|det[ée]n(?:lo|la|me(?:lo|la)?)?'
        r'|ap[áa]ga(?:lo|la|me(?:lo|la)?)?|apagar|b[áa]ja(?:lo|la)|bajar|tumba(?:lo|la)?|stop)\b'
        r'|\bpara\s+' + _SERVICIO, re.I),
    'start': re.compile(
        r'\b(?:arranca(?:lo|la|me(?:lo|la)?)?|arrancar|inicia(?:lo|la|me(?:lo|la)?)?|iniciar'
        r'|lev[áa]nta(?:lo|la|me(?:lo|la)?)?|levantar|enci[ée]nde(?:lo|la)?|encender'
        r'|s[úu]be(?:lo|la)|subir|start)\b', re.I),
    # Reiniciar contiene a las otras dos: quien pide un reinicio ya ha aceptado la
    # parada. Por eso autoriza las tres, y no al revés.
    'restart': re.compile(
        r'\b(?:rein[íi]cia(?:lo|la|me(?:lo|la)?)?|reiniciar|reinicio|rein[íi]ciame'
        r'|res[eé]tea(?:lo|la)?|resetear|restart|reboot)\b', re.I),
}

# Cómo lo dice HELIOS cuando lo PROPONE, que es otra gramática distinta. La
# persona manda en imperativo —«para el contenedor»— y él se ofrece en infinitivo
# o subjuntivo: «puedo parar plex», «¿quieres que pare plex?», «voy a reiniciarlo».
# Medido con una prueba: el patrón de órdenes no reconocía «¿Quieres que pare
# plex?» y un «hazlo» perfectamente legítimo se quedaba sin autorizar.
#
# Estas formas solo se leen sobre el mensaje de Helios, nunca sobre el de la
# persona, y además se exige que la propuesta nombre el contenedor. Por eso puede
# admitir palabras que sueltas serían ambiguas —«paro», «inicio» son también
# sustantivos— sin abrir la puerta a nada.
PROPUESTAS = {
    'stop': re.compile(
        r'\b(?:parar(?:lo|la)?|paro|pare(?:mos)?|detener(?:lo|la)?|detengo|detenga'
        r'|apagar(?:lo|la)?|apago|apague|bajar(?:lo|la)?|bajo|baje)\b', re.I),
    'start': re.compile(
        r'\b(?:arrancar(?:lo|la)?|arranco|arranque|iniciar(?:lo|la)?|inicio|inicie'
        r'|levantar(?:lo|la)?|levanto|levante|encender(?:lo|la)?|enciendo|encienda'
        r'|subir(?:lo|la)?|subo|suba)\b', re.I),
    'restart': re.compile(
        r'\b(?:reiniciar(?:lo|la)?|reinicio|reinicie|resetear(?:lo|la)?|reseteo|resetee)\b', re.I),
}

# Qué acción queda autorizada por cada familia nombrada. Pedir una parada NO
# autoriza un reinicio: el reinicio termina con el servicio en marcha, que es
# justo lo contrario de lo que se pidió.
AUTORIZA = {'stop': {'stop'}, 'start': {'start'},
            'restart': {'restart', 'stop', 'start'}}

AFIRMACION = re.compile(
    r'\b(?:s[íi]|vale|venga|dale|ok|okey|okay|de\s+acuerdo|adelante|correcto|exacto'
    r'|h[áa]zlo|hazlo|procede|confirmo|conf[íi]rmalo|tira|perfecto|eso\s+es)\b', re.I)
# Una afirmación con pero delante no es un permiso: «sí, pero mira antes el
# estado» pide una lectura, no la escritura.
NEGACION = re.compile(r'\bno\b|\bpero\b|\bantes\b|\bmejor\s+no\b|\bespera\b', re.I)


def _familias(texto, propone=False):
    """Familias de acción nombradas en un texto.

    `propone=True` lee además las formas con las que Helios se ofrece a hacerlo,
    que son infinitivo y subjuntivo en vez de imperativo.
    """
    patrones = dict(ACCIONES)
    if propone:
        for familia, patron in PROPUESTAS.items():
            patrones[familia + '\u00b7propuesta'] = patron
    encontradas = {familia.split('\u00b7')[0]
                   for familia, patron in patrones.items() if patron.search(texto or '')}
    return encontradas


def _mensaje_del_turno(store, turn_id):
    fila = store.db.execute("SELECT ts, text FROM conversation WHERE id=? AND role='user'",
                            (turn_id,)).fetchone()
    return (fila['ts'], fila['text']) if fila else (None, None)


def _propuesta_anterior(store, ts):
    """Lo último que dijo Helios antes de este turno."""
    fila = store.db.execute(
        "SELECT text FROM conversation WHERE role='assistant' AND ts < ? "
        "ORDER BY ts DESC LIMIT 1", (ts,)).fetchone()
    return fila['text'] if fila else ''


def authorize_state_change(store, turn_id, name, args):
    """Deja pasar el cambio de estado o lo impide con el motivo.

    Se autoriza de dos formas, y las dos son la persona decidiendo:

      a) Su mensaje de este turno nombra la acción. Se exige que la familia
         nombrada admita la acción pedida, para que «para el contenedor» no
         acabe en un reinicio.

      b) Su mensaje afirma una propuesta que Helios acaba de hacer, y esa
         propuesta nombraba ESTE contenedor y ESTA acción. Un «sí» suelto no
         dice sobre qué, así que el objeto tiene que estar en la propuesta o no
         hay forma de saber a qué dijo que sí.

    Lo que nunca autoriza es el propio modelo: ni un resultado que lo sugiera,
    ni un registro anterior, ni una petición de turnos atrás.
    """
    accion = (args.get('action') or '').strip().casefold()
    objetivo = (args.get('container') or '').strip()
    if accion not in ACCIONES:
        raise ValueError('action debe ser start, stop o restart; llegó ' + repr(args.get('action')))
    if not turn_id:
        # La ruta normal siempre trae el turno. Sin él no hay mensaje que leer, y
        # sin mensaje no hay orden: no se adivina.
        raise ValueError('No se puede cambiar el estado de ' + repr(objetivo) +
                         ' sin el turno en el que se pidió.')

    ts, mensaje = _mensaje_del_turno(store, turn_id)
    if not mensaje:
        raise ValueError('No consta el mensaje de este turno, así que no consta la orden de '
                         'cambiar el estado de ' + repr(objetivo) + '.')

    directas = _familias(mensaje)
    if any(accion in AUTORIZA[familia] for familia in directas):
        return

    if directas:
        # Pidió un cambio, pero no este. Es el caso más peligroso de todos porque
        # parece autorizado de lejos.
        pedido = ', '.join(sorted(directas))
        raise ValueError(
            'En su mensaje se pide ' + pedido + ', no ' + accion + '. No se cambia por otra cosa: '
            'ejecuta lo que pidió, o pregúntale si querías proponerle algo distinto.')

    afirma = AFIRMACION.search(mensaje) and not NEGACION.search(mensaje)
    if afirma:
        propuesta = _propuesta_anterior(store, ts)
        nombrado = objetivo and objetivo.casefold() in (propuesta or '').casefold()
        if nombrado and any(accion in AUTORIZA[familia]
                            for familia in _familias(propuesta, propone=True)):
            return
        raise ValueError(
            'Su mensaje afirma algo, pero lo último que le dijiste no proponía ' + accion +
            ' sobre ' + repr(objetivo) + ', así que no se sabe a qué ha dicho que sí. '
            'Propónselo nombrando el contenedor y la acción, y espera su respuesta.')

    raise ValueError(
        'Su mensaje de este turno no pide ' + accion + ' sobre ningún contenedor, y un cambio de '
        'estado solo lo autoriza él. Si crees que hace falta, díselo y espera: para MIRAR cómo '
        'está usa nas_read section=containers container=' + (objetivo or '<nombre>') +
        ', que no toca nada.')
