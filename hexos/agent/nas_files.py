"""Compatibilidad de las herramientas nas.*; composición, sin reglas de negocio.

Los nuevos consumidores pueden inyectar FileCatalog(reader, store) directamente.
Se mantienen las firmas, el archivo SQLite y las excepciones públicas existentes.
"""
from . import hosts, nas_session  # Compatibilidad con integraciones existentes.
from .file_catalog.ssh import observe, remote_command
from .file_catalog.service import FileCatalog
from .file_catalog.directories import DirectoryCatalog
from .file_catalog import file_access

from .file_catalog.sqlite_repository import SQLiteCatalog, database, remember_directories, publish_snapshot
from .file_catalog.validation import (integer, path_argument, roots_argument, extensions_argument,
                                      filters_argument, parents_within_root, scan_coverage)
from .file_catalog.presentation import bounded_page, PAGE_CHARS


def file_open(workspace, **kwargs):
    return file_access.open_file(workspace, lambda device, request: observe(workspace, device, request), **kwargs)


def file_read(workspace, **kwargs):
    return file_access.read(workspace, **kwargs)


def service(workspace):
    return FileCatalog(lambda device, request: observe(workspace, device, request), SQLiteCatalog(workspace))


def directories(workspace, **kwargs):
    return DirectoryCatalog(lambda device, request: observe(workspace, device, request),
                            SQLiteCatalog(workspace)).directories(**kwargs)


def shares(workspace, **kwargs):
    return DirectoryCatalog(lambda device, request: observe(workspace, device, request),
                            SQLiteCatalog(workspace)).shares(**kwargs)


def directory_page(workspace, **kwargs):
    return DirectoryCatalog(None, SQLiteCatalog(workspace)).page(**kwargs)


def browse(workspace, *, device=None, path='/', offset=0, limit=30):
    return service(workspace).browse(device=device, path=path, offset=offset, limit=limit)

def index(workspace, *, roots, device=None):
    return service(workspace).index(roots=roots, device=device)

def find(workspace, *, device=None, roots=None, extensions=None, min_bytes=0,
         max_bytes=None, query=None, limit=20, include_hidden=False):
    return service(workspace).find(
        device=device, roots=roots, extensions=extensions, min_bytes=min_bytes,
        max_bytes=max_bytes, query=query, limit=limit, include_hidden=include_hidden)

def search(workspace, *, scan_id, min_bytes=0, max_bytes=None, query=None,
           root=None, kind='all', offset=0, limit=30, extensions=None):
    return service(workspace).search(
        scan_id=scan_id, min_bytes=min_bytes, max_bytes=max_bytes, query=query,
        root=root, kind=kind, offset=offset, limit=limit, extensions=extensions)

def locations(workspace, *, device=None, query=None, limit=20, offset=0):
    if device:
        device = hosts.match(workspace, device) or device
    return service(workspace).locations(device=device, query=query, limit=limit, offset=offset)
