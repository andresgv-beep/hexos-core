"""Lector SSH acotado; configuración local y comandos fijos, fuera del modelo."""
import ipaddress
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from .work import now


COMMANDS = {
    'system': 'uname -a; uptime; cat /etc.defaults/VERSION',
    'storage': 'cat /proc/mdstat; cat /proc/partitions',
    'kernel': 'dmesg',
    'messages': 'tail -n 200 /var/log/messages',
}


def diagnose(workspace, section):
    if section not in COMMANDS:
        raise ValueError('Sección permitida: system, storage, kernel o messages')
    config_path = Path(workspace) / 'synology_ssh.json'
    if not config_path.exists():
        raise ValueError('Acceso SSH al Synology aún sin configurar')
    config = json.loads(config_path.read_text())
    host = str(ipaddress.ip_address(config['host']))
    user = config['user']
    port = config.get('port', 22)
    if not isinstance(user, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}', user):
        raise ValueError('Usuario SSH inválido')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Puerto SSH inválido')
    # Relativas al workspace, no al directorio de trabajo: así la config viaja
    # a otra máquina sin reescribir rutas absolutas.
    def locate(name):
        path = Path(config[name]).expanduser()
        return (path if path.is_absolute() else Path(workspace) / path).resolve()
    key = locate('identity_file')
    hosts = locate('known_hosts_file')
    if not key.is_file() or not hosts.is_file():
        raise ValueError('Falta la clave de acceso o el archivo de claves de host verificadas')
    binary = shutil.which('ssh')
    if not binary:
        raise ValueError('Cliente SSH no disponible')
    argv = [binary, '-F', '/dev/null', '-T', '-p', str(port), '-i', str(key),
            '-o', 'BatchMode=yes', '-o', 'PasswordAuthentication=no',
            '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'UserKnownHostsFile='+str(hosts), '-o', 'ConnectTimeout=5',
            '-o', 'ConnectionAttempts=1', '-o', 'ForwardAgent=no',
            '-o', 'ClearAllForwardings=yes', '-l', user, host, COMMANDS[section]]
    # Ficheros temporales evitan acumular toda una salida grande en memoria.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        timed_out = False
        try:
            result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err, timeout=15)
            code = result.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            code = None
        size = out.tell()
        # En kernel interesa el final del buffer. En ambos casos se declara el recorte.
        out.seek(max(0, size-16000) if section == 'kernel' else 0)
        content = out.read(16000).decode(errors='replace')
        err.seek(0)
        error = err.read(2000).decode(errors='replace')
    return dict(target='synology', host=host, section=section, observed_at=now(),
                exit_code=code, timed_out=timed_out, stdout=content, stderr=error,
                truncated=size>16000, read_only_commands=True,
                note='Salida de comandos de lectura; errores o falta de permisos no equivalen a discos sanos. '
                     'Las secciones system y storage incluyen varias consultas; revisa también stderr.')
