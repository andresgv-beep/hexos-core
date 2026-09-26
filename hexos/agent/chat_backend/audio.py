"""Mensajes de voz: WAV en base64 -> AudioClip mono float32 a 16 kHz."""
import array
import base64
import binascii
import io
import sys
import wave

from ..native_transport import AudioClip

SAMPLE_RATE = 16_000
MAX_SECONDS = 30   # lo que admite Gemma 4 12B: 750 tokens de 40 ms


def _resample(samples, source_rate):
    """Interpolación lineal. La voz ya viene a 16 kHz desde la interfaz; esto
    solo cubre un WAV subido a otra frecuencia."""
    if source_rate == SAMPLE_RATE or not samples:
        return samples
    length = max(1, round(len(samples) * SAMPLE_RATE / source_rate))
    step = source_rate / SAMPLE_RATE
    last = len(samples) - 1
    out = array.array('f', bytes(4 * length))
    for i in range(length):
        position = i * step
        left = int(position)
        right = min(left + 1, last)
        fraction = position - left
        out[i] = samples[min(left, last)] * (1 - fraction) + samples[right] * fraction
    return out


def decode_audio(encoded):
    """base64 de un WAV PCM de 16 bits -> AudioClip. None si no hay audio."""
    if encoded is None:
        return None
    if not isinstance(encoded, str) or not encoded:
        raise ValueError('audio debe ser una cadena base64 de un WAV')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError('audio no es base64 válido') from exc
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError('audio mayor de 16 MiB')
    try:
        with wave.open(io.BytesIO(raw)) as source:
            channels, width, rate = source.getnchannels(), source.getsampwidth(), source.getframerate()
            frames = source.readframes(source.getnframes())
    except (wave.Error, EOFError) as exc:
        raise ValueError('no se pudo leer el WAV: ' + str(exc)) from exc
    if width != 2 or channels < 1 or rate <= 0:
        raise ValueError('el WAV debe ser PCM de 16 bits')
    seconds = len(frames) / (2 * channels * rate)
    if seconds > MAX_SECONDS + 0.5:
        raise ValueError('el audio dura %.0f s; el máximo es %d s' % (seconds, MAX_SECONDS))
    pcm = array.array('h', frames)
    if sys.byteorder != 'little':
        pcm.byteswap()
    mono = array.array('f', (sum(pcm[i:i + channels]) / (channels * 32768.0)
                             for i in range(0, len(pcm), channels)))
    mono = _resample(mono, rate)
    if not mono:
        raise ValueError('el audio está vacío')
    return AudioClip(mono.tobytes(), SAMPLE_RATE)
