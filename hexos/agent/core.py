"""El núcleo: lo que Helios guarda en su propio equipo.

Un solo recuento, que es el que responde en el chat y el que pinta la interfaz.
Si cada uno contara por su lado, un día dirían cosas distintas y no habría manera
de saber cuál miente.

Lo que NO es: aquí no hay archivos del NAS, ni fotos, ni vídeos. Helios todavía
no sabe listar un fichero de un servidor. Este recuento habla solo de lo suyo.
"""
from . import notes

SECCIONES = ('notas', 'informes', 'fichas', 'perfil', 'documentos')


def overview(store, profile=None):
    def cuantos(sql, *args):
        return store.db.execute(sql, args).fetchone()[0]

    vigentes = notes.listing(store, limit=200)
    secciones = [
        dict(key='notas', label='Notas', total=len(vigentes),
             pending=sum(1 for n in vigentes if n['state'] == 'pendiente'),
             tool='note.list'),
        dict(key='informes', label='Informes guardados',
             total=cuantos('SELECT COUNT(*) FROM agent_reports'), tool='report.list'),
        dict(key='fichas', label='Trabajos',
             total=cuantos('SELECT COUNT(*) FROM jobs'),
             pending=cuantos("SELECT COUNT(*) FROM jobs WHERE json_extract(body,'$.state')='pendiente'"),
             tool='work.list'),
        dict(key='documentos', label='Documentos',
             total=cuantos('SELECT COUNT(*) FROM documents'), tool='document.read'),
    ]
    perfil = dict(key='perfil', label='Perfil', tool='profile.remember')
    if profile is None:
        perfil.update(total=None, unknown='no hay perfil conectado en esta sesión')
    else:
        try:
            claves = profile.keys()
        except Exception as exc:
            perfil.update(total=None, unknown='no se pudo leer el perfil: ' + str(exc))
        else:
            perfil['total'] = len(claves)
            # Un hecho ilegible no es un hecho ausente: decirlo, no redondear.
            sin_leer = getattr(profile, 'unreadable', None)
            if sin_leer:
                perfil['unreadable'] = len(sin_leer)
    secciones.insert(3, perfil)

    favoritos = [dict(kind='nota', id=n['id'], title=n['title'], state=n['state'],
                      updated_at=n['updated_at'])
                 for n in vigentes if n['favorite']]
    return dict(sections=secciones, favorites=favoritos, total_favorites=len(favoritos),
                note='Lo que Helios guarda en su propio equipo. No incluye archivos del NAS: '
                     'Para archivos remotos usa las herramientas NAS.')


def dispatch(store, name, args, profile=None):
    if name == 'core.overview':
        return overview(store, profile)
    raise ValueError('operación de núcleo no soportada')
