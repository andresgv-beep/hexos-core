"""Congelar presets completos: el nombre de un preset no sustituye sus parámetros."""
import hashlib
import json


def freeze(profile_id, preset):
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise ValueError('profile_id requerido')
    if not isinstance(preset, dict) or preset.get('Folder'):
        raise ValueError('Se necesita un preset hoja completo exportado de HandBrake')
    if preset.get('VideoEncoder') != 'x264' or preset.get('FileFormat') != 'av_mkv':
        raise ValueError('Primera versión: x264 y MKV')
    required = ('PresetName', 'VideoQualitySlider', 'VideoPreset', 'AudioList')
    if any(key not in preset for key in required):
        raise ValueError('Preset incompleto; importar la configuración exportada')
    raw = json.dumps(preset, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return dict(id=profile_id, sha256=hashlib.sha256(raw.encode()).hexdigest(),
                preset=json.loads(raw))


def validate(profile):
    expected = freeze(profile['id'], profile['preset'])
    if expected != profile:
        raise ValueError('El perfil no coincide con su hash o contrato')
    return expected
