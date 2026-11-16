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
from urllib.parse import unquote, urlparse
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
        return 'imagen ' + tipo.split('/', 1)[1].upper()
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
