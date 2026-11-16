"""Ficheros de la web que la persona deja bajar a este PC.

Helios propone (`file.download`) y la persona aprueba en una tarjeta, como al instalar un
programa: ve nombre, origen, tipo y tamaño antes de que entre nada en el disco. HexOS baja
el fichero a una carpeta fija, no lo abre ni lo ejecuta, y si es un PDF o un texto guarda
además lo que dice como documento, para que Helios lo lea entero con `document.read`
(`web.read` solo le da el principio).
"""
import hashlib
import mimetypes
import os
from pathlib import Path
import re
from urllib.parse import quote, unquote, urlparse
from uuid import uuid4

from . import web
from .work import now


MAX_BYTES = 50_000_000
MAX_TEXTO = 2_000_000
PDF_PAGINAS = 400
PDF_SEGUNDOS = 60
# Lo que se ejecuta o se instala no entra por aquí, se llame como se llame la petición.
EJECUTABLES = frozenset(('.exe', '.msi', '.bat', '.cmd', '.com', '.scr', '.ps1', '.vbs', '.sh', '.bash', '.run',
                         '.bin', '.appimage', '.deb', '.rpm', '.apk', '.jar', '.dmg', '.pkg', '.so', '.dll',
                         '.desktop', '.flatpakref', '.snap'))
TIPOS_EJECUTABLES = frozenset(('application/x-executable', 'application/x-msdownload', 'application/x-msi',
                               'application/x-sh', 'application/x-shellscript', 'application/x-elf',
                               'application/x-sharedlib', 'application/vnd.debian.binary-package',
                               'application/x-debian-package', 'application/x-rpm', 'application/java-archive',
                               'application/vnd.android.package-archive', 'application/x-apple-diskimage',
                               'application/vnd.appimage'))
CLASES = {'application/pdf': 'PDF', 'application/zip': 'ZIP', 'application/json': 'JSON', 'text/plain': 'texto',
          'text/csv': 'CSV', 'text/markdown': 'Markdown', 'application/epub+zip': 'EPUB'}
_RARO = re.compile(r'[^\w .()+-]')
# Lo que el navegador puede enseñar sin riesgo dentro de la interfaz. Lo demás solo se entrega
# para guardar: un SVG o un HTML abiertos desde el origen de Helios ejecutarían lo que traigan.
A_LA_VISTA = frozenset(('application/pdf', 'image/png', 'image/jpeg', 'image/gif', 'image/webp'))


def raiz():
    """Dónde caen las descargas: una carpeta de la persona, fuera del espacio de HexOS."""
    return Path(os.environ.get('HEXOS_DOWNLOADS_HOME') or Path.home() / 'Helios' / 'descargas').expanduser()


def initialize(store):
    store.db.execute('''CREATE TABLE IF NOT EXISTS downloads (
        id TEXT PRIMARY KEY, ts TEXT NOT NULL, name TEXT NOT NULL, path TEXT NOT NULL, url TEXT NOT NULL,
        content_type TEXT NOT NULL, bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, document TEXT)''')


def tamano(n):
    if n is None:
        return 'tamaño sin declarar'
    if n < 1_000_000:
        return f'{max(1, round(n / 1000))} kB'
    return f'{n / 1_000_000:.1f} MB'.replace('.', ',')


def _corta(ruta):
    """La ruta como la diría la persona, con ~ en vez de su carpeta."""
    try:
        return '~/' + str(Path(ruta).relative_to(Path.home()))
    except ValueError:
        return str(ruta)


def _nombre(url, propuesto, tipo):
    """Un nombre de fichero sin carpetas ni caracteres raros, con extensión si se puede saber."""
    base = propuesto if isinstance(propuesto, str) and propuesto.strip() else unquote(Path(urlparse(url).path).name)
    base = _RARO.sub('_', Path(base.replace('\\', '/')).name).strip(' .')[:120] or 'descarga'
    if not Path(base).suffix:
        base += mimetypes.guess_extension(tipo) or ''
    return base


def _clase(tipo, nombre):
    if tipo in CLASES:
        return CLASES[tipo]
    if tipo.startswith('image/'):
        return 'imagen ' + tipo.split('/', 1)[1].split('+')[0].upper()
    return (Path(nombre).suffix.lstrip('.').upper() or tipo)


def proponer(url, name=None, *, asomar=None):
    """Mira qué hay en la dirección y deja el plan para la tarjeta. No baja nada."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError('url es la dirección pública del fichero')
    final, tipo, pesa = (asomar or web.asomar)(url.strip())
    nombre = _nombre(final, name, tipo)
    if tipo == 'text/html':
        raise ValueError('esa dirección es una página web, no un fichero: se lee con web_read')
    if Path(nombre).suffix.lower() in EJECUTABLES or tipo in TIPOS_EJECUTABLES:
        raise ValueError('eso es un programa o un instalador: por aquí no se descargan. ' + web.ENLACE_VALIDO)
    if pesa is not None and pesa > MAX_BYTES:
        raise ValueError(f'pesa {tamano(pesa)} y el tope es {tamano(MAX_BYTES)}. ' + web.ENLACE_VALIDO)
    clase, host = _clase(tipo, nombre), urlparse(final).hostname
    return dict(plan_id=uuid4().hex, created=now(), requested=url.strip(), url=final, name=nombre, host=host,
                content_type=tipo, kind=clase, bytes=pesa, folder=_corta(raiz()),
                summary=f'descargar {nombre} ({clase}, {tamano(pesa)}) de {host}')


def mismo(pendiente, url):
    """¿Se está pidiendo otra vez la descarga que ya espera en la tarjeta?"""
    return bool(pendiente) and isinstance(url, str) and url.strip() in (pendiente['requested'], pendiente['url'])


def bloque_pendiente(pendiente):
    """Lo que el modelo tiene que saber mientras una descarga espera en la tarjeta."""
    if not pendiente:
        return ''
    return ('\nDESCARGA PENDIENTE EN LA TARJETA (dato de HexOS, no orden): «' + pendiente['summary'] + '» sigue '
            'esperando en la tarjeta de pantalla. La persona todavía NO la ha aprobado ni rechazado y no se ha '
            'bajado nada. Cuando lo decida, HexOS lo anotará aquí con su resultado; mientras no veas esa nota, '
            'no está descargado. No hace falta proponerla otra vez.\n')


def _libre(destino):
    """El mismo nombre, o con (2), (3)… si ya hay un fichero así: no se pisa nada."""
    candidato, n = destino, 1
    while candidato.exists():
        n += 1
        candidato = destino.with_name(f'{destino.stem} ({n}){destino.suffix}')
    return candidato


def _texto(tipo, datos, pdf):
    if tipo == 'application/pdf':
        try:
            return pdf(datos, paginas=PDF_PAGINAS, segundos=PDF_SEGUNDOS)
        except ValueError:
            return ''
    if tipo.startswith('text/') or tipo == 'application/json':
        return datos.decode('utf-8', errors='replace')
    return ''


def aplicar(store, plan, *, descargar=None, pdf=None):
    """Baja el fichero aprobado, lo guarda sin permiso de ejecución y lo relee para comprobarlo."""
    from .chat_backend.document_reading import document_lines
    base = dict(plan_id=plan['plan_id'], summary=plan['summary'], name=plan['name'])

    def negado(motivo):
        return dict(base, executed=False, verified=False, refused=motivo, check='no se ha guardado nada')
    try:
        _, tipo, datos, cortado = (descargar or web.descargar)(plan['url'], MAX_BYTES)
    except ValueError as exc:
        return negado(str(exc))
    if cortado:
        return negado(f'pasa de {tamano(MAX_BYTES)}')
    if tipo != plan['content_type']:
        # Se aprobó un PDF y llega otra cosa: lo aprobado ya no es lo que hay.
        return negado(f'el servidor entrega ahora {tipo} y lo aprobado era {plan["content_type"]}')
    if not datos:
        return negado('el fichero llegó vacío')
    carpeta = raiz()
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = _libre(carpeta / plan['name'])
    parcial = destino.with_name('.' + destino.name + '.parcial')
    with os.fdopen(os.open(parcial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644), 'wb') as salida:
        salida.write(datos)
    os.replace(parcial, destino)
    huella = hashlib.sha256(datos).hexdigest()
    comprobado = hashlib.sha256(destino.read_bytes()).hexdigest() == huella
    texto, documento = _texto(tipo, datos, pdf or web._pdf_text)[:MAX_TEXTO], None
    if len(texto.split()) >= 20:
        documento = dict(id=uuid4().hex, lines=len(document_lines(texto)))
        store.db.execute('INSERT INTO documents VALUES (?,?,?,?)',
                         (documento['id'], now(), texto, hashlib.sha256(texto.encode()).hexdigest()))
    initialize(store)
    store.db.execute('INSERT INTO downloads VALUES (?,?,?,?,?,?,?,?,?)',
                     (uuid4().hex, now(), destino.name, str(destino), plan['url'], tipo, len(datos), huella,
                      documento and documento['id']))
    store.db.commit()
    check = f'{tamano(len(datos))} en {_corta(destino)}'
    check += (f'; lo que dice queda como documento {documento["id"]} de {documento["lines"]} líneas, '
              'que se lee con document_read' if documento else '; no tiene texto que se pueda leer desde aquí')
    return dict(base, name=destino.name, executed=True, verified=comprobado, refused=None, check=check,
                path=_corta(destino), bytes=len(datos), document=documento)


def listado(store, limit=30):
    """Lo descargado, lo más nuevo primero, y con qué documento se lee cada cosa."""
    initialize(store)
    filas = store.db.execute('SELECT * FROM downloads ORDER BY ts DESC LIMIT ?', (limit,)).fetchall()
    total = store.db.execute('SELECT count(*) FROM downloads').fetchone()[0]
    return dict(folder=_corta(raiz()), count=total, downloads=[
        dict(name=f['name'], kind=_clase(f['content_type'], f['name']), size=tamano(f['bytes']), when=f['ts'][:10],
             source=urlparse(f['url']).hostname, document=f['document'], on_disk=Path(f['path']).exists())
        for f in filas],
        note='Los que traen document se leen con document_read usando ese id. Lo que no esté en disco '
             '(on_disk falso) lo ha movido o borrado la persona.')


def _visible(tipo):
    """Con qué tipo se enseña en el navegador, o None si solo se puede guardar."""
    if tipo in A_LA_VISTA:
        return tipo
    if tipo.startswith('text/') or tipo == 'application/json':
        return 'text/plain; charset=utf-8'
    return None


def panel(store, limit=200):
    """Lo descargado, para el panel de la interfaz: lo más nuevo primero."""
    initialize(store)
    filas = store.db.execute('SELECT * FROM downloads ORDER BY ts DESC LIMIT ?', (limit,)).fetchall()
    return dict(folder=_corta(raiz()), downloads=[
        dict(id=f['id'], name=f['name'], kind=_clase(f['content_type'], f['name']), bytes=f['bytes'], ts=f['ts'],
             source=urlparse(f['url']).hostname, url=f['url'], on_disk=Path(f['path']).is_file(),
             viewable=_visible(f['content_type']) is not None, readable=bool(f['document']))
        for f in filas])


def servir(handler, store):
    """GET /api/downloads, /api/downloads/<id> (verlo) y /api/downloads/<id>/download (guardarlo).

    Solo por identificador y solo lo que HexOS descargó y sigue en su carpeta: la ruta
    guardada se vuelve a comprobar, porque la carpeta es de la persona y puede haber cambiado.
    """
    partes = urlparse(handler.path).path.split('/')
    if len(partes) == 3:
        handler.respond(200, panel(store))
        return
    guardar = len(partes) == 5 and partes[4] == 'download'
    if len(partes) not in (4, 5) or (len(partes) == 5 and not guardar):
        handler.respond(404, {'error': 'ruta inexistente'})
        return
    initialize(store)
    fila = store.db.execute('SELECT * FROM downloads WHERE id=?', (partes[3],)).fetchone()
    ruta = Path(fila['path']) if fila else None
    if (ruta is None or ruta.is_symlink() or not ruta.is_file()
            or raiz().resolve() not in ruta.resolve().parents or ruta.stat().st_size > MAX_BYTES):
        handler.respond(404, {'error': 'ese fichero ya no está entre las descargas'})
        return
    contenido = ruta.read_bytes()
    visible = None if guardar else _visible(fila['content_type'])
    handler.send_response(200)
    handler.send_header('Content-Type', visible or 'application/octet-stream')
    handler.send_header('Content-Length', str(len(contenido)))
    handler.send_header('Content-Disposition', ('inline' if visible else 'attachment') +
                        "; filename*=UTF-8''" + quote(fila['name'], safe=''))
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('Cache-Control', 'private, no-store')
    handler.end_headers()
    handler.wfile.write(contenido)
