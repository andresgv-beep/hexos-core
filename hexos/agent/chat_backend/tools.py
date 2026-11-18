"""Despacho de herramientas y su único circuito normal de ejecución/traza."""
from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING
from uuid import uuid4
from .. import ajustes, catalog, descargas, devices, entorno, hosts, notes, core, pc_status, project_files, terminal_read, web, workflow, procedures, system_packages
from ..continuity import history_tool
from ..progress import announcement
from ..work import now
from .state import Environment, SessionState, TurnState
from .document_reading import document_lines
from .reading_budget import exhausted, READ_TOOLS
from .ledger import blocked_search, completed_call, completed_registration, failed_call
from .file_requests import validate_file_request

if TYPE_CHECKING:
    from .agent import Agent


def con_raices_conocidas(workspace, salida, args):
    """Si una ruta pedida no existe en ese equipo, devuelve las raíces que sí se conocen de él.

    Sin esto el modelo recibía solo «invalid_or_unreadable_root» y se quedaba con la
    ruta que traía de la conversación: el 08/10 buscó en synology 1 una carpeta que
    era del otro NAS. Las rutas salen de lo observado en ese equipo (nas.locations),
    nunca de una lista escrita en el código.
    """
    if not isinstance(salida, dict):
        return salida
    # nas.browse los trae arriba; nas.find, dentro de coverage aunque otra raíz sí responda.
    errores = (salida.get('errors') or []) + ((salida.get('coverage') or {}).get('errors') or [])
    malas = [e.get('path') for e in errores if e.get('reason') == 'invalid_or_unreadable_root']
    equipo = salida.get('device') or args.get('device')
    if not malas or not equipo:
        return salida
    from .. import nas_files
    import posixpath
    util = lambda ruta: '@' not in ruta and len(ruta.strip('/').split('/')) <= 4
    try:
        # Primero las que se parecen a lo que se pidió («multimedia» → «multimedia 1/Multimedia»),
        # luego las carpetas compartidas del equipo. Sin las internas del Synology (@eaDir…).
        parecidas = []
        for mala in malas:
            nombre = posixpath.basename((mala or '').rstrip('/'))
            if nombre:
                parecidas += [v['path'] for v in nas_files.locations(workspace, device=equipo, query=nombre,
                                                                     limit=50)['items']]
        compartidas = [v['path'] for v in nas_files.locations(workspace, device=equipo, limit=100)['items']
                       if len(v['path'].strip('/').split('/')) == 2]
    except Exception:  # noqa: BLE001 - una ayuda; si falla, el error original sigue ahí
        return salida
    raices = [r for r in dict.fromkeys(parecidas + compartidas) if util(r)][:20]
    if not raices:
        return salida
    return dict(salida, known_roots=raices,
                known_roots_note=('No existe o no se puede leer en ' + equipo + ': ' + ', '.join(malas) +
                                  '. Rutas observadas antes en ese mismo equipo: elige una de ellas.'))


class ToolDispatcher:
    def __init__(self, env: Environment, session: SessionState, memory, references, verification):
        self.env = env
        self.session = session
        self.memory = memory
        self.references = references
        self.verification = verification

    def dispatch(self, store, name, args, *, turn_id=None):
        catalog.validate(name, args)
        container_scope = None
        if name == 'nas.read':
            from .container_scope import resolve
            args, container_scope = resolve(args)
        if name == 'profile.recall':
            from .profile_context import recall
            return recall(self.env.profile, args['query'])
        if name.startswith('media.'):
            from .media_tools import dispatch
            return dispatch(self.env.workspace, name, args)
        if turn_id and name in ('nas.find', 'nas.search', 'nas.directories'):
            request = store.db.execute("SELECT text FROM conversation WHERE id=? AND role='user'",
                                       (turn_id,)).fetchone()
            if request:
                validate_file_request(request['text'], name, args)
        if name == 'profile.remember':
            return self.memory.remember_fact(store, args, turn_id)
        if name in ('nas.search', 'nas.locations', 'nas.directory_page', 'nas.file_read'):
            return self.env.dependencies.nas_files(self.env.workspace, operation=name.split('.')[1], **args)
        if name in ('nas.read', 'nas.container', 'device.connect', 'nas.browse', 'nas.index', 'nas.find',
                    'nas.directories', 'nas.shares', 'nas.file_open'):
            if not args.get('device') and name != 'nas.file_open':
                # El modelo omite a veces el equipo aunque la persona lo haya nombrado.
                # No se adivina: se lee su mensaje y solo vale si UNO de los guardados
                # aparece ahí. Con ninguno o con varios, que pregunte.
                nombrado = self.references.device_in_message(store, turn_id)
                if nombrado:
                    args = dict(args, device=nombrado)
                else:
                    # El único acceso guardado puede resolverse sin preguntar. Con
                    # ninguno o con varios, only_device devuelve un error explícito;
                    # nunca se inventa un destino llamado «synology».
                    args = dict(args, device=hosts.only_device(self.env.workspace))
            equipo = args.get('device')
            objetivo = args.get('container')
            if name == 'nas.container' and objetivo:
                # Una escritura anterior sobre este mismo destino se quedó sin saber
                # cómo acabó. Repetirla a ciegas puede duplicar el efecto: pudo
                # ejecutarse y solo perderse la respuesta. Se exige mirar antes.
                colgada = self.verification.pending_effect(store, equipo, objetivo)
                if colgada is not None:
                    raise ValueError(
                        'Hay una acción anterior sobre ' + repr(objetivo) + ' en ' + repr(equipo) +
                        ' (' + colgada['action'] + ', ' + colgada['ts'][:16] + ') cuyo efecto se '
                        'desconoce: se agotó el tiempo y no consta si llegó a ejecutarse. No se '
                        'repite a ciegas. Mira antes su estado con nas_read section=containers '
                        'container=' + objetivo + '; eso lo aclara sin tocar nada.')
            # Conectar es la lectura más barata que existe: si entra, hay acceso, y
            # si no, salta la misma petición de credencial. Sin esta puerta, un
            # «conéctate a servidor 1» no encontraba herramienta que le encajara y
            # el turno acababa en que solo sabía registrar equipos.
            extra = ({'section':'container'} if name == 'nas.container' else
                     {'section':'system'} if name == 'device.connect' else {})
            try:
                if name in ('nas.browse', 'nas.index', 'nas.find', 'nas.directories', 'nas.shares', 'nas.file_open'):
                    salida = self.env.dependencies.nas_files(self.env.workspace,
                                                             operation=name.split('.')[1], **args)
                else:
                    salida = self.env.dependencies.nas_read(self.env.workspace, **extra, **args)
                salida = con_raices_conocidas(self.env.workspace, salida, args)
                if container_scope is not None:
                    salida = dict(salida, scope=container_scope)
                    if not container_scope['covers_all_containers'] and not salida.get('containers'):
                        salida['scope_note'] = 'Sin coincidencias con este filtro; no demuestra ausencia de contenedores en el equipo.'
                if objetivo:
                    estado = (salida.get('container_state') or {}).get('status')
                    if name == 'nas.container' and salida.get('outcome') == 'desconocido':
                        # Queda anotado más allá del turno: el riesgo no caduca al responder.
                        store.db.execute('INSERT INTO pending_effects VALUES (?,?,?,?,?,?,?,?)',
                            (uuid4().hex, now(), equipo.casefold(), objetivo,
                             args.get('action') or '?', turn_id or '', None, None))
                        store.db.commit()
                    elif estado:
                        # Una lectura que sí ve el estado cierra lo que quedó en el aire.
                        self.verification.resolve_effect(store, equipo, objetivo, estado)
                return salida
            except hosts.AccessNeeded as needed:
                # La ventana de la interfaz recoge la credencial; no vuelve por el chat.
                # El puerto guardado viaja con la petición: sin verlo, quien corrige un
                # acceso rechazado vuelve a escribir el mismo y no entiende por qué falla.
                guardado = hosts.credentials(self.env.workspace, needed.device) or {}
                # Lo que estaba intentando hacer, para retomarlo al guardar el acceso
                # en vez de obligar a repetir la petición palabra por palabra.
                pedido = store.db.execute(
                    "SELECT text FROM conversation WHERE id=? AND role='user'",
                    (turn_id,)).fetchone() if turn_id else None
                # El puerto que ya se sabe, en este orden: el de la credencial guardada,
                # el que venía en la dirección al registrar el equipo, y si no el 22.
                sabido = guardado.get('port') or (needed.located or {}).get('port') or 22
                self.session.credential_request = dict(device=needed.device, requested_at=now(),
                                               reason=needed.reason, port=sabido,
                                               user=guardado.get('user'),
                                               pending_operation=dict(tool=name, arguments=dict(args)),
                                               pending_request=pedido['text'][:2000] if pedido else None,
                                               **{k: v for k, v in (needed.located or {}).items()
                                                  if k != 'port'})
                return dict(access_required=True, device=needed.device,
                            located=needed.located, reason=needed.reason,
                            asked_through='interface_credential_dialog',
                            instruction=('El equipo rechazó el acceso guardado. Dile que la ventana se '
                                         'ha vuelto a abrir para corregir usuario, contraseña o puerto, y que '
                                         'un puerto reenviado a otra máquina da este mismo error. '
                                         if needed.reason == 'rejected' else
                                         'La dirección de este equipo se cambió después de guardar su '
                                         'acceso, y el acceso guardado era para la anterior. No se ha '
                                         'conectado a ningún sitio. Dile que se ha abierto la ventana para '
                                         'confirmar usuario, contraseña y puerto de la dirección nueva. '
                                         if needed.reason == 'address_changed' else
                                         'Dile a la persona que Helios ha pedido el acceso y que aparece una '
                                         'ventana en la interfaz para rellenarlo. ') +
                                        'No pidas la contraseña por el chat ni la aceptes si la escribe: no '
                                        'quedaría guardada por esta vía. Esto no dice nada sobre la salud del equipo.')
        if name in ('network.local', 'device.refresh'):
            # La lectura vive en RAM. Permite identificar después «la que termina
            # en 129», pero reiniciar HexOS la elimina y ninguna IP observada entra
            # en el inventario por el mero hecho de haber pasado por la LAN.
            observacion = devices.snapshot()
            self.session.network_observation = observacion
            return dict(devices.annotate(store, observacion), persisted=False,
                        persistence_note=('Observación efímera. No se ha guardado ninguna IP; '
                                          'device.identify persiste solo el equipo elegido.'))
        if name.startswith('device.'):
            return devices.dispatch(store, name, args, turn_id,
                                    observation=self.session.network_observation)
        if name == 'core.overview':
            return core.dispatch(store, name, args, self.env.profile)
        if name.startswith('note.'):
            return notes.dispatch(store, name, args, turn_id)
        if name.startswith('history.'):
            return history_tool(store, name, args)
        if name == 'web.search':
            opciones = dict(limit=args.get('limit', 5))
            if args.get('recency'):
                opciones['recency'] = args['recency']
            # La clave la pone la persona en Ajustes; sin ella se busca como siempre.
            buscador = ajustes.buscador(self.env.workspace)
            if buscador:
                opciones['proveedor'] = buscador
            return self.env.dependencies.web_search(args['query'], **opciones)
        if name == 'web.read':
            return self.env.dependencies.web_read(args['url'])
        if name == 'file.download':
            # Solo propone: baja los ficheros la aprobación de la persona (/api/download).
            # Varias llamadas seguidas van a la misma tarjeta. El 16/11 iban de una en una y, a
            # «bájame los dos», el segundo se quedaba sin proponer hasta que se pedía otra vez.
            repetida = dict(status='pending_approval',
                            note='Este fichero ya estaba en la tarjeta y sigue sin decidir: la persona no lo ha '
                                 'aprobado ni rechazado todavía en la pantalla. No está descargado.')
            llena = dict(status='waiting_previous_plan', planned=False,
                         note=f'No se ha propuesto esta descarga: en una tarjeta caben {descargas.MAX_LOTE} '
                              'ficheros y ya están. No lo intentes otra vez en este turno. Dile a la persona '
                              'que decida esa tarjeta primero y que después propondrás el resto.')
            pendiente = self.session.download_request
            ya = descargas.mismo(pendiente, args['url'])
            if ya:
                return dict(repetida, summary=ya['summary'])
            if pendiente and len(pendiente['items']) >= descargas.MAX_LOTE:
                # Como resultado y no como error: no hay nada que corregir, solo esperar.
                return dict(llena, pending=pendiente['summary'])
            # Asomarse a la dirección sale a la red y tarda: fuera del cerrojo. La tarjeta se
            # vuelve a leer dentro, porque la persona puede haberla decidido mientras tanto.
            fichero = descargas.mirar(args['url'], args.get('name'))
            with self.session.cards_lock:
                pendiente = self.session.download_request
                ya = descargas.mismo(pendiente, fichero['url'])
                if ya:
                    return dict(repetida, summary=ya['summary'])
                if pendiente and len(pendiente['items']) >= descargas.MAX_LOTE:
                    return dict(llena, pending=pendiente['summary'])
                plan = self.session.download_request = descargas.sumar(pendiente, fichero)
            cuantos = len(plan['items'])
            tarjeta = ('A la persona le ha aparecido una tarjeta en la pantalla con el nombre, el origen y el tamaño'
                       if cuantos == 1 else f'Se ha sumado a la tarjeta que ya tenía en la pantalla, que lleva {cuantos} '
                                            'ficheros y se aprueba entera')
            return dict(summary=fichero['summary'], name=fichero['name'], kind=fichero['kind'],
                        size=descargas.tamano(fichero['bytes']), source=fichero['host'], folder=plan['folder'],
                        in_card=cuantos, status='pending_approval',
                        note='Pendiente: NO se ha descargado nada. ' + tarjeta + '; la aprueba o la cancela ahí, '
                             'no en el chat. Si la persona pidió más ficheros, llama ahora a file_download con el '
                             'siguiente: van a la misma tarjeta. Cuando estén todos, dile en una frase qué has '
                             'propuesto bajar y que lo apruebe en la tarjeta. Cuando lo haga te llegará una nota '
                             '«La persona aprobó en la interfaz…» con el resultado.')
        if name == 'file.list':
            return descargas.listado(store)
        if name == 'document.create':
            from .. import documentos
            # Tres intentos fallidos en un turno y se para: el 18/11 el Gemma 4 26B lo reintentó
            # once veces seguidas, cada vez un poco peor.
            if turn_id:
                fallidos = sum(1 for (cuerpo,) in store.db.execute(
                    "SELECT body FROM tool_events WHERE turn_id=? AND body LIKE '%document.create%'", (turn_id,))
                    if json.loads(cuerpo).get('failed'))
                if fallidos >= 3:
                    return dict(status='stopped', error='Ya van tres intentos sin poder crear el documento en este '
                                'turno. No lo intentes otra vez: dile a la persona en una frase qué fallaba según '
                                'el último error y pregúntale si lo reintentas.')
            # El gráfico, del argumento o de lo que la persona ha pedido en sus últimos mensajes: el
            # modelo se olvidaba de pedirlo y lo sustituía por instrucciones o macros inventadas.
            # El deducido nunca impide crear: solo se pone si hay una tabla que se pueda dibujar.
            grafico = args.get('chart')
            if not grafico and args.get('format', '').lower() in ('xlsx', 'excel', 'pdf'):
                pedidos = [fila[0] for fila in store.db.execute(
                    "SELECT text FROM esta_ventana WHERE role='user' ORDER BY rowid DESC LIMIT 3")]
                pedido = documentos.grafico_pedido(pedidos)
                grafico = pedido if pedido and documentos.dibujable(args['content']) else None
            hecho = documentos.crear(store, args['format'], args['name'], args['content'], grafico=grafico)
            return dict(hecho, status='created',
                        note='Hecho y comprobado: a la persona le ha aparecido en el chat una tarjeta con «Ver» y '
                             '«Descargar», y el fichero queda también en su ventana de Descargas. contents dice lo que '
                             'hay DE VERDAD en el fichero: hojas, filas, fórmulas con su resultado y gráficos. Cuéntale '
                             'solo eso, en dos o tres frases y con esos números; no menciones nada que no esté ahí. Si '
                             'falta algo que querías poner, vuelve a crearlo entero. No le pegues el contenido. Lo '
                             f'escrito queda como documento {hecho["document"]}.')
        if name == 'terminal.read':
            return terminal_read.read(args['command'], args.get('filter'), path=args.get('path'))
        if name == 'system.status':
            return pc_status.estado()
        if name == 'system.toolchain':
            return entorno.reconocer()
        if name == 'project.write':
            # Solo propone: escribe la aprobación de la persona (/api/project/change). Los
            # cambios se acumulan en una tarjeta y se aprueban juntos.
            pendiente = self.session.project_request
            cambio = project_files.proponer(store, args['path'], args.get('content'), args.get('old'), args.get('new'),
                                            pendiente=pendiente)
            if not project_files.esta_propuesto(pendiente, cambio):
                self.session.project_request = pendiente = project_files.tarjeta_con(pendiente, cambio)
            nota = ('Pendiente: NO se ha escrito nada. A la persona le aparece una tarjeta en la pantalla '
                    'con todos los ficheros propuestos y las líneas que cambian; los aprueba o cancela '
                    'juntos ahí, no en el chat. Si el encargo tiene más ficheros, proponlos ahora en este '
                    'mismo turno. Al acabar dile en una frase qué has propuesto y que lo apruebe en la '
                    'tarjeta. Cuando lo haga te llegará una nota «La persona aprobó en la interfaz…».')
            if cambio.get('whole_file_for_partial'):
                nota += (' Para la próxima: has mandado el fichero entero para cambiar %d líneas; con old y new '
                         'solo mandas el trozo que cambia.' % (cambio['added'] + cambio['removed']))
            return dict(path=cambio['path'], kind=cambio['kind'], added=cambio['added'], removed=cambio['removed'],
                        status='pending_approval', pending_files=[c['path'] for c in pendiente['changes']], note=nota)
        if name.startswith('project.'):
            return project_files.dispatch(store, name, args)
        if name == 'system.package_plan':
            # Solo planifica: la ejecución la dispara la aprobación de la persona (/api/system).
            pendiente = self.session.system_request
            if system_packages.mismo_plan(pendiente, args['action'], args['package'], args.get('manager')):
                # Pedir otra vez lo que ya espera no hace un plan nuevo: cambiaría el de la
                # tarjeta que la persona tiene delante por otro idéntico.
                return dict({k: v for k, v in pendiente.items() if k not in ('plan_id', 'created')}, status='pending_approval',
                            note='Este plan ya estaba pendiente y sigue sin decidir: la persona no lo ha '
                                 'aprobado ni rechazado todavía en la tarjeta de pantalla. No está hecho.')
            if pendiente:
                # Solo hay una tarjeta. El 13/11, a «instala lo que falte», el E4B planificó
                # pip y después venv: el segundo pisó al primero y él dio los dos por pendientes.
                # Como resultado y no como error: un error pone al modelo a reintentar la misma
                # llamada, y no hay nada que corregir, solo esperar.
                return dict(status='waiting_previous_plan', planned=False, pending=pendiente['summary'],
                            requested=args['package'],
                            note='No se ha planificado ' + args['package'] + ': van de uno en uno y «' +
                                 pendiente['summary'] + '» sigue esperando en la tarjeta. No lo intentes otra '
                                 'vez en este turno. Dile a la persona que decida ese primero y que después '
                                 'planificarás ' + args['package'] + '.')
            plan = system_packages.plan(args['action'], args['package'], args.get('manager'))
            self.session.system_request = plan
            # Sin plan_id: el 03/11 el modelo lo llevó a media.start, que también recibe un
            # plan_id, e intentó ejecutar él mismo un plan que solo aprueba la persona.
            return dict({k: v for k, v in plan.items() if k not in ('plan_id', 'created')},
                        status='pending_approval',
                        note=('Pendiente: la persona lo aprueba o lo cancela en la tarjeta que le ha aparecido '
                              'en la pantalla, no en el chat. No hay herramienta para ejecutarlo: no lo intentes '
                              'con ninguna otra (media.start es solo para vídeos). Dile que lo apruebe en la '
                              'tarjeta. Cuando lo haga, te llegará una nota «La persona aprobó en la interfaz…» '
                              'con el resultado ya comprobado.'))
        if name.startswith('procedure.') or name in ('report.save', 'result.get'):
            return workflow.dispatch(store, name, args, turn_id)
        if name.startswith(('procedure.', 'report.', 'task.')):
            return procedures.dispatch(store, name, args, turn_id=turn_id)
        if name in ('work.list', 'work.get'):
            if 'op' in args:
                raise ValueError('campo op no permitido')
            return store.dispatch(dict(args, op=name.split('.')[1]), actor='model')
        row = store.db.execute('SELECT content FROM documents WHERE id=?', (args.get('id'),)).fetchone()
        if row is None:
            raise ValueError('documento inexistente')
        lines = document_lines(row['content'])
        if name == 'document.search':
            query_text = args.get('query')
            if not isinstance(query_text, str) or not query_text:
                raise ValueError('consulta vacía')
            hits = []
            for i, line in enumerate(lines, 1):
                found = line.casefold().find(query_text.casefold())
                if found >= 0:
                    hits.append({'line': i, 'text': line[max(0, found - 120):found + 180]})
            return dict(matches=hits[:20], total_matches=len(hits), excerpts=True)
        start, count = args.get('start', 1), args.get('count', 40)
        if type(start) is not int or start < 1 or type(count) is not int or not 1 <= count <= 80:
            raise ValueError('rango inválido; count debe estar entre 1 y 80')
        selected = []
        used = 0
        for i in range(start - 1, min(start - 1 + count, len(lines))):
            line = lines[i]
            if used + len(line) > 6000:
                break
            selected.append({'line': i + 1, 'text': line})
            used += len(line)
        return dict(lines=selected, total_lines=len(lines),
                    next_line=start + len(selected), limited=len(selected) < count)


class ToolExecutor:
    def __init__(self, agent: Agent):
        self.agent = agent

    def execute(self, store, turn: TurnState, output: dict) -> None:
        """Validar → anunciar → ejecutar → verificar → registrar → devolver al modelo."""
        if set(output) != {'tool', 'arguments'}:
            raise ValueError('Llamada de herramienta inválida')
        self.agent.state = 'tool'
        # Vía de escape de los grupos: si llama a una herramienta de un grupo que ya no
        # se declara —pasa, porque el historial reinyecta llamadas viejas— su grupo
        # vuelve a estar vivo. Ofrecer no es autorizar: la validación es la de siempre.
        grupos = getattr(self.agent, 'grupos', None)
        if grupos is not None:
            grupos.usada(output['tool'])
        effect = catalog.TOOLS.get(output['tool'], {}).get('effect', 'read')
        try:
            catalog.validate(output['tool'], output['arguments'])
        except (ValueError, TypeError):
            # El circuito normal de abajo registra el error y se lo devuelve al
            # modelo. Aquí solo interesa saber si una llamada VÁLIDA ya se hizo.
            completed = None
        else:
            completed = (completed_call(turn, output['tool'], output['arguments']) or
                         completed_registration(turn, output['tool'], output['arguments']))
        if completed is not None:
            # El modelo puede intentar repetir una llamada después de perder el KV.
            # Se le devuelve el resultado registrado, pero no se toca el mundo ni
            # se añade una segunda operación ficticia a la traza.
            turn.checkpoint_reuses += 1
            self.agent.active_tools = [*self.agent.active_tools, dict(
                tool=output['tool'], status='done', effect=effect, seconds=0.0,
                verification=completed.get('verification'), reused_checkpoint=True)]
            reused = completed.get('result')
            if completed.get('tool') != output['tool']:
                reused = dict(reused, already_completed=True,
                              note='El equipo ya quedó registrado por device_remote; no hace '
                                   'falta identificarlo como vecino local.')
            if hasattr(self.agent.runtime, 'tool_result'):
                self.agent.runtime.tool_result(reused)
                turn.messages = []
            else:
                turn.messages = [dict(role='user', content=
                    'RESULTADO YA OBTENIDO EN ESTE TURNO (no se ejecutó otra vez):\n' +
                    json.dumps(reused, ensure_ascii=False))]
            self.agent.state = 'thinking'
            return
        if exhausted(turn, output["tool"]):
            raise RuntimeError("Se alcanzó el presupuesto de herramientas; no se ejecutó la siguiente solicitud")
        if output["tool"] in READ_TOOLS and turn.reading_started is None:
            turn.reading_started = time.monotonic()
        activity = dict(tool=output['tool'], status='running', effect=effect, seconds=None)
        self.agent.active_tools = [*self.agent.active_tools, activity]
        started = time.monotonic()
        try:
            catalog.validate(output['tool'], output['arguments'])
            # Solo web.read: la negativa de una web no cambia en segundos. Otras
            # lecturas sí pueden dar otro resultado con los mismos argumentos
            # (media.prepare cuando termina un escaneo), y eso tiene sus pruebas.
            anterior = (failed_call(turn, output['tool'], output['arguments'])
                        if output['tool'] == 'web.read' else None)
            if anterior is not None:
                raise ValueError('Esta misma llamada ya falló en este turno: ' +
                                 str((anterior.get('result') or {}).get('error')) +
                                 '. No se ha repetido. Cambia de fuente o de argumentos, '
                                 'o explica el bloqueo con lo que ya tienes.')
            bloqueada = (blocked_search(turn, web.SIN_REINTENTO)
                         if output['tool'] == 'web.search' else None)
            if bloqueada is not None:
                raise ValueError('La búsqueda web ya falló en este turno y otra consulta no lo arregla: ' +
                                 str(bloqueada['result']['error']) +
                                 '. No se ha buscado otra vez. Dile a la persona la causa tal cual y '
                                 'contesta con lo que ya sabes, sin presentar nada como encontrado.')
            # Un aviso por cada llamada, no solo por la primera: en un turno
            # con cuatro herramientas se veía la primera y las otras tres
            # pasaban mudas, así que el recorrido era invisible.
            preamble=getattr(self.agent.runtime,'last_preamble',None)
            primera = not self.agent.progress['messages']
            # La inferencia de respaldo solo en la primera. Pedir una
            # generación entera en cada paso para redactar «voy a mirarlo»
            # cuesta más que el paso mismo; si el modelo no dice nada por su
            # cuenta, la herramienta que corre ya se ve en la traza.
            if turn.listing_followup and primera:
                preamble = 'Recupero todas las páginas del listado anterior, conservando la carpeta y la búsqueda.'
            if not preamble and primera and hasattr(self.agent.runtime,'announce'):
                preamble=self.agent.runtime.announce(output['tool'],output['arguments'],turn.text)
                generation=getattr(self.agent.runtime,'last_announcement_generation',None)
                if generation is not None:
                    store.db.execute('INSERT INTO generation_events(turn_id,ts,body) VALUES (?,?,?)',
                        (turn.uid,now(),json.dumps(generation,ensure_ascii=False)))
            if preamble or primera:
                event=dict(id=uuid4().hex, turn_id=turn.uid, ts=now(), text=announcement(preamble))
                store.db.execute('INSERT INTO progress_events VALUES (?,?,?,?)',
                    (event['id'],turn.uid,event['ts'],event['text']))
                store.db.commit()
                # Se añade, no se reemplaza: el estado final no borra los avances.
                self.agent.progress={'turn_id':turn.uid,
                               'messages':[*self.agent.progress['messages'], event]}
            self.agent.check_cancelled()
            result = self.agent.tool(store, output['tool'], output['arguments'], turn_id=turn.uid)
        except (ValueError, TypeError) as exc:
            result = {'error': str(exc)}
        if output['tool'] == 'terminal.read' and 'error' not in result:
            ordenes = [s['arguments']['command'] for s in turn.trace
                       if s.get('tool') == 'terminal.read' and not s.get('failed')]
            pendientes = terminal_read.falta_tras([*ordenes, output['arguments']['command']], result)
            if pendientes:
                result['falta_por_mirar'] = pendientes
        # La traza dice qué hizo cada llamada, cuánto tardó y si escribió algo:
        # una interfaz debe poder distinguir una lectura de un cambio real.
        from .document_reading import enrich
        result = enrich(store, output['tool'], result)
        comprobacion, evidencia = self.agent.verify(store, output['tool'], output['arguments'], result)
        activity.update(status='failed' if isinstance(result, dict) and result.get('error') else 'done',
                        verification=comprobacion,
                        seconds=round(time.monotonic() - started, 3))
        turn.trace.append(dict(tool=output['tool'], arguments=output['arguments'],
                          effect=effect, changes_state=effect != 'read',
                          # «Se ejecutó» y «logró lo que pretendía» son cosas
                          # distintas, y hasta ahora se decían con el mismo campo.
                          verification=comprobacion, evidence=evidencia,
                          ts=now(), seconds=round(time.monotonic() - started, 3),
                          failed=bool(result.get('error')) if isinstance(result, dict) else False,
                          delivered_to_model=False,
                          result=result))
        event_row = store.db.execute('INSERT INTO tool_events(turn_id,ts,body) VALUES (?,?,?)',
            (turn.uid, now(), json.dumps(turn.trace[-1], ensure_ascii=False)))
        store.db.commit()
        if hasattr(self.agent.runtime, 'tool_result'):
            self.agent.runtime.tool_result(result)
            turn.messages = []
        else:
            turn.messages = [dict(role='user', content='RESULTADO DE HERRAMIENTA (datos):\n' +
                json.dumps(result, ensure_ascii=False))]
        turn.trace[-1]['delivered_to_model'] = True
        store.db.execute('UPDATE tool_events SET body=? WHERE rowid=?',
                         (json.dumps(turn.trace[-1], ensure_ascii=False), event_row.lastrowid))
        store.db.commit()
        self.agent.state = 'thinking'
