"""Prueba NAS explícita con vídeo sintético; no busca ni modifica películas.

Desde la raíz: python3 -m tools.media_encoder_smoke --help
Requiere ffmpeg/ffprobe locales y exportación {preset: hoja, version: Version*}.
Deja evidencia y archivos en directorios propios .hexos-media/smoke-*.
"""
import argparse
import base64
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import time
import uuid

from hexos.agent import nas_session
from hexos.agent.media_jobs.nas_encoder import NasHandBrake, NasEncoderTransport
from hexos.agent.media_jobs.profiles import freeze


def remote(workspace, device, code, marker, limit=12000):
    response = nas_session.execute_remote(workspace, device, 'python3 -c '+shlex.quote(code),
                                          'media_smoke', max_output=limit, payload_marker=marker,
                                          timeout_seconds=20)
    if response['exit_code'] != 0 or response['timed_out'] or response['truncated']:
        raise RuntimeError('Prueba sin respuesta SSH completa')
    return next(line[len(marker):] for line in response['output'].splitlines() if line.startswith(marker))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('workspace', 'device', 'storage-host-root', 'output-host-root', 'preset-json', 'evidence'):
        parser.add_argument('--'+flag, required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.preset_json).read_text())
    profile = freeze('smoke-user-preset', config['preset'])
    fixture = 'smoke-'+uuid.uuid4().hex
    host = str(Path(args.storage_host_root)/'.hexos-media'/fixture)
    evidence = dict(fixture=fixture, observations=[])
    with tempfile.TemporaryDirectory() as directory:
        source, output = Path(directory)/'source.mkv', Path(directory)/'encoded.mkv'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=blue:size=320x180:rate=24', '-f', 'lavfi', '-i',
                        'sine=frequency=440:sample_rate=48000', '-t', '15', '-c:v', 'libx264',
                        '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '16k', str(source)],
                       check=True, timeout=30)
        payload = base64.b64encode(source.read_bytes()).decode()
        if len(payload) > 90000:
            raise ValueError('Fixture demasiado grande para este transporte de prueba')
        code = ('import os,base64;os.makedirs('+repr(host)+',exist_ok=False);open('
                +repr(host+'/source.mkv')+',"wb").write(base64.b64decode('+repr(payload)
                +'));print("__FIXTURE__ok")')
        remote(args.workspace, args.device, code, '__FIXTURE__')
        encoder = NasHandBrake(NasEncoderTransport(args.workspace, args.device), config['version'])
        job = dict(id=fixture, attempt=0, source=dict(device=args.device), profile=profile,
                   staging=dict(container_path='/storage/.hexos-media/'+fixture+'/source.mkv'))
        key = fixture+':0:ready'
        job['run_id'] = encoder.start(job, key)['run_id']
        deadline = time.monotonic()+60
        while time.monotonic() < deadline:
            time.sleep(2)
            state = encoder.observe(job)
            evidence['observations'].append(state)
            print(json.dumps(state), flush=True)
            if state['status'] == 'finished':
                break
        evidence['job'] = job
        Path(args.evidence).write_text(json.dumps(evidence, indent=2))
        if state.get('exit_code') != 0:
            encoder.stop(job, key+':stop')
            raise RuntimeError('La prueba no acredita una finalización correcta; recibo conservado')
        repeated = encoder.start(job, key)
        if repeated != state:
            raise RuntimeError('El segundo arranque no devolvió el mismo resultado')
        remote_output = str(Path(args.output_host_root)/'.hexos-media'/job['run_id']/'encoded.mkv')
        code = 'import base64;print("__FILE__"+base64.b64encode(open('+repr(remote_output)+',"rb").read()).decode())'
        output.write_bytes(base64.b64decode(remote(args.workspace, args.device, code, '__FILE__', 2000000)))
        probe = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                                         'format=duration,format_name,size:stream=codec_name,codec_type,width,height',
                                         '-of', 'json', str(output)], timeout=15)
        evidence['probe'] = json.loads(probe)
        if not 14.9 <= float(evidence['probe']['format']['duration']) <= 15.2:
            raise RuntimeError('Duración inesperada')
        codecs = {stream['codec_name'] for stream in evidence['probe']['streams']}
        if not {'h264', 'aac'} <= codecs or 'matroska' not in evidence['probe']['format']['format_name']:
            raise RuntimeError('Contenedor o pistas inesperadas')
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(output), '-f', 'null', '-'],
                       check=True, timeout=30)
        evidence.update(decode_verified=True, repeated_start_same_receipt=True)
        Path(args.evidence).write_text(json.dumps(evidence, indent=2))
        print('OK: MKV/H.264/AAC decodificable; recibo repetido sin nueva compresión.')


if __name__ == '__main__':
    main()
