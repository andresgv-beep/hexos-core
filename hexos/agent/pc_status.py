"""Cómo va este PC ahora mismo, en una lectura.

«¿Qué consume más?», «¿por qué va lento?», «¿cuánta memoria le queda a la gráfica?» no
se contestan con una orden: hacen falta procesos, memoria, gráfica y discos a la vez, y
un modelo pequeño que tiene que encadenarlas anuncia la segunda y no la lanza. Esta
lectura lo trae todo junto y ya resumido.

Usa psutil y no órdenes de Linux a propósito: la misma lectura vale en Windows.
"""
import csv
import io
import platform
import shutil
import socket
import subprocess
import time

try:
    import psutil
except ImportError:                      # se dice al usarla, no al importar el agente
    psutil = None

MAS = 5                                  # procesos que se nombran en cada lista
MUESTRA = 0.5                            # segundos entre las dos medidas de CPU
SIN_DISCO = {'squashfs', 'tmpfs', 'devtmpfs', 'overlay', 'efivarfs', 'vfat', 'iso9660', 'fuse.portal'}
GPU_CAMPOS = 'name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,uuid'
SEGUNDOS = 5


def tamano(numero):
    """Bytes en la unidad que se lee de un vistazo: «6,2 GB», «540 MB»."""
    for unidad, paso in (('TB', 1 << 40), ('GB', 1 << 30), ('MB', 1 << 20)):
        if numero >= paso:
            valor = numero / paso
            return (('%.1f' % valor).replace('.', ',') if valor < 100 else '%d' % valor) + ' ' + unidad
    return '%d KB' % (numero >> 10)


def duracion(segundos):
    dias, resto = divmod(int(segundos), 86400)
    horas, resto = divmod(resto, 3600)
    if dias:
        return '%d d %d h' % (dias, horas)
    return '%d h %d min' % (horas, resto // 60)


def programa(ruta):
    """Nombre de un ejecutable venga como venga: ruta de Linux o de Windows bajo Wine."""
    return ruta.replace('\\', '/').rstrip('/').rsplit('/', 1)[-1] or ruta


def nvidia(campos, consulta='--query-gpu'):
    """Filas de nvidia-smi. Lista vacía si no hay gráfica NVIDIA o no responde."""
    if not shutil.which('nvidia-smi'):
        return []
    try:
        salida = subprocess.run(['nvidia-smi', consulta + '=' + campos, '--format=csv,noheader,nounits'],
                                capture_output=True, text=True, timeout=SEGUNDOS, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [[c.strip() for c in fila] for fila in csv.reader(io.StringIO(salida)) if fila]


def graficas(consultar=nvidia):
    """Cada gráfica con su memoria y quién la ocupa, de mayor a menor."""
    filas = consultar(GPU_CAMPOS)
    if not filas:
        return []
    # Cada proceso con la gráfica en la que está. Con dos tarjetas no se decía quién
    # ocupaba cada una: el 13/11 el 26B vio la memoria llena, no supo que era su propio
    # motor y mezcló los datos de las dos.
    ocupan = {}
    for fila in consultar('gpu_uuid,name,used_memory', '--query-compute-apps'):
        if len(fila) == 3 and fila[2].isdigit():
            ocupan.setdefault(fila[0], []).append((int(fila[2]), programa(fila[1])))
    vistas = []
    for fila in filas:
        if len(fila) != 7 or not (fila[2].isdigit() and fila[3].isdigit()):
            continue
        usada, total = int(fila[2]), int(fila[3])
        una = dict(nombre=fila[0], memoria='%d de %d MiB' % (usada, total), memoria_libre='%d MiB' % (total - usada),
                   memoria_usada_mib=usada, memoria_total_mib=total)
        if fila[1].isdigit():
            una['uso'] = fila[1] + ' %'
        if fila[4].isdigit():
            una['temperatura'] = fila[4] + ' °C'
        try:
            una['consumo'] = '%d W' % round(float(fila[5]))
        except ValueError:
            pass
        suyos = sorted(ocupan.get(fila[6], []), reverse=True)
        if suyos:
            una['la_ocupan'] = [dict(programa=nombre, memoria='%d MiB' % mib) for mib, nombre in suyos[:MAS]]
        vistas.append(una)
    return vistas


def procesos(ps, muestra):
    """Consumo por programa, sumando sus procesos: Chrome son cuarenta y es uno."""
    vivos = []
    for p in ps.process_iter(['name']):
        try:
            p.cpu_percent(None)
            vivos.append(p)
        except (ps.NoSuchProcess, ps.AccessDenied):
            continue
    time.sleep(muestra)
    suma = {}
    for p in vivos:
        try:
            cpu, memoria = p.cpu_percent(None), p.memory_info().rss
        except (ps.NoSuchProcess, ps.AccessDenied):
            continue
        nombre = p.info.get('name') or '?'
        fila = suma.setdefault(nombre, [0.0, 0, 0])
        fila[0] += cpu
        fila[1] += memoria
        fila[2] += 1
    return suma


def lista(suma, clave, nucleos):
    """Los que más gastan. La CPU va sobre el total del equipo, no sobre un núcleo."""
    orden = sorted(suma.items(), key=lambda par: par[1][clave], reverse=True)[:MAS]
    filas = []
    for nombre, (cpu, memoria, cuantos) in orden:
        if clave == 0 and round(cpu / nucleos) < 1:
            break
        fila = dict(programa=nombre, cpu='%d %%' % round(cpu / nucleos), memoria=tamano(memoria))
        if cuantos > 1:
            fila['procesos'] = cuantos
        filas.append(fila)
    return filas


def discos(ps):
    vistos, filas = set(), []
    for parte in ps.disk_partitions(all=False):
        if parte.fstype in SIN_DISCO or parte.device in vistos or parte.mountpoint.startswith(('/snap/', '/boot')):
            continue
        vistos.add(parte.device)
        try:
            uso = ps.disk_usage(parte.mountpoint)
        except OSError:
            continue
        filas.append(dict(montado_en=parte.mountpoint, usado='%s de %s (%d %%)' % (tamano(uso.used), tamano(uso.total), round(uso.percent)),
                          libre=tamano(uso.free), porcentaje=round(uso.percent)))
    return filas


def temperatura_cpu(ps):
    """La más alta de los sensores del procesador; None donde el sistema no la da (Windows)."""
    try:
        sensores = ps.sensors_temperatures()
    except (AttributeError, OSError):
        return None
    for chip in ('coretemp', 'k10temp', 'zenpower', 'cpu_thermal', 'acpitz'):
        lecturas = [s.current for s in sensores.get(chip, []) if s.current]
        if lecturas:
            return round(max(lecturas))
    return None


def bateria(ps):
    try:
        b = ps.sensors_battery()
    except (AttributeError, OSError):
        return None
    if b is None:
        return None
    dato = dict(carga='%d %%' % round(b.percent), enchufado=bool(b.power_plugged))
    if not b.power_plugged and b.secsleft and b.secsleft > 0:
        dato['le_queda'] = duracion(b.secsleft)
    return dato


def avisos(estado):
    """Lo que se sale de lo normal, dicho en una frase: es lo que suele buscar la pregunta."""
    dichos = []
    memoria = estado['memoria']
    if memoria['porcentaje'] >= 90:
        mayor = estado['mas_memoria'][0] if estado['mas_memoria'] else None
        dichos.append('La memoria RAM está al %d %%' % memoria['porcentaje']
                      + ('; lo que más ocupa es %s (%s).' % (mayor['programa'], mayor['memoria']) if mayor else '.'))
    for grafica in estado.get('grafica', []):
        ocupada = 100 * grafica['memoria_usada_mib'] // max(grafica['memoria_total_mib'], 1)
        if ocupada >= 85:
            quien = grafica.get('la_ocupan')
            dichos.append('La memoria de la gráfica está al %d %%, quedan %s' % (ocupada, grafica['memoria_libre'])
                          + ('; lo que más ocupa es %s (%s).' % (quien[0]['programa'], quien[0]['memoria']) if quien else '.'))
    for disco in estado['discos']:
        if disco['porcentaje'] >= 90:
            dichos.append('El disco %s está al %d %%, quedan %s.' % (disco['montado_en'], disco['porcentaje'], disco['libre']))
    caliente = estado['cpu'].get('temperatura_grados')
    if caliente is not None and caliente >= 90:
        dichos.append('El procesador está a %d °C.' % caliente)
    pila = estado.get('bateria')
    if pila and not pila['enchufado'] and int(pila['carga'].split()[0]) <= 15:
        dichos.append('Queda %s de batería y no está enchufado.' % pila['carga'])
    return dichos


def estado(*, ps=None, consultar=nvidia, muestra=MUESTRA, ahora=time.time):
    ps = ps or psutil
    if ps is None:
        raise RuntimeError('Falta el módulo psutil en este equipo: sin él no se puede medir el consumo.')
    nucleos = ps.cpu_count() or 1
    ps.cpu_percent(None)                               # la primera llamada solo pone el cero
    suma = procesos(ps, muestra)                       # la espera sirve también a la medida global
    uso = ps.cpu_percent(None)
    memoria = ps.virtual_memory()
    cpu = dict(uso='%d %%' % round(uso), nucleos=nucleos)
    grados = temperatura_cpu(ps)
    if grados is not None:
        cpu.update(temperatura='%d °C' % grados, temperatura_grados=grados)
    resultado = dict(
        equipo=dict(nombre=socket.gethostname(), sistema=platform.system() + ' ' + platform.release(),
                    encendido_hace=duracion(ahora() - ps.boot_time())),
        avisos=[],
        cpu=cpu,
        memoria=dict(usada='%s de %s (%d %%)' % (tamano(memoria.total - memoria.available), tamano(memoria.total),
                                                  round(memoria.percent)),
                     libre=tamano(memoria.available), porcentaje=round(memoria.percent)),
        mas_cpu=lista(suma, 0, nucleos),
        mas_memoria=lista(suma, 1, nucleos),
    )
    vistas = graficas(consultar)
    if vistas:
        resultado['grafica'] = vistas
    resultado['discos'] = discos(ps)
    pila = bateria(ps)
    if pila:
        resultado['bateria'] = pila
    resultado['avisos'] = avisos(resultado) or ['Nada fuera de lo normal en memoria, gráfica, discos ni temperatura.']
    if not resultado['mas_cpu']:
        resultado['mas_cpu'] = 'Ningún programa pasa del 1 % del procesador ahora mismo.'
    # Los números sueltos eran para calcular los avisos: al modelo le llega lo legible.
    cpu.pop('temperatura_grados', None)
    resultado['memoria'].pop('porcentaje')
    for disco in resultado['discos']:
        disco.pop('porcentaje')
    for grafica in vistas:
        grafica.pop('memoria_usada_mib')
        grafica.pop('memoria_total_mib')
    return resultado
