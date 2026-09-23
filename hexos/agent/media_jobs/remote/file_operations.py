"""Operaciones de una ficha; cada efecto conserva su temporal y su evidencia."""
import fcntl
import os
from pathlib import Path

from .file_common import (Rejected, copy_checked, directory,
                          inspect, sha256, sync_directory, save)
from .file_layout import layout
from .file_media import probe, validate_media, decode


def paths(request):
    job, config = request['job'], request['config']
    source = job['source']
    path = Path(source['path'])
    root = Path(source['library_root'])
    if str(root) not in config['libraries'] or not root.is_absolute() or root == Path('/'):
        raise Rejected('Biblioteca no autorizada por el operador')
    if root not in path.parents or '..' in path.parts:
        raise Rejected('Origen fuera de la biblioteca')
    destination = path.with_name(path.stem+'.optimizada.mkv')
    if str(destination) != source['destination']:
        raise Rejected('Destino distinto del derivado del origen')
    names = layout(job,request['run_id'])
    staged = Path(config['storage'])/'.hexos-media'/names['input']
    output = Path(config['output'])/'.hexos-media'/names['output']
    return path, destination, staged, output


def stage(request, root, checkpoint):
    job, config = request['job'], request['config']
    source, destination, staged, _ = paths(request)
    inspect(source, job['source']['identity'])
    if destination.exists() or destination.is_symlink():
        raise Rejected('Ya existe una salida en el destino')
    staged.parent.mkdir(parents=True, exist_ok=True)
    temporary = staged.with_name(staged.name+'.part')
    evidence = copy_checked(source, temporary, job['source']['identity'], checkpoint)
    metadata = probe(temporary, config, root, checkpoint)
    checkpoint()
    os.link(str(temporary), str(staged), follow_symlinks=False)
    if job.get('layout_version',1)==2:
        temporary.unlink()
    sync_directory(staged.parent)
    if job.get('layout_version',1)==2:
        save(staged.parent/'estado.json', dict(job_id=job['id'],source=str(source),destination=str(destination),status='copied'))
    return dict(copied=True, path=str(staged), container_path='/storage/.hexos-media/'+layout(job,request['run_id'])['input'],
                identity=inspect(staged), sha256=evidence['sha256'], probe=metadata)


def verify(request, root, checkpoint):
    job, config = request['job'], request['config']
    source, _, staged, output = paths(request)
    inspect(source, job['source']['identity'])
    inspect(staged, job['staging']['identity'])
    before = inspect(output)
    if before['size_bytes'] <= 0 or before['size_bytes'] != job['completion']['output_bytes']:
        raise Rejected('Salida vacía o distinta del recibo del encoder')
    if config.get('require_smaller', True) and before['size_bytes'] >= job['source']['identity']['size_bytes']:
        raise Rejected('La conversión no reduce el tamaño; conservar para revisión, sin publicar')
    if job['completion'].get('exit_code') != 0 or job['completion'].get('run_id') != request['run_id']:
        raise Rejected('No consta finalización correcta de esta ejecución')
    metadata = probe(output, config, root, checkpoint)
    facts = validate_media(job['staging']['probe'], metadata, job['profile']['preset'])
    digest = sha256(output, checkpoint)
    decode(output, config, root, checkpoint)
    inspect(output, before)
    if job.get('layout_version',1)==2:
        verified = Path(config['output'])/'.hexos-media'/layout(job,request['run_id'])['verified']
        checkpoint()
        os.link(str(output),str(verified),follow_symlinks=False)
        output.unlink()
        sync_directory(verified.parent)
        save(verified.parent/'estado.json', dict(job_id=job['id'],source=str(source),
             destination=job['source']['destination'],status='verified',file=str(verified),sha256=digest))
    return dict(valid=True, identity=before, sha256=digest, probe=metadata,
                decoded=True, facts=facts, run_id=request['run_id'],
                size_goal='smaller_than_source' if config.get('require_smaller', True) else 'not_enforced')


def publish(request, root, checkpoint):
    job = request['job']
    source, destination, _, output = paths(request)
    if job.get('layout_version',1)==2:
        output = Path(request['config']['output'])/'.hexos-media'/layout(job,request['run_id'])['verified']
    validated = job['validation']
    if validated.get('valid') is not True or validated.get('decoded') is not True or validated.get('run_id') != request['run_id']:
        raise Rejected('Falta validación de esta salida')
    inspect(source, job['source']['identity'])
    inspect(output, validated['identity'])
    temporary = destination.with_name('.hexos-'+request['run_id']+'.part')
    # La copia vive en el filesystem de destino; link publica sin reemplazar.
    evidence = copy_checked(output, temporary, validated['identity'], checkpoint)
    if evidence['sha256'] != validated['sha256']:
        raise Rejected('La salida cambió desde su validación')
    checkpoint()
    parent = directory(destination.parent)
    try:
        # Comparte candado con cancelación: esta se confirma antes o después del commit.
        with (root.parent.parent/'control.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            checkpoint()
            inspect(source, job['source']['identity'])
            os.link(temporary.name, destination.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            os.fsync(parent)
        observed = inspect(destination, evidence['identity'])
        if job.get('layout_version',1)==2:
            save(output.parent/'estado.json',dict(job_id=job['id'],source=str(source),
                 destination=str(destination),status='published',original_preserved=True))
        return dict(published=True, path=str(destination), identity=observed,
                    sha256=evidence['sha256'], original_preserved=True)
    finally:
        os.close(parent)


def observe_publication(request, root, checkpoint):
    job = request['job']
    _, destination, _, _ = paths(request)
    actual = inspect(destination, job['publication']['identity'])
    if sha256(destination, checkpoint) != job['publication']['sha256']:
        raise Rejected('El destino cambió tras publicarlo')
    return dict(path=str(destination), identity=actual, verified=True)


OPERATIONS = dict(stage=stage, verify=verify, publish=publish, index=observe_publication)
