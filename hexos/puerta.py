"""La puerta: usuario y contraseña delante de Helios, para entrar sin estar en Tailscale.

Helios solo se veía dentro de la red privada, y quien llega a la interfaz es Andrés: ve su
conversación, sus notas, su NAS y aprueba tarjetas que cambian su equipo. Para abrirlo a
internet nadie puede pasar sin sesión. nginx (runtime/puerta/nginx.conf) pregunta aquí en
cada petición si la cookie vale (auth_request); sin sesión, la página de entrar. La interfaz y
el agente de detrás no cambian.

Lo que importa:

- **Las contraseñas solo entran por la terminal** (`python3 -m hexos.puerta usuario nuevo X`),
  con getpass, y se guardan con scrypt en un fichero 600. Ni la interfaz ni el chat las ven.
- **La sesión** son 32 bytes al azar en una cookie `__Host-` HttpOnly, Secure y SameSite=Lax;
  en disco solo queda su huella. Caduca a los 30 días sin uso y a los 90 en cualquier caso.
- **Quitar un usuario o cambiarle la contraseña cierra sus sesiones** en el acto.
- **Intentos**: 5 fallos seguidos bloquean ese usuario 15 minutos; 30 fallos en 10 minutos,
  a todos. El aviso de error no dice si el usuario existe.
- **Si algo falla, no se pasa**: un fichero ilegible o legible por otros cierra la puerta.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

COOKIE = '__Host-helios'
NOMBRE = re.compile(r'[a-z0-9][a-z0-9._-]{0,31}')
MIN_CLAVE = 12
MAX_CLAVE = 1024
MAX_CUERPO = 8192
SIN_USO = 30 * 86400
MAXIMO = 90 * 86400
GUARDAR_VISTA = 3600
FALLOS_USUARIO = 5
BLOQUEO_USUARIO = 15 * 60
FALLOS_TODOS = 30
VENTANA_TODOS = 10 * 60
BLOQUEO_TODOS = 10 * 60
SCRYPT = dict(n=2 ** 15, r=8, p=1)
MEMORIA_SCRYPT = 64 * 1024 * 1024
PUERTO = 8096
# El emblema de la cabecera de Helios. La página de entrar no puede pedirlo a la interfaz:
# sin sesión, nginx no deja pasar nada. Lo sirve la puerta.
EMBLEMA = Path(__file__).resolve().parents[1] / 'interfaz' / 'public' / 'helios-emblem.png'


class Rechazo(Exception):
    """No se entra. El texto es para la persona y no dice si el usuario existe."""

    def __init__(self, aviso, bloqueo=False):
        super().__init__(aviso)
        self.aviso = aviso
        self.bloqueo = bloqueo


def config_dir():
    return Path(os.environ.get('HEXOS_PUERTA_CONFIG') or Path.home() / '.config' / 'hexos' / 'puerta')


def estado_dir():
    return Path(os.environ.get('HEXOS_PUERTA_ESTADO') or Path.home() / '.local' / 'state' / 'hexos' / 'puerta')


def _b64(datos):
    return base64.urlsafe_b64encode(datos).decode().rstrip('=')


def _de64(texto):
    return base64.urlsafe_b64decode(texto + '=' * (-len(texto) % 4))


def resumir(clave, sal=None):
    sal = sal or secrets.token_bytes(16)
    hecho = hashlib.scrypt(clave.encode(), salt=sal, maxmem=MEMORIA_SCRYPT, dklen=32, **SCRYPT)
    return 'scrypt$%d$%d$%d$%s$%s' % (SCRYPT['n'], SCRYPT['r'], SCRYPT['p'], _b64(sal), _b64(hecho))


def coincide(clave, guardado):
    try:
        tipo, n, r, p, sal, esperado = guardado.split('$')
        if tipo != 'scrypt':
            return False
        esperado = _de64(esperado)
        calculado = hashlib.scrypt(clave.encode(), salt=_de64(sal), n=int(n), r=int(r), p=int(p),
                                   maxmem=MEMORIA_SCRYPT, dklen=len(esperado))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculado, esperado)


_FALSO = []


def _falso():
    # Con un usuario que no existe se calcula igual un scrypt: que el tiempo de respuesta
    # no diga qué nombres hay.
    if not _FALSO:
        _FALSO.append(resumir(secrets.token_hex(16)))
    return _FALSO[0]


def _huella(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _leer(ruta, vacio):
    try:
        estado = ruta.stat()
    except FileNotFoundError:
        return vacio
    if estado.st_mode & 0o077:
        raise PermissionError(f'{ruta} es legible por otros; corrige con chmod 600')
    return json.loads(ruta.read_text(encoding='utf-8'))


def _escribir(ruta, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporal = ruta.with_name('.' + ruta.name + '.' + secrets.token_hex(4))
    descriptor = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as fichero:
            json.dump(datos, fichero, ensure_ascii=False, indent=1)
        os.replace(temporal, ruta)
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise


def destino(volver):
    """Adónde volver tras entrar: solo una ruta de este mismo sitio."""
    if (isinstance(volver, str) and volver.startswith('/') and not volver.startswith('//')
            and '\\' not in volver and not volver.startswith('/_puerta/') and len(volver) <= 2000
            and not any(ord(c) < 0x20 or ord(c) == 0x7f for c in volver)):
        return volver
    return '/'


def _minutos(segundos):
    minutos = max(1, int(-(-segundos // 60)))
    return '1 minuto' if minutos == 1 else f'{minutos} minutos'


class Puerta:
    """Usuarios, sesiones e intentos. El servidor HTTP es solo su envoltorio."""

    def __init__(self, config=None, estado=None, reloj=time.time):
        self.usuarios_ruta = Path(config or config_dir()) / 'usuarios.json'
        self.sesiones_ruta = Path(estado or estado_dir()) / 'sesiones.json'
        self.reloj = reloj
        self.lock = threading.Lock()
        self._usuarios = {}
        self._marca = None
        self.sesiones = _leer(self.sesiones_ruta, {})
        self.fallos = {}
        self.bloqueado = {}
        self.todos = deque()
        self.todos_hasta = 0.0

    def usuarios(self):
        """Se relee si el fichero cambia: la terminal añade o quita sin reiniciar nada."""
        try:
            estado = self.usuarios_ruta.stat()
            marca = (estado.st_ino, estado.st_mtime_ns, estado.st_size)
        except FileNotFoundError:
            marca = None
        if marca != self._marca:
            self._usuarios = _leer(self.usuarios_ruta, {'usuarios': {}})['usuarios']
            self._marca = marca
        return self._usuarios

    def _guardar(self):
        _escribir(self.sesiones_ruta, self.sesiones)

    def _espera(self, clave, ahora):
        return max(0.0, max(self.bloqueado.get(clave, 0.0), self.todos_hasta) - ahora)

    def _fallo(self, clave, ahora):
        lista = self.fallos.setdefault(clave, deque())
        lista.append(ahora)
        while lista and ahora - lista[0] > BLOQUEO_USUARIO:
            lista.popleft()
        if len(lista) >= FALLOS_USUARIO:
            self.bloqueado[clave] = ahora + BLOQUEO_USUARIO
            lista.clear()
        self.todos.append(ahora)
        while self.todos and ahora - self.todos[0] > VENTANA_TODOS:
            self.todos.popleft()
        if len(self.todos) >= FALLOS_TODOS:
            self.todos_hasta = ahora + BLOQUEO_TODOS
            self.todos.clear()
        # Nombres inventados por quien prueba: que no crezca sin fin.
        if len(self.fallos) > 1000:
            for nombre in [n for n, l in self.fallos.items() if not l or ahora - l[-1] > BLOQUEO_USUARIO]:
                self.fallos.pop(nombre, None)
            for nombre in [n for n, hasta in self.bloqueado.items() if hasta <= ahora]:
                self.bloqueado.pop(nombre, None)

    def entrar(self, usuario, clave):
        """El valor de la cookie de una sesión nueva, o Rechazo."""
        ahora = self.reloj()
        usuario = (usuario or '').strip().lower()
        valido = bool(NOMBRE.fullmatch(usuario))
        contador = usuario if valido else '?'
        with self.lock:
            espera = self._espera(contador, ahora)
            datos = self.usuarios().get(usuario) if valido else None
        if espera:
            raise Rechazo('Demasiados intentos. Prueba otra vez dentro de ' + _minutos(espera) + '.', bloqueo=True)
        clave = clave if isinstance(clave, str) and len(clave) <= MAX_CLAVE else ''
        bien = coincide(clave, datos['clave'] if datos else _falso()) and datos is not None
        with self.lock:
            if not bien:
                self._fallo(contador, ahora)
                raise Rechazo('Usuario o contraseña incorrectos.')
            self.fallos.pop(contador, None)
            token = secrets.token_urlsafe(32)
            self.sesiones[_huella(token)] = dict(usuario=usuario, creada=ahora, vista=ahora)
            for huella in [h for h, s in self.sesiones.items()
                           if ahora - s['vista'] > SIN_USO or ahora - s['creada'] > MAXIMO]:
                del self.sesiones[huella]
            self._guardar()
        return token

    def comprobar(self, token):
        """El usuario de esa sesión, o None."""
        if not token or len(token) > 200:
            return None
        ahora = self.reloj()
        huella = _huella(token)
        with self.lock:
            sesion = self.sesiones.get(huella)
            if not sesion:
                return None
            datos = self.usuarios().get(sesion['usuario'])
            if (not datos or sesion['creada'] < datos.get('sesiones_desde', 0)
                    or ahora - sesion['vista'] > SIN_USO or ahora - sesion['creada'] > MAXIMO):
                del self.sesiones[huella]
                self._guardar()
                return None
            if ahora - sesion['vista'] > GUARDAR_VISTA:
                sesion['vista'] = ahora
                self._guardar()
            return sesion['usuario']

    def salir(self, token):
        if not token:
            return
        with self.lock:
            if self.sesiones.pop(_huella(token), None) is not None:
                self._guardar()


# --- Usuarios, desde la terminal -------------------------------------------------------

def _usuarios_fichero(config=None):
    ruta = Path(config or config_dir()) / 'usuarios.json'
    return ruta, _leer(ruta, {'usuarios': {}})


def nuevo(usuario, clave, config=None, cambiar=False):
    usuario = (usuario or '').strip().lower()
    if not NOMBRE.fullmatch(usuario):
        raise ValueError('El usuario va en minúsculas, con letras, números, «.», «_» o «-», hasta 32.')
    if len(clave) < MIN_CLAVE:
        raise ValueError(f'La contraseña necesita al menos {MIN_CLAVE} caracteres.')
    if len(clave) > MAX_CLAVE:
        raise ValueError('La contraseña es demasiado larga.')
    ruta, datos = _usuarios_fichero(config)
    existe = usuario in datos['usuarios']
    if existe and not cambiar:
        raise ValueError(f'{usuario} ya existe: para cambiarle la contraseña, «usuario clave {usuario}».')
    if cambiar and not existe:
        raise ValueError(f'{usuario} no existe.')
    ahora = time.time()
    previo = datos['usuarios'].get(usuario, {})
    # Cambiar la contraseña cierra las sesiones abiertas con la anterior.
    datos['usuarios'][usuario] = dict(clave=resumir(clave), creado=previo.get('creado', ahora), sesiones_desde=ahora)
    _escribir(ruta, datos)


def quitar(usuario, config=None):
    ruta, datos = _usuarios_fichero(config)
    if datos['usuarios'].pop((usuario or '').strip().lower(), None) is None:
        raise ValueError(f'{usuario} no existe.')
    _escribir(ruta, datos)


def cerrar(usuario, config=None):
    ruta, datos = _usuarios_fichero(config)
    usuario = (usuario or '').strip().lower()
    if usuario not in datos['usuarios']:
        raise ValueError(f'{usuario} no existe.')
    datos['usuarios'][usuario]['sesiones_desde'] = time.time()
    _escribir(ruta, datos)


def lista(config=None):
    return sorted(_usuarios_fichero(config)[1]['usuarios'])


# --- La página de entrar ---------------------------------------------------------------

ESTILO = '''
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 16px;
  background: #0b0b0c; color: #ece8df; font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { width: min(380px, 100%); background: #141416; border: 1px solid #2a2a2e; border-radius: 14px;
  padding: 32px 24px 28px; }
.marca { display: flex; flex-direction: column; align-items: center; gap: 12px; margin-bottom: 22px; }
.emblema { width: 76px; height: 76px; background: #ece8df; filter: drop-shadow(0 0 14px rgba(216, 180, 90, .45));
  -webkit-mask: url(/_puerta/emblema.png) center / contain no-repeat; mask: url(/_puerta/emblema.png) center / contain no-repeat; }
h1 { margin: 0; font: 400 1.75rem/1 "Russo One", system-ui, sans-serif; letter-spacing: .06em; }
p { margin: 0 0 20px; color: #a7a39b; }
.marca p { margin: 0; }
label { display: block; font-size: .9rem; color: #c9c4ba; margin: 14px 0 6px; }
input { width: 100%; padding: 12px; border-radius: 10px; border: 1px solid #34343a; background: #0e0e10;
  color: inherit; font: inherit; }
input:focus { outline: 2px solid #d8b45a; outline-offset: 1px; border-color: transparent; }
button { width: 100%; margin-top: 22px; padding: 12px; border: 0; border-radius: 10px; background: #d8b45a;
  color: #17140c; font: inherit; font-weight: 650; cursor: pointer; }
.aviso { margin: 16px 0 0; padding: 10px 12px; border-radius: 10px; background: #2a1715; color: #ffb4a8; }
'''


def pagina(titulo, cuerpo):
    return ('<!doctype html><html lang="es"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta name="robots" content="noindex">'
            '<link rel="icon" href="/_puerta/emblema.png">'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Russo+One&display=swap">'
            f'<title>{html.escape(titulo)}</title><style>{ESTILO}</style></head>'
            f'<body><main>{cuerpo}</main></body></html>').encode()


def pagina_entrar(volver='/', aviso=''):
    aviso_html = f'<p class="aviso" role="alert">{html.escape(aviso)}</p>' if aviso else ''
    return pagina('Helios · Entrar', f'''
<div class="marca"><span class="emblema" aria-hidden="true"></span><h1>HELIOS</h1>
<p>Entra con tu usuario.</p></div>
<form method="post" action="/_puerta/entrar">
<input type="hidden" name="volver" value="{html.escape(destino(volver))}">
<label for="usuario">Usuario</label>
<input id="usuario" name="usuario" autocomplete="username" autocapitalize="none" autocorrect="off"
 spellcheck="false" required autofocus>
<label for="clave">Contraseña</label>
<input id="clave" name="clave" type="password" autocomplete="current-password" required>
<button type="submit">Entrar</button>
</form>{aviso_html}''')


def pagina_salir():
    return pagina('Helios · Salir', '''
<div class="marca"><span class="emblema" aria-hidden="true"></span><h1>HELIOS</h1>
<p>Cerrar la sesión en este dispositivo.</p></div>
<form method="post" action="/_puerta/salir"><button type="submit">Salir</button></form>''')


CABECERAS_PAGINA = {
    'Content-Security-Policy': "default-src 'none'; img-src 'self'; style-src 'unsafe-inline' "
                               "https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
                               "form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'same-origin',
    'X-Content-Type-Options': 'nosniff',
    'Cache-Control': 'no-store',
}


def make_handler(puerta, registro=sys.stderr):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'puerta'
        sys_version = ''

        def log_message(self, formato, *args):
            pass

        def _apunte(self, texto):
            origen = self.headers.get('X-Forwarded-For') or self.client_address[0]
            print(time.strftime('%Y-%m-%d %H:%M:%S'), origen, texto, file=registro, flush=True)

        def _token(self):
            for trozo in (self.headers.get('Cookie') or '').split(';'):
                nombre, _, valor = trozo.strip().partition('=')
                if nombre == COOKIE:
                    return valor
            return None

        def _responder(self, codigo, cuerpo=b'', tipo='text/html; charset=utf-8', cabeceras=None):
            self.send_response(codigo)
            for nombre, valor in (cabeceras or {}).items():
                self.send_header(nombre, valor)
            if cuerpo:
                self.send_header('Content-Type', tipo)
            self.send_header('Content-Length', str(len(cuerpo)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(cuerpo)

        def _pagina(self, codigo, cuerpo, extra=None):
            self._responder(codigo, cuerpo, cabeceras={**CABECERAS_PAGINA, **(extra or {})})

        def _error(self, codigo, texto):
            # Siempre una página: un error sin cuerpo, Chrome en iPhone lo bajaba como «entrar.txt».
            self._pagina(codigo, pagina('Helios', '<div class="marca"><span class="emblema" aria-hidden="true">'
                         '</span><h1>HELIOS</h1></div><p class="aviso" role="alert">' + html.escape(texto) +
                         '</p><form method="get" action="/_puerta/entrar"><button type="submit">Volver a entrar'
                         '</button></form>'))

        def _mismo_sitio(self):
            # Sec-Fetch-Site lo pone el navegador y una página ajena no puede falsearlo: si
            # viene, manda. El 18/11 Chrome en iPhone mandó «same-origin» con «Origin: null»
            # (la página pedía no-referrer) y la comparación de Origin lo rechazaba.
            sitio = self.headers.get('Sec-Fetch-Site')
            if sitio:
                return sitio in ('same-origin', 'none')
            origen = self.headers.get('Origin')
            if origen is None:
                return True
            return urlsplit(origen).netloc == (self.headers.get('Host') or '')

        def _sin_sesion(self):
            original = self.headers.get('X-Original-URI') or '/'
            if self.command not in ('GET', 'HEAD') or urlsplit(original).path.startswith('/api/'):
                cuerpo = json.dumps({'error': 'Sin sesión: vuelve a entrar en Helios.'}, ensure_ascii=False).encode()
                self._responder(401, cuerpo, 'application/json; charset=utf-8', {'Cache-Control': 'no-store'})
                return
            self._responder(302, cabeceras={'Location': '/_puerta/entrar?volver=' + quote(destino(original), safe=''),
                                            'Cache-Control': 'no-store'})

        def do_GET(self):
            ruta = urlsplit(self.path)
            try:
                if ruta.path == '/_puerta/comprobar':
                    usuario = puerta.comprobar(self._token())
                    if usuario:
                        self._responder(204, cabeceras={'X-Puerta-Usuario': usuario})
                    else:
                        self._responder(401)
                elif ruta.path == '/_puerta/sin-sesion':
                    self._sin_sesion()
                elif ruta.path == '/_puerta/entrar':
                    volver = destino(parse_qs(ruta.query).get('volver', ['/'])[0])
                    if puerta.comprobar(self._token()):
                        self._responder(303, cabeceras={'Location': volver, 'Cache-Control': 'no-store'})
                    else:
                        self._pagina(200, pagina_entrar(volver))
                elif ruta.path == '/_puerta/salir':
                    self._pagina(200, pagina_salir())
                elif ruta.path == '/_puerta/emblema.png':
                    self._responder(200, EMBLEMA.read_bytes(), 'image/png',
                                    {'Cache-Control': 'public, max-age=86400', 'X-Content-Type-Options': 'nosniff'})
                else:
                    self._error(404, 'Esa dirección no existe.')
            except Exception as exc:
                # Cerrada ante cualquier duda: nginx no deja pasar un 500.
                self._apunte('error: ' + type(exc).__name__ + ': ' + str(exc)[:200])
                self._error(500, 'Algo ha fallado en la puerta. Prueba otra vez en un momento.')

        do_HEAD = do_GET

        def _cuerpo(self):
            try:
                largo = int(self.headers.get('Content-Length') or 0)
            except ValueError:
                return None
            if largo < 0 or largo > MAX_CUERPO:
                return None
            datos = parse_qs(self.rfile.read(largo).decode('utf-8', 'replace'), keep_blank_values=True)
            return {clave: valores[0] for clave, valores in datos.items()}

        def do_POST(self):
            ruta = urlsplit(self.path).path
            try:
                if ruta == '/_puerta/sin-sesion':
                    self._sin_sesion()
                    return
                if ruta not in ('/_puerta/entrar', '/_puerta/salir'):
                    self._error(404, 'Esa dirección no existe.')
                    return
                if not self._mismo_sitio():
                    self._apunte('rechazado: otro origen en ' + ruta + ' (Origin=' + str(self.headers.get('Origin'))
                                 + ', Sec-Fetch-Site=' + str(self.headers.get('Sec-Fetch-Site')) + ')')
                    self._error(403, 'El navegador no confirmó que el formulario venía de esta página. '
                                     'Vuelve a entrar y prueba otra vez.')
                    return
                if ruta == '/_puerta/salir':
                    puerta.salir(self._token())
                    self._responder(303, cabeceras={
                        'Location': '/_puerta/entrar', 'Cache-Control': 'no-store',
                        'Set-Cookie': f'{COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax'})
                    return
                campos = self._cuerpo()
                if campos is None:
                    self._error(413, 'El formulario es demasiado grande.')
                    return
                volver = destino(campos.get('volver', '/'))
                usuario = campos.get('usuario', '')
                try:
                    token = puerta.entrar(usuario, campos.get('clave', ''))
                except Rechazo as rechazo:
                    self._apunte(('bloqueado: ' if rechazo.bloqueo else 'fallo: ') + usuario.strip().lower()[:40])
                    self._pagina(429 if rechazo.bloqueo else 401, pagina_entrar(volver, rechazo.aviso))
                    return
                self._apunte('entra: ' + usuario.strip().lower())
                self._responder(303, cabeceras={
                    'Location': volver, 'Cache-Control': 'no-store',
                    'Set-Cookie': f'{COOKIE}={token}; Path=/; Max-Age={MAXIMO}; HttpOnly; Secure; SameSite=Lax'})
            except Exception as exc:
                self._apunte('error: ' + type(exc).__name__ + ': ' + str(exc)[:200])
                self._error(500, 'Algo ha fallado en la puerta. Prueba otra vez en un momento.')

        do_PUT = do_PATCH = do_DELETE = do_POST

    return Handler


def servir(puerto=PUERTO):
    puerta = Puerta()
    puerta.usuarios()           # que un fichero mal puesto se vea al arrancar, no al primer intento
    servidor = ThreadingHTTPServer(('127.0.0.1', puerto), make_handler(puerta))
    servidor.daemon_threads = True
    print(f'Puerta de Helios: http://127.0.0.1:{puerto}', flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


def _pedir_clave():
    if not sys.stdin.isatty():
        primera = sys.stdin.readline().rstrip('\n')
        segunda = sys.stdin.readline().rstrip('\n')
    else:
        primera = getpass.getpass('Contraseña (no se ve al escribir): ')
        segunda = getpass.getpass('Repítela: ')
    if primera != segunda:
        raise ValueError('Las dos contraseñas no coinciden.')
    return primera


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python3 -m hexos.puerta', description=__doc__.split('\n')[0])
    ordenes = parser.add_subparsers(dest='orden', required=True)
    servidor = ordenes.add_parser('servir', help='el servicio al que pregunta nginx')
    servidor.add_argument('--puerto', type=int, default=PUERTO)
    usuario = ordenes.add_parser('usuario', help='añadir, quitar o ver usuarios')
    acciones = usuario.add_subparsers(dest='accion', required=True)
    for nombre, ayuda in (('nuevo', 'crear un usuario; pide la contraseña'),
                          ('clave', 'cambiar la contraseña; cierra sus sesiones'),
                          ('quitar', 'quitar un usuario; cierra sus sesiones'),
                          ('cerrar', 'cerrar sus sesiones abiertas')):
        accion = acciones.add_parser(nombre, help=ayuda)
        accion.add_argument('nombre')
    acciones.add_parser('lista', help='ver los usuarios')
    args = parser.parse_args(argv)
    try:
        if args.orden == 'servir':
            servir(args.puerto)
        elif args.accion in ('nuevo', 'clave'):
            nuevo(args.nombre, _pedir_clave(), cambiar=args.accion == 'clave')
            print('Hecho.' if args.accion == 'nuevo' else 'Contraseña cambiada; sus sesiones se han cerrado.')
        elif args.accion == 'quitar':
            quitar(args.nombre)
            print('Quitado; sus sesiones se han cerrado.')
        elif args.accion == 'cerrar':
            cerrar(args.nombre)
            print('Sesiones cerradas.')
        else:
            print('\n'.join(lista()) or '(ninguno)')
    except (ValueError, PermissionError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
