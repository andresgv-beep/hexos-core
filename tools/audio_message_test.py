"""Mensajes de voz: WAV -> AudioClip -> runtime nativo -> adjunto pcm_f32."""
import array
import base64
import io
import math
import tempfile
import threading
import unittest
import wave
from collections import deque
from types import SimpleNamespace

from hexos.agent.chat import Agent
from hexos.agent.chat_backend.audio import decode_audio
from hexos.agent.chat_backend.settings import AUDIO_SIN_TEXTO
from hexos.agent.native import NativeRuntime
from hexos.agent.native_transport import AudioClip, NativeTransport


def wav(seconds=1.0, rate=16000, channels=1, width=2):
    frames = int(seconds * rate)
    samples = array.array('h', (int(8000 * math.sin(i / 10)) for i in range(frames) for _ in range(channels)))
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(samples.tobytes() if width == 2 else bytes(frames * channels * width))
    return base64.b64encode(buffer.getvalue()).decode()


class DecodeAudioTest(unittest.TestCase):
    def test_voice_at_16k_is_kept_sample_for_sample(self):
        clip = decode_audio(wav(1.5))
        self.assertEqual((clip.sample_rate, round(clip.seconds, 3)), (16000, 1.5))
        first = array.array('f', clip.pcm[:8])
        self.assertAlmostEqual(first[1], int(8000 * math.sin(0.1)) / 32768, places=6)

    def test_stereo_48k_becomes_mono_16k(self):
        clip = decode_audio(wav(1.0, rate=48000, channels=2))
        self.assertEqual(len(clip.pcm) // 4, 16000)

    def test_rejects_what_the_model_cannot_take(self):
        self.assertIsNone(decode_audio(None))
        for bad, reason in ((wav(31), 'máximo es 30'), (wav(1, width=1), '16 bits'),
                            ('no-es-base64!', 'base64'), (base64.b64encode(b'RIFFxx').decode(), 'WAV')):
            with self.subTest(reason), self.assertRaisesRegex(ValueError, reason):
                decode_audio(bad)


class NativeAudioTest(unittest.TestCase):
    def runtime(self, multimodal=True):
        rt = NativeRuntime.__new__(NativeRuntime)
        rt._transport = SimpleNamespace(model_info={'multimodal': multimodal}, control=lambda _: None)
        rt.messages = []; rt.pending = deque(); rt.current = None
        return rt

    def test_audio_waits_in_the_attachment_slot_and_needs_a_multimodal_model(self):
        rt = self.runtime()
        rt.attach_audio(b'\x00' * 8, 16000)
        self.assertEqual(rt.pending_image, AudioClip(b'\x00' * 8, 16000))
        with self.assertRaisesRegex(RuntimeError, 'unsupported_attachment'):
            self.runtime(multimodal=False).attach_audio(b'\x00' * 8, 16000)
        with self.assertRaises(ValueError):
            rt.attach_audio(b'\x00' * 7, 16000)

    def test_transport_sends_pcm_f32_and_resets_the_session(self):
        transport = NativeTransport.__new__(NativeTransport)
        controls, writes = [], []
        transport.control = lambda request, payload=b'': (controls.append((request, len(payload))),
                                                          {'request_id': 'a1'})[1]
        transport.write = lambda request, payload=b'': writes.append(request)
        transport.poisoned = False
        transport.cancelled = SimpleNamespace(is_set=lambda: False)
        transport.reset_sessions = set()
        transport.aux_ready = True
        transport.state_lock = threading.Lock()
        transport.start('prompt con <|audio|>', AudioClip(b'\x00' * 64, 16000))
        self.assertEqual(controls[0][0]['type'], 'reset')
        self.assertEqual(controls[1], (dict(type='attachment', kind='pcm_f32', bytes=64,
                                            sample_rate=16000, channels=1), 64))
        self.assertEqual(writes[-1]['attachment_ids'], ['a1'])


class VoiceTurnTest(unittest.TestCase):
    class Runtime:
        def __init__(self):
            self.audio, self.inputs = [], []

        def attach_audio(self, pcm, sample_rate):
            self.audio.append((len(pcm), sample_rate))

        def generate(self, messages):
            self.inputs.append(repr(messages))
            return dict(reply='Te he oído.', work=None)

        def call(self, request):
            pass

    def test_a_voice_message_without_text_asks_to_answer_it(self):
        with tempfile.TemporaryDirectory() as workspace:
            runtime = self.Runtime()
            agent = Agent(workspace, runtime)
            agent.chat('', image=AudioClip(b'\x00' * 64000, 16000))
            self.assertEqual(runtime.audio, [(64000, 16000)])
            self.assertIn(AUDIO_SIN_TEXTO, runtime.inputs[0])
            self.assertIn('mensaje de voz de 1.0 s', runtime.inputs[0])


if __name__ == '__main__':
    unittest.main()
