import test from "node:test";
import assert from "node:assert/strict";
import { encodeWav, toBase64, VOICE_RATE } from "../lib/helios/voice";

test("el WAV es PCM 16 bits mono a 16 kHz, como lo espera HexOS", () => {
  const wav = encodeWav(new Float32Array([0, 0.5, -0.5, 1.5, -2]));
  const view = new DataView(wav.buffer);
  assert.equal(new TextDecoder().decode(wav.subarray(0, 4)), "RIFF");
  assert.equal(new TextDecoder().decode(wav.subarray(8, 12)), "WAVE");
  assert.equal(view.getUint16(20, true), 1);          // PCM
  assert.equal(view.getUint16(22, true), 1);          // mono
  assert.equal(view.getUint32(24, true), VOICE_RATE);
  assert.equal(view.getUint16(34, true), 16);
  assert.equal(view.getUint32(40, true), 10);         // 5 muestras x 2 bytes
  assert.deepEqual([0, 1, 2, 3, 4].map(i => view.getInt16(44 + i * 2, true)), [0, 16383, -16384, 32767, -32768]);
});

test("base64 aguanta audios largos sin desbordar la pila", () => {
  const bytes = new Uint8Array(30 * VOICE_RATE * 2).fill(7);
  const encoded = toBase64(bytes);
  assert.equal(encoded.length, Math.ceil(bytes.length / 3) * 4);
  assert.equal(atob(encoded.slice(0, 4)).charCodeAt(0), 7);
});

test("el historial muestra la voz como al enviarla", async () => {
  const { displayUserText } = await import("../lib/helios/voice");
  assert.equal(displayUserText("Mensaje de voz (5 s), transcrito: «¿Cómo está el Synology?»"), "🎤 «¿Cómo está el Synology?»");
  assert.equal(displayUserText("Mira esto:\n\nMensaje de voz (3 s), transcrito: «hola»"), "Mira esto:\n\n🎤 «hola»");
  assert.equal(displayUserText("Un mensaje normal"), "Un mensaje normal");
  assert.equal(displayUserText("[La persona envió un mensaje de voz de 4.3 s en este turno. Lo estás oyendo ahora; responde a lo que dice.]\nTranscribe exactamente lo que dice el audio, en español."), "🎤 Mensaje de voz (4 s)");
  assert.equal(displayUserText("[Nota interna] algo"), "[Nota interna] algo");
});
