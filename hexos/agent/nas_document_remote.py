"""Copia acotada de un archivo regular observado, sin seguir enlaces ni escribir."""
import base64
import json
import os
import stat
import sys

MARKER = '__HEXOS_FILES_V1__'
MAX_BYTES = 8 * 1024 * 1024


def identity(info):
    return dict(size_bytes=info.st_size, mtime_ns=info.st_mtime_ns,
                inode=info.st_ino, filesystem_id=str(info.st_dev))


def collect(request):
    descriptor = None
    try:
        parts = request['path'].split('/')
        descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        for part in parts[1:-1]:
            if not part or part in ('.', '..'):
                raise ValueError('invalid_path')
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        os.close(descriptor)
        descriptor = child
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('not_regular_file')
        if identity(before) != request['expected']:
            raise ValueError('file_changed_refresh_catalog')
        if before.st_size > MAX_BYTES:
            raise ValueError('document_size_limit_8_MiB')
        chunks, total = [], 0
        while True:
            chunk = os.read(descriptor, min(65536, MAX_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_BYTES:
                raise ValueError('document_size_limit_8_MiB')
        if identity(os.fstat(descriptor)) != identity(before) or total != before.st_size:
            raise ValueError('file_changed_during_read')
        return dict(content_base64=base64.b64encode(b''.join(chunks)).decode('ascii'), **identity(before))
    except (OSError, ValueError) as exc:
        return dict(error=str(exc) if isinstance(exc, ValueError) else 'file_read_failed',
                    errno=getattr(exc, 'errno', None))
    finally:
        if descriptor is not None:
            os.close(descriptor)


if __name__ == '__main__':
    result = collect(json.loads(sys.argv[1]))
    print(MARKER + base64.b64encode(json.dumps(result).encode()).decode())
