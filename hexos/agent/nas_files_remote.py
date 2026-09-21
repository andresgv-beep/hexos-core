"""Lector enviado por SSH: biblioteca estándar, sin instalar ni escribir en el NAS.

Se ejecuta con Python 3 del NAS. No importa módulos del agente y solo devuelve
metadatos. Un recorrido incompleto se identifica explícitamente.
"""
import base64
import json
import os
import re
import stat
import sys
import time

MARKER = '__HEXOS_FILES_V1__'
MAX_ENTRIES = 100000
MAX_FIND_ENTRIES = 1000000
MAX_SECONDS = 25
MAX_PAYLOAD = 12 * 1024 * 1024
VIDEO = frozenset('.mkv .mp4 .m4v .avi .mov .wmv .ts .m2ts .mts .webm .mpg .mpeg .vob .iso'.split())


def discover_data_roots(include_hidden=False):
    """Volúmenes de datos Synology observados, no rutas supuestas por el modelo.

    Los subvolúmenes Btrfs pueden tener otro st_dev sin figurar como un montaje
    separado. Añadimos sus carpetas compartidas como raíces explícitas.
    """
    roots, errors = [], []
    with open('/proc/self/mountinfo') as source:
        mounts = [re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), line.split()[4])
                  for line in source if len(line.split()) > 4]
    volumes = sorted({path for path in mounts
                      if re.fullmatch(r'/volume[0-9]+|/volumeUSB[0-9]+(?:/[^/]+)?', path)})
    for volume in volumes:
        roots.append(volume)
        descriptor = None
        try:
            descriptor = open_directory(volume)
            device = os.fstat(descriptor).st_dev
            with os.scandir(descriptor) as entries:
                for entry in entries:
                    if not include_hidden and entry.name.startswith(('.', '@')):
                        continue
                    info = entry.stat(follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode) and info.st_dev != device:
                        roots.append(os.path.join(volume, entry.name))
                    if len(roots) > 128:
                        raise ValueError('Demasiadas raíces descubiertas; indica roots explícitas')
        except OSError as exc:
            errors.append(dict(path=volume, errno=exc.errno, reason='root_discovery_failed'))
        finally:
            if descriptor is not None:
                os.close(descriptor)
    return sorted(set(roots), key=lambda path: (len(path), path)), errors


def open_directory(path):
    """Abre cada componente sin seguir enlaces, incluso si cambian al recorrer."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open('/', flags)
    try:
        for part in path.split('/'):
            if not part:
                continue
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def root_path(path):
    descriptor = open_directory(path)
    try:
        return os.fstat(descriptor).st_dev
    finally:
        os.close(descriptor)


def record(path, root, info):
    mode = info.st_mode
    kind = ('directory' if stat.S_ISDIR(mode) else 'symlink' if stat.S_ISLNK(mode)
            else 'file' if stat.S_ISREG(mode) else 'special')
    return dict(path=path, root=root, name=os.path.basename(path), kind=kind,
                size_bytes=info.st_size if kind == 'file' else None,
                mtime_ns=info.st_mtime_ns, filesystem_id=str(info.st_dev), inode=info.st_ino,
                media_kind='video' if kind == 'file' and os.path.splitext(path)[1].lower() in VIDEO else 'other')


def collect(request):
    started = time.monotonic()
    browse = request['operation'] == 'browse'
    directories = request['operation'] == 'directories'
    query = request.get('query', '').casefold()
    def matches(name):
        return name.casefold() == query if request.get('exact', False) else query in name.casefold()
    roots = request['roots']
    auto_discovered = request['operation'] in ('find', 'directories') and roots is None
    discovery_errors = []
    if auto_discovered:
        roots, discovery_errors = discover_data_roots(include_hidden=not request.get('skip_hidden', False))
        if not roots:
            discovery_errors.append(dict(reason='no_data_volumes_discovered',
                                         note='Indica roots observadas con nas.browse para este equipo'))
    items, errors, skipped = [], discovery_errors, dict(symlinks=0, special=0, mount_boundaries=0, hidden=0)
    skip_hidden = request.get('skip_hidden', False)
    extensions = request.get('extensions', [])
    entry_limit = MAX_FIND_ENTRIES if request['operation'] in ('find', 'directories') else MAX_ENTRIES
    visited = 0
    payload_size = 0
    stopped = None
    filesystems = {}
    for root in roots:
        try:
            root_device = root_path(root)
            filesystems[root] = str(root_device)
            if directories and matches(os.path.basename(root)):
                items.append(dict(path=root, root=root, name=os.path.basename(root), kind='directory', size_bytes=None))
        except (OSError, ValueError) as exc:
            errors.append(dict(path=root, errno=getattr(exc, 'errno', None), reason='invalid_or_unreadable_root'))
            continue
        pending = [root]
        while pending and stopped is None:
            directory = pending.pop()
            descriptor = None
            try:
                descriptor = open_directory(directory)
                if os.fstat(descriptor).st_dev != root_device:
                    skipped['mount_boundaries'] += 1
                    continue
                with os.scandir(descriptor) as entries:
                    for entry in entries:
                        if visited >= entry_limit or time.monotonic() - started >= MAX_SECONDS:
                            stopped = 'entry_limit' if visited >= entry_limit else 'time_limit'
                            break
                        visited += 1
                        if skip_hidden and entry.name.startswith(('.', '@')):
                            skipped['hidden'] += 1
                            continue
                        path = os.path.join(directory, entry.name)
                        try:
                            if (extensions and entry.is_file(follow_symlinks=False) and
                                    os.path.splitext(entry.name)[1].lower().lstrip('.') not in extensions):
                                continue
                            info = entry.stat(follow_symlinks=False)
                        except OSError as exc:
                            errors.append(dict(path=path, errno=exc.errno, reason='stat_failed'))
                            if len(errors) >= 100:
                                stopped = 'error_limit'
                                break
                            continue
                        item = record(path, root, info)
                        kind = item['kind']
                        if browse or (directories and kind == 'directory' and matches(entry.name)) or (not directories and kind == 'file'):
                            payload_size += len(json.dumps(item, ensure_ascii=True)) + 2
                            if payload_size > MAX_PAYLOAD:
                                stopped = 'payload_limit'
                                break
                            items.append(item)
                        if kind in ('symlink', 'special'):
                            skipped['symlinks' if kind == 'symlink' else 'special'] += 1
                        elif kind == 'directory' and not browse:
                            if info.st_dev == root_device:
                                pending.append(path)
                            else:
                                skipped['mount_boundaries'] += 1
            except OSError as exc:
                errors.append(dict(path=directory, errno=exc.errno, reason='directory_unreadable'))
                if len(errors) >= 100:
                    stopped = 'error_limit'
            finally:
                if descriptor is not None:
                    os.close(descriptor)
        if stopped:
            break
    result = dict(complete=not errors and stopped is None, errors=errors, roots=roots,
                  auto_discovered=auto_discovered, excludes_hidden=skip_hidden,
                  indexed_extensions=extensions,
                  stopped_reason=stopped, visited_entries=visited, skipped=skipped,
                  filesystems=filesystems, items=items)
    if browse:
        # Mostrar primero carpetas de usuario; las ocultas y las internas @ de
        # DSM siguen disponibles en las mismas páginas, sin excluir ninguna.
        items.sort(key=lambda item: (item['name'].startswith(('.', '@')),
                                     item['kind'] != 'directory', item['path']))
        offset, limit = request['offset'], request['limit']
        result['total_entries'] = len(items)
        result['items'] = items[offset:offset + limit]
        result['next_offset'] = offset + limit if offset + limit < len(items) else None
    return result


if __name__ == '__main__':
    try:
        result = collect(json.loads(sys.argv[1]))
    except Exception as exc:
        result = dict(complete=False, items=[], errors=[dict(reason=type(exc).__name__)])
    # El transporte interactivo reconoce prompts SSH. Los nombres de archivos
    # nunca deben poder parecer "password:" ni un prompt sudo.
    payload = json.dumps(result, ensure_ascii=True, separators=(',', ':')).encode('ascii')
    print(MARKER + base64.b64encode(payload).decode('ascii'))
