"""Sesión local de diagnóstico. Credencial solo en memoria; comandos acotados."""
from pathlib import Path
import re
import time

from . import hosts
from .work import now


DOCKER = ('if command -v docker >/dev/null 2>&1; then D=docker; '
          'elif [ -x /usr/local/bin/docker ]; then D=/usr/local/bin/docker; '
          'else echo "docker no encontrado" >&2; exit 127; fi; ')
CONTAINER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}')


def command(section, disk=None, container=None, action=None):
    if section == 'container':
        if action not in ('start', 'stop', 'restart'):
            raise ValueError('action debe ser start, stop o restart')
        if not isinstance(container, str) or not CONTAINER.fullmatch(container):
            raise ValueError('container debe ser un nombre visto en section=containers')
        # Comprobar el estado después: docker devuelve 0 al arrancar aunque el
        # contenedor se caiga acto seguido, que es lo habitual en uno mal configurado.
        return (DOCKER + '$D ' + action + ' -- ' + container + '; echo __HEXOS_STATE__; '
                'sleep 1; $D ps -a --filter name=' + container +
                ' --format "{{.Names}}\\t{{.State}}\\t{{.Status}}"')
    if section == 'containers' and container is not None:
        # Mirar un contenedor concreto sin tocarlo: comprobar no debe exigir una acción.
        if not isinstance(container, str) or not CONTAINER.fullmatch(container):
            raise ValueError('container debe ser un nombre de contenedor')
        return (DOCKER + '$D ps -a --filter name=' + container +
                ' --format "{{.Names}}\t{{.State}}\t{{.Status}}\t{{.Image}}"')
    commands = {
        'diagnosis': 'diagnosis',
        'system': 'date; uname -a; uptime; cat /etc.defaults/VERSION',
        'storage': 'cat /proc/mdstat; for d in /sys/block/sd* /sys/block/nvme*n*; do echo DEVICE=$(basename "$d"); readlink -f "$d/device"; done',
        # El recuento recorre el buffer entero: la cola de 65 líneas puede haber dejado fuera la tormenta.
        'kernel': "echo LINK_EVENT_TALLY; dmesg | grep -Ei 'hard resetting link|device unplugged|DevExch|PHYRdyChg"
                  "|COMRESET failed|slow to respond|limiting SATA link speed' | grep -oE 'ata[0-9]+' | sort | uniq -c;"
                  " echo LINK_EVENT_TALLY_END;"
                  " dmesg | grep -Ei 'ata[0-9]|sata|reset|I/O error|failed command|link (up|down)|sd[a-z]|nvme' | tail -n 65",
        'messages': "tail -n 2000 /var/log/messages | grep -Ei 'ata[0-9]|reset|I/O error|disconnect|reconnect' | tail -n 65",
        'containers': DOCKER + '$D ps -a --format "{{.Names}}\t{{.State}}\t{{.Status}}\t{{.Image}}"',
    }
    if section == 'smart':
        if not isinstance(disk,str) or not re.fullmatch(r'(sd[a-z]|nvme[0-9]+n[0-9]+)',disk):
            raise ValueError('Para SMART indica disk como sda, sdb o nvme0n1, obtenido de storage. No es el número de bahía.')
        return 'smartctl -i -H -A -l error -l selftest /dev/' + disk
    if section not in commands or disk is not None or container is not None or action is not None:
        raise ValueError('section: system, storage, kernel, messages, containers, smart o container. '
                         'disk solo con smart; action solo con section=container. '
                         'container vale en section=containers (mirar sin tocar) y en section=container (actuar).')
    return commands[section]


def read(workspace, section, disk=None, device=None, container=None, action=None):
    # SMART sin disco significa revisar los discos descubiertos, no pedir al usuario
    # que traduzca su dispositivo a un nombre del kernel.
    requested_section = section
    if section == 'smart' and disk is None:
        section = 'diagnosis'
    command(section, disk, container, action)
    device = device or hosts.only_device(workspace)
    if not hosts.credentials(workspace, device):
        # Resolver aquí permite enseñar en la ventana a qué máquina se da el acceso.
        try:
            located = hosts.resolve(workspace, device)
        except ValueError:
            located = None
        raise hosts.AccessNeeded(device, located)
    result = execute(workspace, device, section, disk, container, action)
    return present_result(result, section, requested_section)


# Velocidad a la que el kernel ha limitado el enlace, según el nibble SPD de SControl.
SPD_LIMIT = {1: '1.5 Gbps', 2: '3.0 Gbps', 3: '6.0 Gbps'}
LINK_EVENTS = [('unplugged', r'device unplugged'),
               ('phy_changes', r'SError:[^\n]*(?:PHYRdyChg|DevExch|10B8B)'),
               ('hard_resets', r'hard resetting link'),
               ('slow_to_respond', r'link is slow to respond'),
               ('comreset_failed', r'COMRESET failed'),
               ('speed_limited', r'limiting SATA link speed'),
               ('io_errors', r'I/O error|failed command'),
               ('disabled', r'disabling port|device disabled|failed to (?:recover|resume) link')]
ERROR_PATTERN = (r'SError|hard resetting link|slow to respond|link down|failed command|I/O error'
                 r'|connection status changed|device unplugged|COMRESET failed|limiting SATA link speed'
                 r'|disabling port|device disabled|exception Emask')


def link_report(kernel_output):
    """Estado por enlace ata: velocidad negociada, tope impuesto por el kernel y recuentos."""
    links = {}
    tally = re.search(r'LINK_EVENT_TALLY\n(.*?)LINK_EVENT_TALLY_END', kernel_output, re.S)
    totals = dict((match.group(2), int(match.group(1)))
                  for match in re.finditer(r'(?m)^\s*(\d+)\s+ata(\d+)\s*$', tally.group(1) if tally else ''))
    for link, total in totals.items():
        links.setdefault(link, dict(negotiated_speed=None, kernel_speed_limit=None,
                                    transfer_mode=None, events={}))['events_in_whole_buffer'] = total
    for line in kernel_output.splitlines():
        match = re.search(r'ata(\d+)(?:\.\d+)?:', line)
        if not match:
            continue
        entry = links.setdefault(match.group(1), dict(negotiated_speed=None, kernel_speed_limit=None,
                                                      transfer_mode=None, events={}))
        speed = re.search(r'SATA link up ([\d.]+) Gbps \(SStatus \w+ SControl ([0-9a-fA-F]+)\)', line)
        if speed:
            entry['negotiated_speed'] = speed.group(1) + ' Gbps'
            entry['kernel_speed_limit'] = SPD_LIMIT.get(int(speed.group(2), 16) >> 4 & 0xf)
        mode = re.search(r'configured for (UDMA/\d+|MWDMA\d+|PIO\d+)', line)
        if mode:
            entry['transfer_mode'] = mode.group(1)
        for name, pattern in LINK_EVENTS:
            if re.search(pattern, line, re.I):
                entry['events'][name] = entry['events'].get(name, 0) + 1
    return links


def smart_field(summary, label):
    match = re.search(label + r':\s*(.+)', summary)
    return match.group(1).strip() if match else None


def sata_speeds(summary):
    """Capacidad y velocidad actual declaradas por el propio disco, independientes de dmesg."""
    match = re.search(r'SATA Version is:[^\n]*?([\d.]+) Gb/s\s*\(current:\s*([\d.]+) Gb/s\)', summary)
    return (match.group(1) + ' Gb/s', match.group(2) + ' Gb/s') if match else (None, None)


def rank_disk_evidence(links, maps, records, attributes):
    """Ordena por evidencia ligada a un disco físico. El recuento RAID nunca entra aquí."""
    suspects = []
    for link, state in links.items():
        events = state['events']
        disk = maps.get(link)
        record = next((item for item in records if item['disk'] == disk), None)
        summary = record.get('summary', '') if record else ''
        capability, current = sata_speeds(summary)
        counters = next((dict(item['attributes']) for item in attributes if item['disk'] == disk), {})
        downshift = bool(state['kernel_speed_limit']) or (capability and current and capability != current)
        physical = events.get('unplugged', 0) + events.get('phy_changes', 0) + events.get('comreset_failed', 0)
        if not any(events.values()):
            continue
        surface = {name: counters[name] for name in
                   ('Reallocated_Sector_Ct', 'Current_Pending_Sector', 'Offline_Uncorrectable', 'Reported_Uncorrect')
                   if name in counters}
        crc = counters.get('UDMA_CRC_Error_Count')
        buffered = state.get('events_in_whole_buffer') or 0
        score = physical * 3 + sum(events.values()) + (4 if downshift else 0) + min(buffered, 20)
        suspects.append((score, dict(
            disk=disk, link='ata' + link,
            confidence='alta' if downshift and physical else 'media' if physical or downshift else 'baja',
            model=smart_field(summary, r'(?:Device Model|Model Number)'),
            serial=smart_field(summary, r'Serial Number'),
            negotiated_speed=state['negotiated_speed'], drive_supports=capability,
            drive_reports_current=current, transfer_mode=state['transfer_mode'],
            kernel_speed_limit=state['kernel_speed_limit'], events=events,
            events_in_whole_buffer=state.get('events_in_whole_buffer'),
            link_error_counter={'UDMA_CRC_Error_Count': crc} if crc is not None else {},
            surface_counters=surface)))
    suspects.sort(key=lambda item: -item[0])
    return [suspect for _, suspect in suspects]


def suspect_headline(suspect, links):
    """Frase ya redactada: el resumen debe nombrar el disco, no el recuento de arrays."""
    peers = [state['negotiated_speed'] for link, state in links.items()
             if 'ata' + link != suspect['link'] and state['negotiated_speed']]
    # Sin correspondencia ata/sd se nombra el enlace: llamar disco a un puerto sería inventar.
    text = ('La evidencia apunta al disco ' + suspect['disk'] + ' (' + suspect['link'] + ')' if suspect['disk']
            else 'La evidencia apunta al enlace ' + suspect['link'] + ', cuyo disco no consta en la lectura de storage')
    text += ', no a los arrays RAID: '
    marks = []
    if suspect['events'].get('unplugged'):
        marks.append('el kernel registra device unplugged')
    if suspect['events'].get('phy_changes'):
        marks.append('cambios de estado del PHY (PHYRdyChg/DevExch)')
    resets = suspect['events'].get('hard_resets')
    if resets:
        marks.append(str(resets) + (' reinicio del enlace' if resets == 1 else ' reinicios del enlace'))
    if suspect.get('events_in_whole_buffer'):
        marks.append(str(suspect['events_in_whole_buffer']) + ' eventos de enlace en todo el buffer del kernel')
    if suspect['kernel_speed_limit']:
        marks.append('el kernel limitó el enlace a ' + suspect['kernel_speed_limit'] +
                     (' y el disco quedó en ' + suspect['transfer_mode'] if suspect['transfer_mode'] else ''))
    elif suspect['drive_supports'] and suspect['drive_reports_current'] and \
            suspect['drive_supports'] != suspect['drive_reports_current']:
        marks.append('negocia ' + suspect['drive_reports_current'] + ' pese a admitir ' + suspect['drive_supports'])
    if peers and suspect['negotiated_speed'] and suspect['negotiated_speed'] not in peers:
        marks.append('los demás enlaces negocian ' + ', '.join(sorted(set(peers))))
    return text + '; '.join(marks) + '.'


BANNER = re.compile(r'^(?:\*\*|\S+@\S+\'s|Could not chdir|Connection to |\s*$|.*post-quantum.*'
                    r'|.*store now, decrypt later.*|.*openssh\.com/pq.*)', re.I)


# El estado se lee un segundo después de actuar, así que un arranque real sale en
# segundos. En minutos ya no: ese contenedor llevaba arriba de antes.
RECIEN = re.compile(r'^Up\s+(?:Less than a second|\d+\s+seconds?)\b', re.I)


def arranco_ahora(status):
    """¿El Status de docker demuestra que este contenedor acaba de arrancar?

    Sin esto, un `restart` sobre algo que ya llevaba dos semanas arriba se daba por
    hecho solo porque seguía `running`. La evidencia tiene que ser de la acción, no
    del estado que ya había.
    """
    return bool(status) and bool(RECIEN.match(status.strip()))


def container_rows(output):
    """Filas de docker ps, separando el ruido del banner SSH de la salida útil."""
    rows = []
    tail = output.split('__HEXOS_STATE__')[-1]
    for line in output.splitlines():
        line = line.replace('\r', '').rstrip()
        if BANNER.match(line):
            continue
        fields = line.split('\t')
        if len(fields) >= 3:
            rows.append(dict(name=fields[0].strip(), state=fields[1].strip(), status=fields[2].strip()))
    return rows, tail


def present_result(result, section, requested_section=None):
    if section == 'diagnosis' and 'smart' in result:
        # Presentar dos veces el mismo resultado es legítimo (replays sobre lo guardado):
        # el resumen ya retiró /proc/mdstat, así que los hechos previos sustituyen a la lectura.
        previous = result.get('facts') or {}
        for key in ('headline', 'primary_suspect', 'other_disks_with_link_events',
                    'diagnostic_findings', 'diagnostic_limits'):
            result.pop(key, None)
        layout = result['storage'].get('output', '')
        raid = []
        for match in re.finditer(r'(md\d+)\s*:[^\n]*\n\s*[^\n]*\[(\d+)/(\d+)\]\s*\[([U_]+)\]', layout):
            name, expected, present, flags = match.groups()
            header = re.search(r'(?m)^' + name + r'\s*:[^\n]*', layout)
            members = re.findall(r'\b((?:sd[a-z]|nvme\d+n\d+)p?\d+)\[\d+\]', header.group(0) if header else '')
            raid.append(dict(array=name, configured_members=int(expected), active_members=int(present),
                             all_configured_members_present=expected == present and '_' not in flags,
                             members=members))
        if not raid:
            raid = [dict(entry, members=entry.get('members') or []) for entry in previous.get('raid', [])]
        maps = {m.group(2): m.group(1) for m in re.finditer(r'DEVICE=(\w+)\s+/sys/[^\r\n]*/ata(\d+)/', layout)}
        if not maps:
            maps = {entry['link'][3:]: entry['disk'] for entry in previous.get('links_in_error_log', []) if entry.get('disk')}
        error_lines = [line for line in result['kernel']['output'].splitlines()
                       if re.search(ERROR_PATTERN, line, re.I)]
        links = sorted(set(re.findall(r'ata(\d+)(?:\.\d+)?:', '\n'.join(error_lines))))
        indicators = []
        for record in result['smart']:
            # Conservar columnas y valores, quitando el relleno tabular del terminal.
            kept=[];attributes=next((dict(item['attributes']) for item in result.get('facts',{}).get('smart_attributes',[]) if item['disk']==record['disk']), {});selftests=0
            for line in record['summary'].splitlines():
                fields=line.split()
                if fields and fields[0].isdigit() and len(fields)>=10:
                    if fields[0] in ('5','9','12','187','188','192','194','197','198','199'):
                        attributes[fields[1]]=' '.join(fields[9:])
                    if fields[0] in ('1','7','195'):
                        # Campos Seagate brutos empaquetados no son recuentos simples de fallos.
                        line=f'{fields[1]}: normalized={fields[3]}, threshold={fields[5]}, when_failed={fields[8]}; raw vendor-specific omitted'
                    else:
                        continue
                if re.match(r'\s*(ID#\s+ATTRIBUTE_NAME|Num\s+Test_Description|SMART Error Log Version'
                            r'|SMART Self-test log structure)', line):
                    continue
                if line.lstrip().startswith('#'):
                    selftests+=1
                    if selftests>2:continue
                kept.append(' '.join(line.split()))
            indicators.append(dict(disk=record['disk'], attributes=attributes, read_exit_code=record['exit_code']))
            record['summary'] = '\n'.join(kept)
        # El estado del enlace se lee de todas las líneas, no solo de las que son error:
        # la velocidad renegociada aparece en una línea de éxito y es la señal más específica.
        quality = link_report(result['kernel']['output'])
        for link, state in previous.get('link_state', {}).items():
            entry = quality.setdefault(link[3:], dict(state))
            for name in ('negotiated_speed', 'kernel_speed_limit', 'transfer_mode', 'events_in_whole_buffer'):
                entry[name] = entry.get(name) or state.get(name)
            entry['events'] = entry.get('events') or state.get('events', {})
        suspects = rank_disk_evidence(quality, maps, result['smart'], indicators)
        # El extracto conserva primero las líneas con señal; el corte por cola las perdía.
        lines = result['kernel']['output'].splitlines()
        signal = [line for line in lines if re.search(ERROR_PATTERN + r'|SATA link up|configured for', line, re.I)
                  and 'LINK_EVENT_TALLY' not in line]
        result['kernel']['output'] = '\n'.join((signal or lines)[-14:])
        result['kernel']['excerpt'] = len(lines) > 14
        result['kernel']['excerpt_note'] = ('Líneas con señal de enlace de la lectura filtrada; section=kernel permite ampliar. '
                                            'SMART resume atributos clave y dos pruebas previas; section=smart da detalle.')
        result.pop('facts', None)
        for entry in raid:
            # DSM crea md0/md1 con 12 ranuras en cualquier modelo: el hueco es el valor de fábrica.
            system = entry['array'] in ('md0', 'md1')
            entry['role'] = 'DSM_system_partition' if system else 'data_pool_or_cache'
            if system:
                entry['slot_count_is_DSM_default'] = True
        pools = [entry for entry in raid if entry['role'] != 'DSM_system_partition']
        complete = [entry['array'] for entry in pools if entry['all_configured_members_present']]
        incomplete = [entry['array'] for entry in pools if not entry['all_configured_members_present']]
        raid_summary = ('Pools de datos completos: ' + (', '.join(complete) or 'ninguno') +
                        '. Incompletos: ' + (', '.join(incomplete) or 'ninguno') +
                        '. md0/md1 son particiones de sistema DSM: sus 12 ranuras son el valor fijo de DSM, no 12 discos '
                        'físicos. Ningún recuento de miembros identifica un disco averiado ni es por sí solo la avería.')
        result = dict(facts=dict(links_in_error_log=[dict(link='ata' + link, disk=maps.get(link)) for link in links],
                   link_state={'ata' + link: state for link, state in sorted(quality.items())},
                   raid_summary=raid_summary, raid=raid, smart_attributes=indicators,
                   interpretation='[n/n] no es degradación. Los RAW de lectura/búsqueda Seagate no son sectores dañados. '
                   'SMART exit_code no nulo puede ser límite de smartctl, no fallo de SSH. '
                   'Para sectores: Reallocated_Sector_Ct, Current_Pending_Sector, Offline_Uncorrectable.',
                   smart_assessment_limit='PASSED no descarta fallos físicos, de alimentación o enlace; '
                   'sin lectura válida (health_assessment=unknown) la salud es desconocida, no buena.'),
                   **result)
        # La evidencia va dentro del sospechoso; repetirla como lista aparte llenaba el contexto.
        evidence = {link: [line for line in error_lines if re.search(r'ata' + link + r'(?:\.\d+)?:', line)][-3:]
                    for link in links}
        for record in result['smart']:
            summary = record.get('summary', '')
            match = re.search(r'SMART overall-health[^\n]*:\s*(PASSED|FAILED)', summary)
            record['health_assessment'] = match.group(1) if match else 'unknown'
        if raid:
            result['storage'].pop('output', None)
            result['storage']['layout_source'] = 'Recuentos extraídos de /proc/mdstat en facts.raid; section=storage conserva la salida completa.'
        limits = ['No se ha determinado la causa física ni si el error sigue ocurriendo ahora.',
                  'No atribuir una advertencia DSM a un array sin leer esa advertencia.']
        head = dict(diagnostic_limits=limits)
        for suspect in suspects:
            suspect['evidence'] = evidence.get(suspect['link'][3:], [])
            suspect['cause'] = 'undetermined'
        if suspects:
            first = suspects[0]
            crc = first['link_error_counter'].get('UDMA_CRC_Error_Count')
            # CRC cuenta errores en las líneas de datos; su ausencia junto a eventos del PHY
            # deja el contacto o la alimentación como hipótesis más viva que el cable de datos.
            discriminator = ('' if crc is None else
                             ' UDMA_CRC_Error_Count=0 pese a los eventos del PHY: el ruido en las líneas de datos queda '
                             'menos respaldado que un contacto o una alimentación intermitentes.' if crc.split()[0] == '0' else
                             ' UDMA_CRC_Error_Count=' + crc + ': hay errores en las líneas de datos, compatible con el cable o su conector.')
            first['reading'] = ('Fallo de enlace en este disco. Contadores de superficie: ' +
                                (', '.join(name + '=' + value for name, value in first['surface_counters'].items()) or 'no leídos') +
                                '.' + discriminator +
                                ' Compatible con cable, conector, alimentación, puerto/controladora o electrónica del disco; '
                                'no está demostrado cuál de ellos.')
            first['next_step'] = ('Identificar el disco por modelo y número de serie, no por bahía. '
                                  'Revisar cable y conector de alimentación de ese disco antes que sustituirlo.')
            head = dict(headline=suspect_headline(first, quality), primary_suspect=first,
                        other_disks_with_link_events=suspects[1:], **head)
            limits.append('primary_suspect concentra la evidencia; el recuento RAID no lo determina.')
        else:
            head = dict(headline='Sin eventos de enlace en la ventana de kernel leída. Esto no demuestra que no ocurran: '
                                 'el buffer puede haber rotado; section=messages amplía el histórico.', **head)
        result = dict(**head, **result)
    elif section in ('container', 'containers'):
        rows, tail = container_rows(result.get('output', ''))
        if section == 'containers':
            result = dict(containers=rows, total=len(rows),
                          note_state='State running/exited/created; Status es el texto de docker. '
                                     'Un contenedor created nunca llegó a arrancar.', **result)
            result.pop('output', None)
        else:
            wanted = result.get('container')
            state = next((row for row in rows if row['name'] == wanted), None)
            done = result.get('exit_code') == 0 and wanted in tail
            accion = result.get('action')
            # La intención se cumple por el estado resultante, no porque el comando devuelva 0.
            expected = 'running' if accion in ('start', 'restart') else 'exited'
            if result.get('timed_out') or not done and result.get('exit_code') is None:
                # Se agotó el tiempo: no se sabe si la acción llegó a ejecutarse. Eso no
                # es un fallo ni un éxito, y sobre todo no autoriza a repetirla.
                outcome = 'desconocido'
            elif not state or not done:
                outcome = 'sin_confirmar'
            elif state['state'] != expected and not (expected == 'exited' and state['state'] != 'running'):
                outcome = 'no_se_sostuvo'
            elif accion in ('start', 'restart') and not arranco_ahora(state.get('status')):
                # Ver «running» no demuestra que se haya arrancado ni reiniciado: uno que
                # ya llevaba dos semanas arriba se ve igual. La evidencia tiene que
                # corresponder a la acción, y aquí eso es un tiempo de vida recién puesto a cero.
                outcome = 'sin_confirmar'
            else:
                outcome = 'hecho'
            result = dict(
                outcome=outcome,
                container_state=state,
                headline=(wanted + ': ahora ' + state['state'] + ' (' + state['status'] + ')') if state
                         else 'No se pudo leer el estado de ' + str(wanted) + ' después de la acción',
                warning=None if not state or state['state'] == 'running' or result.get('action') == 'stop'
                        else 'El comando no falló pero el contenedor no está corriendo: arrancó y volvió a salir, '
                             'o no llegó a arrancar. Revisa su configuración o sus registros.',
                limit='Estado tomado un segundo después de la acción; puede cambiar luego.', **result)
            result.pop('output', None)
    elif section == 'storage':
        result=dict(scope='partial_storage_layout_only',
            missing_checks=['kernel_link_errors','SMART'],
            next_read=dict(section='diagnosis'),
            interpretation_limit='Esta lectura NO es un diagnóstico de salud. [12/1] indica miembros configurados/activos, no once discos físicos fallados ni gravedad demostrada. No establece reconstrucción ni la causa de una advertencia DSM.', **result)
    if requested_section and requested_section != section:
        result['requested_section']=requested_section
        result['effective_section']=section
    return result


def execute(workspace, device, section, disk=None, container=None, action=None):
    """Conecta al equipo guardado con ese nombre usando su credencial local."""
    remote = command(section, disk, container, action)
    if section == 'diagnosis':
        storage = execute(workspace, device, 'storage')
        kernel = execute(workspace, device, 'kernel')
        disks = re.findall(r'(?m)^DEVICE=(sd[a-z]|nvme[0-9]+n[0-9]+)\s*$', storage['output'])
        smart = []
        for name in dict.fromkeys(disks):
            result = execute(workspace, device, 'smart', name)
            lines = []
            for line in result['output'].splitlines():
                if re.search(r'Device Model|Model Number|Serial Number|Firmware Version|SATA Version|SMART overall|PASSED|FAILED|Error|error|Temperature|Critical Warning|Media|Self-test|#\s*[0-9]', line) or re.match(r'\s*(5|9|12|187|188|190|192|194|197|198|199)\s', line):
                    lines.append(line)
            smart.append(dict(disk=name, exit_code=result['exit_code'], timed_out=result['timed_out'],
                              summary='\n'.join(lines), truncated=result['truncated']))
        return dict(target=device, observed_at=now(), section=section,
                    storage=storage, kernel=kernel, smart=smart,
                    note='Lecturas correlacionadas automáticamente. Errores SMART o ausencia de datos no equivalen a salud. '
                         'section=smart da el detalle de un disco. No se ejecutan tests ni reparaciones.')
    located = hosts.resolve(workspace, device)
    account = hosts.credentials(workspace, device)
    if not account:
        raise ValueError('No hay credenciales guardadas para ' + repr(device) + '. Guárdalas con: '
                         'python3 -m hexos.agent.hosts --workspace ' + str(workspace) +
                         ' --device ' + device + ' --user USUARIO')
    password = account['password']
    # La clave de host queda fijada en el primer acceso y se verifica en los siguientes.
    known = str(Path(workspace).resolve() / (device.casefold().replace(' ', '_') + '_known_hosts'))
    quoted = "'" + remote.replace("'", "'\\''") + "'"
    # Un equipo puede tener dos caminos: su IP en la red y una dirección de fuera.
    # Si el primero no llega, se prueba el siguiente en vez de rendirse — antes
    # había que decirle a mano «prueba por la https», y eso no es iniciativa suya.
    rutas = [located] + list(located.get('alternatives') or [])
    intentos = []
    for indice, ruta in enumerate(rutas):
        puerto = ruta.get('port') or account['port']
        argv = ['-tt', '-o', 'StrictHostKeyChecking=accept-new', '-o', 'UserKnownHostsFile=' + known,
                '-o', 'ConnectTimeout=5', '-o', 'NumberOfPasswordPrompts=1',
                '-o', 'PubkeyAuthentication=no', '-o', 'ForwardAgent=no', '-o', 'ClearAllForwardings=yes',
                '-p', str(puerto), account['user'] + '@' + ruta['host'],
                "sudo -p '__HEXOS_SUDO__:' /bin/sh -c " + quoted]
        resultado = _ssh(argv, password, device, ruta, puerto, section, disk, container, action)
        intentos.append(dict(host=ruta['host'], port=puerto, pinned=ruta.get('pinned', False),
                             unreachable=resultado.pop('_unreachable')))
        # Solo se pasa a la siguiente si NO se llegó al equipo. Un error de dentro
        # es una respuesta suya, no una razón para llamar a otra puerta.
        if not intentos[-1]['unreachable'] or indice == len(rutas) - 1:
            resultado['routes_tried'] = intentos
            if len(intentos) > 1:
                resultado['note'] += (' Se intentó por ' + str(len(intentos)) + ' direcciones; '
                                      'valió ' + intentos[-1]['host'] + '.')
            return resultado
    raise ValueError('No se pudo alcanzar ' + repr(device) + ' por ninguna de sus direcciones')


def _ssh(argv, password, device, located, port, section, disk, container, action):
    """Una conexión y su lectura. `_unreachable` dice si ni siquiera se llegó."""
    import pexpect
    proc = pexpect.spawn('/usr/bin/ssh', argv, encoding='utf-8', codec_errors='replace', timeout=40)
    output = []; prompts = 0; timeout = False; deadline = time.monotonic() + 45
    try:
        while True:
            event = proc.expect([r"(?i)password:", r'__HEXOS_SUDO__:', pexpect.EOF, pexpect.TIMEOUT],
                                timeout=max(0, deadline - time.monotonic()))
            output.append(proc.before)
            if event in (0, 1):
                prompts += 1
                if prompts > 2: break
                # Nunca enviar una credencial si el terminal mantiene eco.
                if not proc.waitnoecho(timeout=2):
                    break
                proc.sendline(password)
            elif event == 2: break
            else:
                timeout = True; break
    finally:
        proc.close(force=True)
    text = ''.join(output).replace(password, '[credencial omitida]')
    # Ni se llegó al equipo: eso sí justifica probar otra dirección suya.
    inalcanzable = bool(re.search(
        r'No route to host|Connection refused|Connection timed out|Network is unreachable|'
        r'Name or service not known|Temporary failure in name resolution|'
        r'Could not resolve hostname|Operation timed out', text, re.I))
    # Credencial rechazada: no es una lectura fallida, es que falta el acceso. Se
    # pide otra vez por la ventana en vez de devolver el error como si fuera un
    # dato del equipo, que dejaba a la persona sin forma de corregir usuario,
    # contraseña o puerto.
    if re.search(r'Permission denied|Authentication failed|Too many authentication failures', text, re.I):
        raise hosts.AccessNeeded(device, located, reason='rejected')
    return dict(target=device, host=located['host'], port=port, observed_at=now(), section=section,
                disk=disk, container=container, action=action, _unreachable=inalcanzable,
                exit_code=proc.exitstatus, timed_out=timeout,
                output=text[-18000:], truncated=len(text) > 18000,
                note='Lectura real SSH con la credencial guardada. '
                     'Errores, permisos o salida vacía no prueban salud.')


if __name__ == '__main__':
    raise SystemExit('Las credenciales se guardan con: python3 -m hexos.agent.hosts '
                     '--workspace runtime/workspace --device NOMBRE --user USUARIO')
