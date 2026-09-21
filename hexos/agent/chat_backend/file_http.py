"""Entrega de copias locales por identificador; nunca acepta rutas remotas o locales."""
from urllib.parse import urlparse, parse_qs, quote
from ..file_catalog import file_copies, file_access


def serve(handler, workspace):
    url = urlparse(handler.path)
    if url.path == '/api/files':
        handler.respond(200, file_copies.listing(workspace))
        return
    parts = url.path.split('/')
    if len(parts) not in (4, 5):
        handler.respond(404, {'error':'ruta inexistente'})
        return
    identifier = parts[3]
    try:
        metadata, content = file_copies.get(workspace, identifier)
        action = parts[4] if len(parts) == 5 else ''
        if action == 'download':
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/octet-stream')
            handler.send_header('Content-Length', str(len(content)))
            handler.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(metadata['name'], safe=''))
            handler.send_header('X-Content-Type-Options', 'nosniff')
            handler.send_header('Content-Security-Policy', "default-src 'none'; sandbox")
            handler.send_header('Cache-Control', 'no-store')
            handler.end_headers()
            handler.wfile.write(content)
        elif action == 'text':
            params = parse_qs(url.query)
            handler.respond(200, file_access.read(workspace, file_id=identifier,
                                                 offset=int(params.get('offset', ['0'])[0]), count=6000))
        elif not action:
            handler.respond(200, metadata)
        else:
            handler.respond(404, {'error':'ruta inexistente'})
    except (ValueError, TypeError) as exc:
        handler.respond(400, {'error':str(exc)})
