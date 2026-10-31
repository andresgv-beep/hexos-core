#!/usr/bin/python3
"""Banco de cadenas: ¿completa Helios una tarea de varios pasos sin que le lleven de la mano?

Cada caso arranca sin historial, sin notas y sin memoria: un espacio de trabajo
nuevo y el KV vacío. En la conversación real el modelo acierta porque tiene delante
las correcciones de otros días; aquí solo cuentan el prompt del sistema y las
herramientas, que es lo que queremos medir.

Modelo real y Agent completo, igual que media_conversation_live.py. Lo que no es
real es el borde: el NAS se simula con el listado guardado en nas.json, la web con
respuestas fijas y la cola de compresión no tiene worker. No se abre ninguna
conexión al NAS ni se escribe fuera de --salida.

Mide si la cadena termina, no si la primera llamada acierta: tarea cumplida,
empujones (turnos extra de la persona, sin contar la confirmación de comprimir),
llamadas, fallos y llamadas repetidas.

Helios debe estar parado (GPU). Primero se saca el listado, una sola vez:

    python3 tools/banco_cadenas.py --crear-nas --salida ~/Documentos/banco-cadenas
    systemd-run --user --scope -p MemoryMax=16G /usr/bin/python3 tools/banco_cadenas.py \\
        --salida ~/Documentos/banco-cadenas

Deja resultados.jsonl, resumen.json y resumen.md con cada conversación para leerla
a mano: el veredicto solo mira hechos comprobables, no si la respuesta es buena.
--grupo-correcto repite el banco ofreciendo solo las herramientas del caso, sin
tocar el catálogo, para saber cuánto ayuda centrar al modelo.
"""
import argparse
import base64
import json
import posixpath
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
CORE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CORE))

RELEASE = Path.home() / 'Documentos/hexos-prueba-12b/release.env'
GB = 10 ** 9
VIDEO = {'.mkv', '.mp4', '.m4v', '.avi', '.mov', '.wmv', '.ts', '.m2ts', '.mpg', '.mpeg', '.iso'}
# Prefijos del listado real. Solo bibliotecas: el resto del NAS no pinta nada aquí
# y tiene carpetas privadas que no deben acabar en el archivo de resultados.
PREFIJOS = {'synology 1': ('/volume1/multimedia 1/', '/volume4/multimedia 3/'),
            'synology home': ('/volume1/multimedia/',)}
# Carpetas que existen pero no se pueden leer, como en el NAS de verdad.
SIN_PERMISO = {'synology 1': ['/volume1/garage', '/volume1/Download', '/volume1/music'], 'synology home': []}
VACIAS = {'synology 1': ['/volume1/Compartido', '/volume1/docker'], 'synology home': ['/volume1/DATA_1', '/volume1/DATA_2']}
DOCUMENTO = dict(path='/volume1/Compartido/mantenimiento/notas-raid.txt',
                 texto='Revisión del RAID del 12 de octubre.\nEl disco sdc dio errores de lectura y se cambió.\n'
                       'Los demás discos están bien.\n')
ESPACIO = {'synology 1': dict(total_gb=43600, free_gb=6120), 'synology home': dict(total_gb=21800, free_gb=9340)}
WEB = dict(buena='https://www.home-assistant.io/blog/2026/10/01/release-202610/',
           mala='https://community.example.org/t/ultima-version-home-assistant')


def crear_nas(workspace, salida):
    """Último estado conocido de cada carpeta según lo guardado por Helios; no conecta con el NAS."""
    db = sqlite3.connect(f'file:{workspace}/nas_files.sqlite?mode=ro', uri=True)
    nas, carpetas = {}, {}
    for device, prefijos in PREFIJOS.items():
        archivos = {}
        for scan, roots, coverage in db.execute('SELECT id, roots, coverage FROM scans WHERE device=? ORDER BY observed_at',
                                                (device,)).fetchall():
            cobertura = json.loads(coverage)
            extensiones = cobertura.get('indexed_extensions') or []
            # Un recorrido nuevo sustituye a los anteriores: lo borrado o comprimido ya no está.
            for root in json.loads(roots) if cobertura.get('complete') else ():
                dentro = root.rstrip('/') + '/'
                for path in [p for p in archivos if p.startswith(dentro)]:
                    if not extensiones or posixpath.splitext(path)[1].lower().lstrip('.') in extensiones:
                        del archivos[path]
            for path, size in db.execute('SELECT path, size_bytes FROM files WHERE scan_id=?', (scan,)):
                if path.startswith(prefijos) and '/@' not in path and size is not None:
                    archivos[path] = size
        nas[device] = sorted(archivos.items())
        carpetas[device] = sorted(r[0] for r in db.execute('SELECT path FROM directories WHERE device=?', (device,))
                                  if r[0].startswith(prefijos) and '/@' not in r[0])
    salida.mkdir(parents=True, exist_ok=True)
    (salida / 'nas.json').write_text(json.dumps(dict(nas, _carpetas=carpetas), ensure_ascii=False))
    return {k: (len(nas[k]), len(carpetas[k])) for k in nas}


class NAS:
    """Mismo formato que nas_files_remote.collect y nas_shares_remote, sobre un listado."""

    def __init__(self, listado):
        self.archivos = {d: dict(v) for d, v in listado.items() if not d.startswith('_')}
        self.archivos['synology 1'][DOCUMENTO['path']] = len(DOCUMENTO['texto'].encode())
        self.carpetas = {}
        for device, archivos in self.archivos.items():
            carpetas = set(VACIAS[device]) | set(SIN_PERMISO[device]) | set(listado.get('_carpetas', {}).get(device, []))
            for path in archivos:
                padre = posixpath.dirname(path)
                while padre not in ('/', ''):
                    carpetas.add(padre)
                    padre = posixpath.dirname(padre)
            self.carpetas[device] = carpetas

    def raices(self, device):
        return sorted({'/'.join(c.split('/')[:2]) for c in self.carpetas[device]})

    def registro(self, device, path, root, carpeta=False):
        size = None if carpeta else self.archivos[device][path]
        ext = posixpath.splitext(path)[1].lower()
        return dict(path=path, root=root, name=posixpath.basename(path), kind='directory' if carpeta else 'file',
                    size_bytes=size, mtime_ns=1, filesystem_id='37', inode=abs(hash(path)) % 10 ** 9,
                    media_kind='video' if not carpeta and ext in VIDEO else 'other')

    def recorrer(self, device, request):
        roots = request.get('roots')
        automatica = request['operation'] in ('find', 'directories') and roots is None
        roots = self.raices(device) if automatica else roots
        items, errores = [], []
        extensiones = request.get('extensions') or []
        q = request.get('query', '').casefold()
        coincide = lambda n: n.casefold() == q if request.get('exact') else q in n.casefold()
        visitadas = 0
        for root in roots:
            if root not in self.carpetas[device]:
                errores.append(dict(path=root, errno=2, reason='invalid_or_unreadable_root'))
                continue
            dentro = root.rstrip('/') + '/'
            for carpeta in sorted(self.carpetas[device]):
                if carpeta in SIN_PERMISO[device] and (carpeta == root or carpeta.startswith(dentro)):
                    errores.append(dict(path=carpeta, errno=13, reason='directory_unreadable'))
            if request['operation'] == 'directories':
                items += [self.registro(device, c, root, True) for c in sorted(self.carpetas[device])
                          if (c == root or c.startswith(dentro)) and coincide(posixpath.basename(c))]
                continue
            for path in self.archivos[device]:
                if path.startswith(dentro):
                    visitadas += 1
                    ext = posixpath.splitext(path)[1].lower().lstrip('.')
                    if not extensiones or ext in extensiones:
                        items.append(self.registro(device, path, root))
        return dict(items=items, errors=errores, complete=not errores, roots=roots, auto_discovered=automatica,
                    excludes_hidden=True, indexed_extensions=extensiones, stopped_reason=None, visited_entries=visitadas,
                    skipped=dict(symlinks=0, special=0, mount_boundaries=0, hidden=0),
                    filesystems={r: '37' for r in roots if r in self.carpetas[device]})

    def browse(self, device, request):
        path = request['roots'][0].rstrip('/') or '/'
        base = dict(errors=[], complete=True, roots=[path], auto_discovered=False, excludes_hidden=False,
                    indexed_extensions=[], stopped_reason=None, skipped=dict(symlinks=0, special=0, mount_boundaries=0, hidden=0),
                    filesystems={})
        if path in SIN_PERMISO[device] or (path != '/' and path not in self.carpetas[device]):
            motivo = 'directory_unreadable' if path in SIN_PERMISO[device] else 'invalid_or_unreadable_root'
            return dict(base, items=[], total_entries=0, next_offset=None, visited_entries=0, complete=False,
                        errors=[dict(path=path, errno=13 if path in SIN_PERMISO[device] else 2, reason=motivo)])
        hijos = [c for c in self.carpetas[device] if posixpath.dirname(c) == path]
        archivos = [p for p in self.archivos[device] if posixpath.dirname(p) == path]
        items = ([self.registro(device, c, path, True) for c in sorted(hijos)] +
                 [self.registro(device, p, path) for p in sorted(archivos)])
        offset, limit = request.get('offset', 0), request.get('limit', 30)
        fin = offset + limit
        return dict(base, items=items[offset:fin], total_entries=len(items), visited_entries=len(items),
                    next_offset=fin if fin < len(items) else None)

    def __call__(self, device, request):
        device = device or 'synology 1'
        if device not in self.archivos:
            raise ValueError('Equipo desconocido: ' + str(device))
        operacion = request['operation']
        if operacion == 'shares':
            items = [dict(name=posixpath.basename(c), path=c, kind='directory', size_bytes=None,
                          readable=c not in SIN_PERMISO[device], access_errno=13 if c in SIN_PERMISO[device] else None)
                     for c in sorted(self.carpetas[device]) if c.count('/') == 2]
            resultado = dict(items=items, complete=True, errors=[], source='/etc/samba/smb.share.conf')
        elif operacion == 'file_open':
            resultado = dict(content_base64=base64.b64encode(DOCUMENTO['texto'].encode()).decode())
        elif operacion == 'browse':
            resultado = self.browse(device, request)
        else:
            resultado = self.recorrer(device, request)
        return dict(resultado, device=device, observed_at='2026-10-31T12:00:00+00:00')


def lectura_nas(workspace, *, device=None, section=None, **_):
    from hexos.agent import hosts
    device = hosts.match(workspace, device) or device if device else device
    if section not in ('space', 'storage') or device not in ESPACIO:
        raise ValueError('En este banco solo está la sección space de los dos NAS')
    datos = ESPACIO[device]
    return dict(device=device, section=section, observed_at='2026-10-31T12:00:00+00:00',
                volumes=[dict(path='/volume1', total_gb=datos['total_gb'], free_gb=datos['free_gb'])])


def buscar_web(query, limit=5, recency=None):
    return dict(query=query, results=[
        dict(title='Última versión de Home Assistant - foro', url=WEB['mala'], snippet='Hilo sobre la última versión.'),
        dict(title='Home Assistant 2026.10 release', url=WEB['buena'], snippet='Notas de la versión de octubre.')])


def leer_web(url):
    if url == WEB['buena']:
        return dict(url=url, title='Home Assistant 2026.10', text='Ya está disponible Home Assistant 2026.10.3, '
                    'la última versión estable, publicada en octubre de 2026.')
    raise ValueError('Fuente bloqueada: la web ha rechazado la lectura automática (403)')


def nada(*args, **kwargs):
    raise ValueError('No disponible en este banco')


def dependencias(root, nas):
    from hexos.agent import hosts
    from hexos.agent.chat_backend.state import AgentDependencies
    from hexos.agent.file_catalog import file_access
    from hexos.agent.file_catalog.directories import DirectoryCatalog
    from hexos.agent.file_catalog.service import FileCatalog
    from hexos.agent.file_catalog.sqlite_repository import SQLiteCatalog

    def equipo(device):
        return hosts.match(root, device) or device if device else device

    def archivos(workspace, *, operation, **kw):
        if 'device' in kw:
            kw['device'] = equipo(kw['device'])
        servicio = FileCatalog(nas, SQLiteCatalog(root))
        carpetas = DirectoryCatalog(nas, SQLiteCatalog(root))
        if operation == 'file_open':
            return file_access.open_file(root, nas, **kw)
        if operation == 'file_read':
            return file_access.read(root, **kw)
        if operation in ('directories', 'shares'):
            return getattr(carpetas, operation)(**kw)
        if operation == 'directory_page':
            return carpetas.page(**kw)
        return getattr(servicio, operation)(**kw)
    return AgentDependencies(nas_files=archivos, nas_read=lectura_nas, web_search=buscar_web, web_read=leer_web)


# ------------------------------------------------------------------ casos

def rutas_cola(root):
    from hexos.agent.media_jobs.store import JobStore
    store = JobStore(root)
    try:
        return sorted(j['path'] if 'path' in j else j['source']['path'] for b in store.listing() for j in b['jobs'])
    finally:
        store.close()


def videos(nas, device, *carpetas):
    return {p: s for p, s in nas.archivos[device].items()
            if posixpath.splitext(p)[1].lower() in VIDEO and any(p.startswith(c.rstrip('/') + '/') for c in carpetas)}


def localizar(nas, texto, device='synology 1'):
    return sorted(p for p in nas.archivos[device] if texto.casefold() in posixpath.basename(p).casefold())


def num(reply):
    return reply.replace('.', '').replace(',', '.')


class Caso:
    def __init__(self, id, turnos, grupo, comprobar, confirmar=0):
        # `confirmar`: pedir permiso antes de comprimir es correcto, no cuenta como ayuda.
        self.id, self.turnos, self.grupo, self.comprobar, self.confirmar = id, turnos, grupo, comprobar, confirmar


ARCHIVOS = ('nas.locations', 'nas.directories', 'nas.directory_page', 'nas.shares', 'nas.find', 'nas.search',
            'nas.browse', 'nas.file_open', 'nas.file_read')
MULTIMEDIA = ARCHIVOS + ('media.options', 'media.prepare', 'media.start', 'media.control', 'media.jobs', 'media.job')


def casos(nas):
    """Peticiones como las de la charla real: sin rutas buenas y sin decir qué herramienta usar."""
    marvel = [c for c in nas.carpetas['synology 1'] if c.casefold().endswith('/marvel')]
    peliculas = [c for c in nas.carpetas['synology 1'] if posixpath.basename(c).casefold() == 'peliculas'
                 and c.count('/') == 4]
    pelis = videos(nas, 'synology 1', *peliculas)
    tres = sorted(sorted(pelis, key=pelis.get)[-3:])
    en_marvel = videos(nas, 'synology 1', *marvel)
    spider = [p for p in localizar(nas, 'Brand New Day') if p in en_marvel]
    capitana = [p for p in en_marvel if 'capitana marvel' in p.casefold()]
    avatar = sorted((p for p in videos(nas, 'synology 1', *peliculas) if 'avatar' in posixpath.basename(p).casefold()),
                    key=pelis.get)
    inter = [p for p in localizar(nas, 'interstellar') if posixpath.splitext(p)[1].lower() in VIDEO]
    rango = sorted(p for p, s in en_marvel.items() if 15 * GB <= s <= 25 * GB)

    def cola_es(esperadas):
        def comprobar(root, reply):
            hay = rutas_cola(root)
            return hay == sorted(esperadas), 'en cola: ' + json.dumps(hay, ensure_ascii=False)
        return comprobar

    def cita(*textos):
        def comprobar(root, reply):
            falta = [t for t in textos if t.casefold() not in reply.casefold()]
            return not falta, 'falta en la respuesta: ' + ', '.join(falta) if falta else 'datos presentes'
        return comprobar

    def nota(root, reply):
        db = sqlite3.connect(Path(root) / 'work.sqlite')
        try:
            texto = ' '.join(str(c) for fila in db.execute('SELECT * FROM notes') for c in fila)
        finally:
            db.close()
        return '2026.10.3' in texto, 'nota con 2026.10.3' if '2026.10.3' in texto else 'sin nota con la versión'

    def cuenta(root, reply):
        n = str(len(en_marvel))
        return bool(re.search(r'(?<![\d.,])' + n + r'(?![\d.,])', reply)), 'esperaba ' + n

    def gb_interstellar(root, reply):
        gb = nas.archivos['synology 1'][inter[0]] / GB
        cifras = [float(x) for x in re.findall(r'\d+(?:\.\d+)?', num(reply))]
        ok = 'synology 1' in reply.casefold() and any(abs(c - gb) < .6 for c in cifras)
        return ok, f'esperaba synology 1 y {gb:.1f} GB'

    def mas_libre(root, reply):
        return 'synology home' in reply.casefold() and '9340' in re.sub(r'[.,\s]', '', reply), \
            'esperaba synology home con 9340 GB'

    def ruta_real(root, reply):
        ok = 'multimedia 3' in reply and 'marvel' in reply.casefold()
        return ok, 'esperaba la carpeta real: ' + (capitana[0] if capitana else '¿sin fixture?')

    return [
        Caso('comprimir-titulo', ['Comprime la película Spider-Man Brand New Day'], MULTIMEDIA, cola_es(spider[:1]), 1),
        Caso('ruta-equivocada', ['Busca la película Capitana Marvel en /volume1/multimedia del synology 1'], ARCHIVOS, ruta_real),
        Caso('contar-carpeta', ['¿Cuántas películas hay en las carpetas marvel del synology 1?'], ARCHIVOS, cuenta),
        Caso('tres-pesadas', ['Comprime las 3 películas más pesadas de las carpetas peliculas del synology 1'],
             MULTIMEDIA, cola_es(tres), 1),
        Caso('rango', ['Comprime las películas de marvel del synology 1 que ocupen entre 15 y 25 GB'], MULTIMEDIA, cola_es(rango), 1),
        Caso('que-nas', ['¿En qué NAS está Interstellar y cuánto ocupa?'], ARCHIVOS, gb_interstellar),
        Caso('leer-documento', ['En Compartido del synology 1 hay un archivo notas-raid.txt. ¿Qué disco falló?'],
             ARCHIVOS, cita('sdc')),
        Caso('dos-nas', ['¿Cuál de mis dos NAS tiene más espacio libre y cuánto?'], ('device.list', 'nas.read'), mas_libre),
        Caso('web-y-nota', ['Mira en internet cuál es la última versión de Home Assistant y apúntala en una nota'],
             ('web.search', 'web.read', 'note.save', 'note.list', 'note.get'), nota),
        Caso('seguir-turno', ['Busca las películas de Avatar en las carpetas peliculas del synology 1',
                              'Comprime la que menos ocupe'], MULTIMEDIA, cola_es(avatar[:1]), 1),
    ]


# ------------------------------------------------------------------ ejecución

EMPUJON = 'Sí, adelante. No sé la ruta exacta, búscalo tú.'
MAX_EMPUJONES = 3


def preparar(root, media):
    from hexos.agent import hosts
    from hexos.agent.media_jobs.configuration import load
    from hexos.agent.media_jobs.planning import ensure
    from hexos.agent.media_jobs.store import JobStore
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    shutil.copy2(media, root / 'media_jobs.json')
    hosts.save(root, 'synology 1', 'banco', 'no-es-una-credencial', host='192.0.2.1')
    hosts.save(root, 'synology home', 'banco', 'no-es-una-credencial', host='192.0.2.2')
    store = JobStore(root)
    ensure(store.db)
    cfg = load(root)
    store.db.execute('INSERT OR REPLACE INTO media_service VALUES (?,?,?)',
                     (cfg['resource'], time.time() + 86400, json.dumps(dict(ready=True, config_digest=cfg['digest']))))
    store.close()


def eventos(agent):
    with agent.store() as store:
        return [json.loads(r[0]) for r in store.db.execute('SELECT body FROM tool_events ORDER BY seq')]


def medir(eventos_caso):
    firmas = Counter(json.dumps([e['tool'], e.get('arguments')], sort_keys=True, ensure_ascii=False) for e in eventos_caso)
    return dict(llamadas=len(eventos_caso), fallos=sum(1 for e in eventos_caso if e.get('failed')),
                repetidas=sum(n - 1 for n in firmas.values()), herramientas=[
                    e['tool'] + ('!' if e.get('failed') else '') for e in eventos_caso])


def ejecutar(caso, root, runtime, nas, media, solo_grupo=False):
    from hexos.agent.chat import Agent
    preparar(root, media)
    runtime.call(dict(type='reset'))
    completas = runtime.tools
    if solo_grupo:
        nombres = {n.replace('.', '_') for n in caso.grupo}
        runtime.tools = [t for t in completas if t['function']['name'] in nombres]
    agent = Agent(root, runtime, dependencies=dependencias(root, nas))
    charla, ok, detalle, empujones, inicio = [], False, '', 0, time.time()
    try:
        pendientes = list(caso.turnos)
        while True:
            texto = pendientes.pop(0) if pendientes else EMPUJON
            try:
                reply = agent.chat(texto).get('reply') or ''
            except RuntimeError as exc:
                # En la charla real el turno muere igual: el presupuesto agotado cuenta como no cumplido.
                charla += [dict(role='persona', text=texto), dict(role='helios', text='[turno cortado] ' + str(exc))]
                ok, detalle = False, str(exc)
                break
            charla += [dict(role='persona', text=texto), dict(role='helios', text=reply)]
            if not pendientes:
                ok, detalle = caso.comprobar(root, reply)
                if ok or empujones == MAX_EMPUJONES:
                    break
                empujones += 1
    finally:
        runtime.tools = completas
    return dict(caso=caso.id, ok=bool(ok), detalle=detalle, empujones=max(0, empujones - caso.confirmar), segundos=round(time.time() - inicio, 1),
                contexto=getattr(runtime, 'kv_position', None), **medir(eventos(agent)), charla=charla)


def resumir(filas, modo):
    n = len(filas) or 1
    resumen = dict(modo=modo, casos=len(filas), cumplidos=sum(f['ok'] for f in filas),
                   sin_ayuda=sum(f['ok'] and not f['empujones'] for f in filas),
                   empujones=sum(f['empujones'] for f in filas), llamadas=sum(f['llamadas'] for f in filas),
                   fallos=sum(f['fallos'] for f in filas), repetidas=sum(f['repetidas'] for f in filas),
                   segundos_por_caso=round(sum(f['segundos'] for f in filas) / n, 1))
    lineas = [f'# Banco de cadenas ({modo})', '',
              f"Cumplidos {resumen['cumplidos']}/{len(filas)}, sin ayuda {resumen['sin_ayuda']}/{len(filas)}, "
              f"{resumen['empujones']} empujones, {resumen['llamadas']} llamadas, {resumen['fallos']} fallos, "
              f"{resumen['repetidas']} repetidas.", '',
              '| Caso | Cumplido | Empujones | Llamadas | Fallos | Repetidas |', '|---|---|---:|---:|---:|---:|']
    lineas += [f"| {f['caso']} | {'sí' if f['ok'] else 'NO'} | {f['empujones']} | {f['llamadas']} | {f['fallos']} | "
               f"{f['repetidas']} |" for f in filas]
    for f in filas:
        lineas += ['', f"## {f['caso']}", '', f"Veredicto: {f['detalle']}", '',
                   'Herramientas: ' + (' → '.join(f['herramientas']) or 'ninguna'), '']
        lineas += [f"**{m['role']}:** {m['text']}\n" for m in f['charla']]
    return resumen, '\n'.join(lineas) + '\n'


def leer_release():
    entorno = {}
    for linea in RELEASE.read_text().splitlines():
        if '=' in linea and not linea.startswith('#'):
            clave, valor = linea.split('=', 1)
            entorno[clave] = shlex.split(valor)[0] if valor else ''
    return entorno


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--salida', type=Path, required=True)
    parser.add_argument('--crear-nas', action='store_true', help='Copia el listado guardado por Helios y termina')
    parser.add_argument('--casos', help='Ids separados por comas')
    parser.add_argument('--grupo-correcto', action='store_true', help='Ofrece solo las herramientas del caso')
    parser.add_argument('--ctx', type=int, help='Ventana; por defecto la de release.env')
    parser.add_argument('--pensar', action='store_true', help='Abre el canal de pensamiento en todos los turnos')
    args = parser.parse_args()
    env = leer_release()
    args.salida = args.salida.expanduser()
    if args.crear_nas:
        print(crear_nas(env['HEXOS_WORKSPACE'], args.salida))
        return
    apps = subprocess.check_output(['nvidia-smi', '--query-compute-apps=process_name', '--format=csv,noheader'], text=True)
    if 'helios_runtime' in apps:
        raise SystemExit('Hay un motor cargado en la GPU: para Helios antes de medir.')
    from hexos.agent.native import NativeRuntime
    nas = NAS(json.loads((args.salida / 'nas.json').read_text()))
    elegidos = set(args.casos.split(',')) if args.casos else None
    lista = [c for c in casos(nas) if not elegidos or c.id in elegidos]
    modo = 'grupo-correcto' if args.grupo_correcto else 'catalogo-entero'
    carpeta = args.salida / modo
    carpeta.mkdir(parents=True, exist_ok=True)
    runtime = NativeRuntime(env['HEXOS_RUNTIME'], env['HEXOS_MODEL'], args.ctx or int(env['HEXOS_CTX']), carpeta,
                            env['HEXOS_TEMPLATE'], thinking=args.pensar)
    filas = []
    try:
        with (carpeta / 'resultados.jsonl').open('w') as salida:
            for caso in lista:
                fila = ejecutar(caso, carpeta / 'espacios' / caso.id, runtime, nas,
                                Path(env['HEXOS_WORKSPACE']) / 'media_jobs.json', args.grupo_correcto)
                filas.append(fila)
                salida.write(json.dumps(fila, ensure_ascii=False) + '\n')
                salida.flush()
                print(json.dumps({k: fila[k] for k in ('caso', 'ok', 'empujones', 'llamadas', 'fallos', 'repetidas', 'segundos', 'contexto',
                                                       'herramientas', 'detalle')}, ensure_ascii=False), flush=True)
    finally:
        runtime.close()
    resumen, texto = resumir(filas, modo)
    (carpeta / 'resumen.json').write_text(json.dumps(resumen, ensure_ascii=False, indent=1))
    (carpeta / 'resumen.md').write_text(texto)
    print('RESUMEN', json.dumps(resumen, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
