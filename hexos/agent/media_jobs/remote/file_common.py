"""Primitivas de archivos del host NAS: identidad, caminos y escrituras durables."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile


class Rejected(Exception):
    pass


class Cancelled(Exception):
    pass


def sync_directory(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save(path, value):
    fd, name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name+'.')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, allow_nan=False)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(name, str(path))
        sync_directory(path.parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def identity(info):
    return dict(size_bytes=info.st_size, mtime_ns=info.st_mtime_ns,
                inode=info.st_ino, filesystem_id=str(info.st_dev))


def directory(path):
    """Abre padres sin seguir enlaces, incluso durante sustituciones concurrentes."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise Rejected('Ruta absoluta sin .. requerida')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def opened(path):
    parent = directory(Path(path).parent)
    try:
        fd = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise Rejected('Se requiere archivo regular')
    return os.fdopen(fd, 'rb')


def inspect(path, expected=None):
    with opened(path) as stream:
        actual = identity(os.fstat(stream.fileno()))
    if expected is not None and actual != expected:
        raise Rejected('Archivo modificado desde la observación: '+str(path))
    return actual


def sha256(path, checkpoint):
    digest = hashlib.sha256()
    with opened(path) as stream:
        before = identity(os.fstat(stream.fileno()))
        while True:
            block = stream.read(4*1024*1024)
            if not block:
                break
            digest.update(block); checkpoint()
        if identity(os.fstat(stream.fileno())) != before:
            raise Rejected('Archivo modificado durante el hash')
    inspect(path, before)
    return digest.hexdigest()


def copy_checked(source, target, expected, checkpoint, reserve=64*1024*1024):
    """Temporal propio y exclusivo; no continuar sobre datos parciales desconocidos."""
    with opened(source) as incoming:
        before = os.fstat(incoming.fileno())
        if identity(before) != expected:
            raise Rejected('El origen cambió antes de copiar')
        parent = directory(target.parent)
        try:
            space = os.fstatvfs(parent)
            if space.f_bavail*space.f_frsize < expected['size_bytes']+reserve:
                raise OSError('Espacio libre insuficiente')
            fd = os.open(target.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            digest, copied = hashlib.sha256(), 0
            with os.fdopen(fd, 'wb') as outgoing:
                while True:
                    checkpoint(copied)
                    block = incoming.read(4*1024*1024)
                    if not block:
                        break
                    outgoing.write(block); digest.update(block); copied += len(block)
                outgoing.flush(); os.fsync(outgoing.fileno())
                if os.geteuid() == 0:
                    os.fchown(outgoing.fileno(), before.st_uid, before.st_gid)
                os.fchmod(outgoing.fileno(), stat.S_IMODE(before.st_mode) & 0o666)
            if identity(os.fstat(incoming.fileno())) != expected or copied != expected['size_bytes']:
                raise Rejected('El origen cambió durante la copia')
            inspect(source, expected)
            if sha256(target, checkpoint) != digest.hexdigest():
                raise Rejected('La copia no coincide con el origen')
            os.fsync(parent)
            return dict(sha256=digest.hexdigest(), identity=inspect(target))
        finally:
            os.close(parent)
