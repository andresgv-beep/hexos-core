"""Nombres deterministas compartidos entre el host y el adaptador del encoder."""
from pathlib import Path
import re


def clipped(text, limit=150):
    # Límite en bytes para NAME_MAX, preservando fronteras UTF-8.
    return text.encode('utf-8')[:limit].decode('utf-8', errors='ignore')


def layout(job, run_id):
    version = job.get('layout_version', 1)
    source = Path(job['source']['path'])
    if version == 1:
        return dict(input=job['id']+'/source'+source.suffix.lower(),
                    output=run_id+'/encoded.mkv', verified=run_id+'/encoded.mkv')
    if version != 2:
        raise ValueError('Versión de nombres de tarea desconocida')
    if not re.fullmatch('[a-f0-9]{32}', job['id']) or not re.fullmatch('[a-f0-9]{64}',run_id):
        raise ValueError('Identidad de tarea inválida')
    title = clipped(re.sub(r'[\\/\x00-\x1f\x7f]', '_', source.stem)).strip(' .') or 'Película'
    folder = title+'--'+job['id']
    output_folder = folder+'--intento-'+str(int(job['attempt']))
    return dict(input=folder+'/'+title+source.suffix.lower(),
                output=output_folder+'/'+title+'.parcial.mkv',
                verified=output_folder+'/'+title+'.optimizada.mkv')
