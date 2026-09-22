"""Configurar el servicio opt-in con rutas del operador y un preset exportado."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from .profiles import freeze


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','device','preset-json','storage','output','control','ffmpeg','ffprobe'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--library',action='append',required=True,help='Raíz exacta clasificada como películas; repetible')
    parser.add_argument('--container',default='HandBrake')
    parser.add_argument('--profile-id',default='jellyfin-rf19')
    args=parser.parse_args()
    imported=json.loads(Path(args.preset_json).read_text())
    config=dict(enabled=True,device=args.device,container=args.container,
                profiles=[freeze(args.profile_id,imported['preset'])],preset_version=imported['version'],
                files=dict(libraries=args.library,storage=args.storage,output=args.output,control=args.control,
                           ffmpeg=args.ffmpeg,ffprobe=args.ffprobe,require_smaller=True))
    for field in ('storage','output','control','ffmpeg','ffprobe'):
        path=Path(config['files'][field])
        if not path.is_absolute() or '..' in path.parts or path==Path('/'):
            parser.error('Ruta absoluta del NAS requerida para '+field)
    if any(not Path(p).is_absolute() or '..' in Path(p).parts or p=='/' for p in args.library):
        parser.error('Bibliotecas absolutas específicas, no /')
    root=Path(args.workspace);root.mkdir(parents=True,exist_ok=True)
    target=root/'media_jobs.json'
    if target.exists():parser.error('La configuración ya existe; revísala antes de sustituirla')
    fd,name=tempfile.mkstemp(dir=root,prefix='.media-config-')
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(config,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
        os.link(name,target)
    finally:os.unlink(name)
    print('Configurado:',target)
    print('Reinicia Helios desde esta rama. media.options comprobará si el servicio está disponible.')


if __name__=='__main__':main()
