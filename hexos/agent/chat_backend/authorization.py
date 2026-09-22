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

Tres propiedades sostienen esto, y las tres faltaban en la primera versión. Una
revisión las encontró sin tocar el NAS y conviene dejarlas escritas:

  · NEGACIÓN. Reconocer el verbo no basta: «no quiero parar plex» lo contiene y
    autorizaba la parada.
  · OBJETO. Una orden vale para SU contenedor y su equipo; «reinicia plex»
    autorizaba reiniciar HandBrake porque nadie ataba la orden a su destino.
  · LÍMITE DE PALABRA. Los nombres se comparaban por subcadena, así que aceptar
    `plex-test` abría la puerta a `plex`.
"""
from __future__ import annotations

import re

# Efectos cuya ejecución exige una orden explícita del turno. Lista cerrada y a
# mano a propósito: añadir aquí un efecto es una decisión de seguridad, y nadie
# debería heredarla sin querer por llamar a su herramienta `write_algo`.
EFECTOS_QUE_EXIGEN_ORDEN = frozenset({'write_container'})

# Formas imperativas por familia de acción. Con enclítico pegado, que es como se
# escribe en un chat —«párala», «reinícialo»—, y CON Y SIN TILDE, porque el
# cotejo es por bytes: «arráncalo» no contiene «arranca», la á es otro carácter.
# Ese descuido dejaba fuera una orden perfectamente legítima.
#
# Ojo con dos trampas del español:
#   · «para» a secas es una PREPOSICIÓN («mira el estado para saber si…») y
#     aceptarla autorizaría paradas que nadie pidió. Solo entra con enclítico,
#     en infinitivo o delante de un sustantivo de servicio.
#   · «inicia» está dentro de «reinicia». Lo resuelve `\b`: entre la `e` y la `i`
#     no hay frontera de palabra, así que `\binicia` no casa dentro de «reinicia».
_SERVICIO = r'(?:el\s+|la\s+)?(?:contenedor|servicio|docker|stack|c[oó]ntainer)\b'
_CLITICO = r'(?:lo|la|los|las|me(?:lo|la)?)'
ACCIONES = {
    'stop': re.compile(
        r'\b(?:p[áa]ra' + _CLITICO + r'|parar|detener|det[ée]n(?:' + _CLITICO + r')?'
        r'|ap[áa]ga(?:' + _CLITICO + r')?|apagar|b[áa]ja' + _CLITICO + r'|bajar'
        r'|t[úu]mba(?:' + _CLITICO + r')?|stop)\b'
        r'|\bpara\s+' + _SERVICIO, re.I),
    'start': re.compile(
        r'\b(?:arr[áa]nca(?:' + _CLITICO + r')?|arrancar|in[íi]cia(?:' + _CLITICO + r')?|iniciar'
        r'|lev[áa]nta(?:' + _CLITICO + r')?|levantar|enci[ée]nde(?:' + _CLITICO + r')?|encender'
        r'|s[úu]be' + _CLITICO + r'|subir|start)\b', re.I),
    # Reiniciar contiene a las otras dos: quien pide un reinicio ya ha aceptado la
    # parada. Por eso autoriza las tres, y no al revés.
    'restart': re.compile(
        r'\b(?:rein[íi]cia(?:' + _CLITICO + r')?|reiniciar|reinicio'
        r'|res[eé]tea(?:' + _CLITICO + r')?|resetear|restart|reboot)\b', re.I),
}

# Cómo lo dice HELIOS cuando lo PROPONE, que es otra gramática distinta. La
# persona manda en imperativo —«para el contenedor»— y él se ofrece en infinitivo
# o subjuntivo: «puedo parar plex», «¿quieres que pare plex?».
#
# Solo se leen sobre el mensaje de Helios, nunca sobre el de la persona, y además
# se exige que la propuesta nombre el contenedor. Por eso puede admitir palabras
# que sueltas serían ambiguas —«paro», «inicio» son también sustantivos— sin
# abrir la puerta a nada.
PROPUESTAS = {
    'stop': re.compile(
        r'\b(?:parar(?:' + _CLITICO + r')?|paro|pare(?:mos)?|detener(?:' + _CLITICO + r')?'
        r'|detengo|detenga|apagar(?:' + _CLITICO + r')?|apago|apague'
        r'|bajar(?:' + _CLITICO + r')?|bajo|baje)\b', re.I),
    'start': re.compile(
        r'\b(?:arrancar(?:' + _CLITICO + r')?|arranco|arranque|iniciar(?:' + _CLITICO + r')?'
        r'|inicio|inicie|levantar(?:' + _CLITICO + r')?|levanto|levante'
        r'|encender(?:' + _CLITICO + r')?|enciendo|encienda|subir(?:' + _CLITICO + r')?'
        r'|subo|suba)\b', re.I),
    'restart': re.compile(
        r'\b(?:reiniciar(?:' + _CLITICO + r')?|reinicio|reinicie'
        r'|resetear(?:' + _CLITICO + r')?|reseteo|resetee)\b', re.I),
}

# Qué acción queda autorizada por cada familia nombrada. Pedir una parada NO
# autoriza un reinicio: el reinicio termina con el servicio en marcha, que es
# justo lo contrario de lo que se pidió.
AUTORIZA = {'stop': {'stop'}, 'start': {'start'},
            'restart': {'restart', 'stop', 'start'}}

# Negación DELANTE del verbo y dentro de su misma oración. Mirar si hay un «no»
# en cualquier sitio del mensaje rechazaría «para plex, no el otro», que es una
# orden buena; mirar solo lo que precede al verbo distingue «no quiero parar» de
# «para plex, no el otro» sin listas de frases.
NEGADO_DELANTE = re.compile(r'\b(?:no|ni|nunca|jam[áa]s|tampoco|sin)\b[^.;:\n¿?]{0,40}$', re.I)

AFIRMACION = re.compile(
    r'\b(?:s[íi]|vale|venga|dale|ok|okey|okay|de\s+acuerdo|adelante|correcto|exacto'
    r'|h[áa]zlo|hazlo|procede|confirmo|conf[íi]rmalo|tira|perfecto|eso\s+es)\b', re.I)
# Una afirmación con reparo no es un permiso: «sí, pero mira antes el estado»
# pide una lectura, no la escritura.
REPARO = re.compile(r'\bno\b|\bpero\b|\bantes\b|\bmejor\s+no\b|\bespera\b', re.I)

# Orden que señala en vez de nombrar: «reinícialo», «para ese». Solo con una de
# estas se acepta que el objeto venga del turno anterior; si la persona nombra un
# objeto distinto, eso NO es señalar y no hay nada que heredar.
DEIXIS = re.compile(r'\w' + _CLITICO + r'\b|\b(?:ese|esa|este|esta|eso|esto)\b', re.I)


def _token(nombre):
    """Casa el nombre como unidad, no como trozo de otro.

    `\\b` no basta: en «plex-test» hay frontera de palabra tras «plex», así que
    `\\bplex\\b` casaría dentro y aprobar `plex-test` abriría la puerta a `plex`.
    Se excluyen además guion, guion bajo y punto, que es de lo que están hechos
    los nombres de contenedor.
    """
    return re.compile(r'(?<![\w.\-])' + re.escape(nombre) + r'(?![\w.\-])', re.I)


def _nombra(texto, nombre):
    return bool(nombre) and bool(_token(nombre).search(texto or ''))


def _familias(texto, propone=False):
    """Familias de acción nombradas y NO negadas en un texto.

    `propone=True` lee además las formas con las que Helios se ofrece a hacerlo,
    que son infinitivo y subjuntivo en vez de imperativo.
    """
    texto = texto or ''
    grupos = [(familia, patron) for familia, patron in ACCIONES.items()]
    if propone:
        grupos += [(familia, patron) for familia, patron in PROPUESTAS.items()]
    encontradas = set()
    for familia, patron in grupos:
        for hallazgo in patron.finditer(texto):
            if not NEGADO_DELANTE.search(texto[:hallazgo.start()]):
                encontradas.add(familia)
                break
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


def authorize_state_change(store, turn_id, name, args, dispositivos=()):
    """Deja pasar el cambio de estado o lo impide con el motivo.

    Se autoriza de dos formas, y las dos son la persona decidiendo:

      a) Su mensaje nombra la acción SIN negarla y nombra el contenedor; o lo
         señala («reinícialo») y el contenedor está en lo último que dijo Helios.

      b) Su mensaje afirma una propuesta que Helios acaba de hacer, y esa
         propuesta ofrecía ESTA acción sobre ESTE contenedor. Un «sí» suelto no
         dice sobre qué, así que el objeto tiene que estar en la propuesta.

    Con varios equipos registrados, el equipo también tiene que constar: da igual
    lo clara que sea la orden si no se sabe en cuál de ellos.

    Lo que nunca autoriza es el propio modelo: ni un resultado que lo sugiera,
    ni un registro anterior, ni una petición de turnos atrás.
    """
    accion = (args.get('action') or '').strip().casefold()
    objetivo = (args.get('container') or '').strip()
    equipo = (args.get('device') or '').strip()
    if accion not in ACCIONES:
        raise ValueError('action debe ser start, stop o restart; llegó ' + repr(args.get('action')))
    if not objetivo:
        raise ValueError('No se cambia el estado de un contenedor sin decir cuál.')
    if not turn_id:
        # La ruta normal siempre trae el turno. Sin él no hay mensaje que leer, y
        # sin mensaje no hay orden: no se adivina.
        raise ValueError('No se puede cambiar el estado de ' + repr(objetivo) +
                         ' sin el turno en el que se pidió.')

    ts, mensaje = _mensaje_del_turno(store, turn_id)
    if not mensaje:
        raise ValueError('No consta el mensaje de este turno, así que no consta la orden de '
                         'cambiar el estado de ' + repr(objetivo) + '.')
    propuesta = _propuesta_anterior(store, ts)

    # El EQUIPO, cuando hay más de uno donde equivocarse. Una orden clarísima
    # sobre el servidor que no era sigue siendo un servicio caído.
    conocidos = [d for d in dispositivos if d]
    if len(conocidos) > 1 and equipo and not (_nombra(mensaje, equipo) or
                                              _nombra(propuesta, equipo)):
        raise ValueError(
            'Hay varios equipos registrados y en la conversación no consta que se pida el cambio '
            'en ' + repr(equipo) + '. Pregúntale en cuál antes de tocar nada.')

    directas = _familias(mensaje)
    permitidas = {a for familia in directas for a in AUTORIZA[familia]}
    if accion in permitidas:
        # La orden vale para SU objeto. O lo nombra, o lo señala y entonces el
        # antecedente es lo último que dijo Helios; nunca lo elige el modelo.
        if _nombra(mensaje, objetivo):
            return
        if DEIXIS.search(mensaje) and _nombra(propuesta, objetivo):
            return
        raise ValueError(
            'Se pide ' + accion + ', pero en el mensaje no consta que sea sobre ' + repr(objetivo) +
            '. No se elige el destino por él: pregúntale cuál, o nómbralo tú y espera respuesta.')

    if directas:
        # Pidió un cambio, pero no este. Es el caso más peligroso de todos porque
        # parece autorizado de lejos.
        raise ValueError(
            'En su mensaje se pide ' + ', '.join(sorted(directas)) + ', no ' + accion + '. No se '
            'cambia por otra cosa: ejecuta lo que pidió, o pregúntale si querías proponerle algo '
            'distinto.')

    if AFIRMACION.search(mensaje) and not REPARO.search(mensaje):
        ofrecidas = {a for familia in _familias(propuesta, propone=True) for a in AUTORIZA[familia]}
        if accion in ofrecidas and _nombra(propuesta, objetivo):
            return
        raise ValueError(
            'Su mensaje afirma algo, pero lo último que le dijiste no ofrecía ' + accion +
            ' sobre ' + repr(objetivo) + ', así que no se sabe a qué ha dicho que sí. '
            'Propónselo nombrando el contenedor y la acción, y espera su respuesta.')

    raise ValueError(
        'Su mensaje de este turno no pide ' + accion + ' sobre ' + repr(objetivo) + ', y un cambio '
        'de estado solo lo autoriza él. Si crees que hace falta, díselo y espera: para MIRAR cómo '
        'está usa nas_read section=containers container=' + objetivo + ', que no toca nada.')
