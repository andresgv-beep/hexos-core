"""Proceso durable dentro de HandBrake; stdout del cliente SSH no es su dueño.

Se despliega como archivo versionado. Los registros viven en /config/.hexos-media.
Una intención ya registrada nunca se relanza automáticamente: incluso perder la
respuesta entre Popen y el registro de PID debe reconciliarse, no duplicarse.
"""
import fcntl
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time


def save(path, value):
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w') as stream:
        json.dump(value, stream, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    directory = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def progress_objects(buffer):
    decoder = json.JSONDecoder()
    position = 0
    while True:
        start = buffer.find('Progress:', position)
        if start < 0:
            return
        brace = buffer.find('{', start)
        if brace < 0:
            return
        try:
            item, length = decoder.raw_decode(buffer[brace:])
        except ValueError:
            return
        yield item
        position = brace + length


def run(request_path):
    request_path = Path(request_path)
    request = json.loads(request_path.read_text())
    root = request_path.parent
    state_path = root/'state.json'
    def persist(value):
        save(state_path,value)
        if request.get('display'):
            target_dir = Path(request['output']).parent
            target_dir.mkdir(parents=True,exist_ok=True)
            save(target_dir/'estado.json',dict(request['display'],**value))
    lock = (root/'run.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    if state_path.exists():
        return
    state = dict(run_id=request['run_id'], status='launching', phase='starting', percent=0,
                 eta_seconds=None, output_bytes=0, activity_counter=0, observed_at=time.time())
    resource = (root.parent/'encoder.lock').open('a')
    try:
        fcntl.flock(resource, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        persist(dict(state, status='blocked', error='Otro trabajo HexOS ocupa el encoder'))
        return
    if (root/'cancel').exists():
        persist(dict(state, status='finished', exit_code=130))
        return
    # No competir con otro CLI. El uso exclusivo frente a GUI queda como
    # precondición operativa del adaptador; no se deduce del estado running.
    for proc in Path('/proc').glob('[0-9]*/comm'):
        try:
            if proc.read_text().strip() == 'HandBrakeCLI':
                persist(dict(state, status='blocked', error='Hay otro HandBrakeCLI activo'))
                return
        except OSError:
            pass
    target = Path(request['output'])
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        persist(dict(state, status='blocked', error='La salida ya existe sin recibo de esta ejecución'))
        return
    preset = root/'preset.json'
    save(preset, request['preset_export'])
    argv = ['HandBrakeCLI', '--json', '--preset-import-file', str(preset),
            '--preset', request['preset_name'], '--input', request['input'], '--output', str(target)]
    # El intento queda durable ANTES de iniciar el proceso externo.
    persist(state)
    try:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors='replace', start_new_session=True)
    except OSError as exc:
        persist(dict(state, status='finished', exit_code=127, error=str(exc)))
        return
    state.update(status='running', pid=proc.pid)
    persist(state)
    chunks = queue.Queue(maxsize=256)
    def read_output():
        for line in proc.stdout:
            chunks.put(line)
        chunks.put(None)
    thread = threading.Thread(target=read_output, daemon=True)
    thread.start()
    buffer = ''
    last_write = 0
    cancel_at = None
    log_path = target.parent/'handbrake.log' if request.get('display') else root/'encoder.log'
    with log_path.open('a') as log:
        eof = False
        while not eof or proc.poll() is None:
            now = time.time()
            if (root/'cancel').exists() and proc.poll() is None:
                if cancel_at is None:
                    proc.terminate()
                    cancel_at = now
                elif now-cancel_at > 10:
                    proc.kill()
            try:
                chunk = chunks.get(timeout=0.5)
                if chunk is None:
                    eof = True
                else:
                    log.write(chunk)
                    log.flush()
                    buffer = (buffer+chunk)[-262144:]
                    for item in progress_objects(buffer):
                        phase = item.get('State', 'unknown')
                        detail = item.get('Working') or item.get('Searching') or item.get('Muxing') or {}
                        state.update(phase=phase, percent=round(float(detail.get('Progress',0))*100,3),
                                     eta_seconds=detail.get('ETASeconds'))
            except queue.Empty:
                pass
            if now-last_write >= 1:
                try:
                    stat = Path('/proc', str(proc.pid), 'stat').read_text().rsplit(')',1)[1].split()
                    state['activity_counter'] = int(stat[11])+int(stat[12])
                except (OSError, ValueError, IndexError):
                    pass
                state.update(output_bytes=target.stat().st_size if target.exists() else 0, observed_at=now)
                persist(state)
                last_write = now
        result = proc.wait()
    state.update(status='finished', exit_code=result, observed_at=time.time(),
                 percent=100.0 if result == 0 else state['percent'],
                 output_bytes=target.stat().st_size if target.exists() else 0,
                 cancelled=cancel_at is not None, output=str(target))
    persist(state)


if __name__ == '__main__':
    run(sys.argv[1])
