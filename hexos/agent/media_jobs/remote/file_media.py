"""Inspección y decodificación completa con binarios configurados por el operador."""
import json
import math
import subprocess
import tempfile
import time

from .file_common import Rejected


def process(argv, root, checkpoint, timeout):
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=output, stderr=errors)
        deadline = time.monotonic()+timeout
        try:
            while child.poll() is None:
                checkpoint()
                if time.monotonic() >= deadline:
                    raise OSError('Verificador excedió el tiempo máximo configurado')
                time.sleep(.2)
            errors.seek(0); error = errors.read(4096).decode(errors='replace')
            if child.returncode != 0:
                raise Rejected('Verificador rechazó el archivo: '+error)
            output.seek(0); data = output.read(1024*1024+1)
            if len(data) > 1024*1024:
                raise Rejected('Metadatos demasiado grandes')
            return data
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill(); child.wait()


def probe(path, config, root, checkpoint):
    raw = process([config['ffprobe'], '-v', 'error', '-show_entries',
                   'format=duration,format_name,size:stream=codec_name,codec_type,width,height,channels:stream_tags=language',
                   '-of', 'json', str(path)], root, checkpoint, 120)
    return json.loads(raw)


def validate_media(source, output, preset):
    """Una pista AAC (primer audio del idioma pedido), sin passthru; subtítulos opcionales."""
    if preset.get('AudioTrackSelectionBehavior') != 'first' or len(preset.get('AudioList', [])) != 1:
        raise Rejected('Reglas de audio aún no soportadas por el verificador')
    if preset['AudioList'][0].get('AudioEncoder') not in ('fdk_aac', 'av_aac'):
        raise Rejected('Este verificador requiere salida AAC explícita')
    languages = subtitle_languages(preset)
    duration, expected = float(output['format']['duration']), float(source['format']['duration'])
    if not math.isfinite(duration) or not math.isfinite(expected) or expected <= 0 or abs(duration-expected) > max(1.0, expected*.001):
        raise Rejected('Duración de salida fuera de tolerancia')
    if 'matroska' not in output['format']['format_name']:
        raise Rejected('Salida no MKV')
    video = [s for s in output['streams'] if s['codec_type'] == 'video']
    audio = [s for s in output['streams'] if s['codec_type'] == 'audio']
    original_audio = [s for s in source['streams'] if s['codec_type'] == 'audio']
    if len(video) != 1 or video[0]['codec_name'] != 'h264':
        raise Rejected('Se esperaba un vídeo H.264')
    if len(audio) != min(1, len(original_audio)) or any(s['codec_name'] != 'aac' for s in audio):
        raise Rejected('Pistas de audio distintas de las esperadas')
    if not 0 < video[0]['width'] <= 1920 or not 0 < video[0]['height'] <= 1080:
        raise Rejected('Dimensiones de salida inválidas')
    subtitles = [s for s in output['streams'] if s['codec_type'] == 'subtitle']
    offered = [s for s in source['streams'] if s['codec_type'] == 'subtitle'
               and (s.get('tags') or {}).get('language') in languages]
    if any((s.get('tags') or {}).get('language') not in languages for s in subtitles):
        raise Rejected('Subtítulos en un idioma no pedido por el perfil')
    if len(subtitles) > len(offered):
        raise Rejected('Más pistas de subtítulos de las que trae el original')
    return dict(duration_seconds=duration, audio_tracks=len(audio), subtitle_tracks=len(subtitles),
                visual_quality='not_assessed', burned_subtitles='not_assessed')


def subtitle_languages(preset):
    """Sin subtítulos, o los de una lista de idiomas como pistas aparte. Solo se
    queman los forzados que encuentra la búsqueda de audio extranjero; quemar
    pistas completas de Blu-ray/DVD taparía la imagen para siempre."""
    behavior = preset.get('SubtitleTrackSelectionBehavior')
    if behavior == 'none':
        return ()
    languages = preset.get('SubtitleLanguageList')
    if behavior not in ('first', 'all') or not isinstance(languages, list) or not languages \
            or not all(isinstance(code, str) and len(code) == 3 for code in languages):
        raise Rejected('Subtítulos: se necesita una lista de idiomas ISO 639-2')
    if preset.get('SubtitleBurnBehavior') not in ('none', 'foreign') \
            or preset.get('SubtitleBurnBDSub') or preset.get('SubtitleBurnDVDSub'):
        raise Rejected('Subtítulos: solo se pueden quemar los forzados')
    return tuple(languages)


def decode(path, config, root, checkpoint):
    process([config['ffmpeg'], '-nostdin', '-v', 'error', '-xerror', '-i', str(path),
             '-map', '0:v', '-map', '0:a?', '-f', 'null', '-'], root, checkpoint,
            config.get('verification_timeout_seconds', 86400))
