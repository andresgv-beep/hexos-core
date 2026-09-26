// Mensajes de voz para Gemma 4 12B: el modelo oye la onda cruda a 16 kHz,
// mono, hasta 30 s. El navegador decodifica lo que sea (webm/opus de la
// grabación, mp3, m4a, wav…) y aquí se deja en WAV PCM de 16 bits.

export const VOICE_RATE = 16_000;
export const VOICE_MAX_SECONDS = 30;

/** WAV PCM 16 bits mono. Las muestras fuera de [-1, 1] se recortan. */
export function encodeWav(samples: Float32Array, rate = VOICE_RATE): Uint8Array {
  const bytes = new Uint8Array(44 + samples.length * 2);
  const view = new DataView(bytes.buffer);
  const text = (offset: number, value: string) => { for (let i = 0; i < value.length; i++) bytes[offset + i] = value.charCodeAt(i); };
  text(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); text(8, "WAVE");
  text(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, "data"); view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const value = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, value < 0 ? value * 0x8000 : value * 0x7fff, true);
  }
  return bytes;
}

export function toBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

/** Cualquier audio que decodifique el navegador -> WAV mono 16 kHz en base64. */
export async function audioToVoice(data: ArrayBuffer): Promise<{ base64: string; seconds: number }> {
  const context = new AudioContext();
  let decoded: AudioBuffer;
  try { decoded = await context.decodeAudioData(data); }
  catch { throw new Error("No se pudo leer el audio."); }
  finally { void context.close(); }
  if (decoded.duration > VOICE_MAX_SECONDS + 0.5) {
    throw new Error(`El audio dura ${Math.round(decoded.duration)} s; Helios oye como máximo ${VOICE_MAX_SECONDS} s.`);
  }
  // OfflineAudioContext mezcla los canales a mono y remuestrea a 16 kHz.
  const offline = new OfflineAudioContext(1, Math.max(1, Math.ceil(decoded.duration * VOICE_RATE)), VOICE_RATE);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start();
  const mono = (await offline.startRendering()).getChannelData(0);
  return { base64: toBase64(encodeWav(mono)), seconds: mono.length / VOICE_RATE };
}

/** El micrófono solo existe en contextos seguros: https o localhost. */
export function canRecord(): boolean {
  return typeof window !== "undefined" && window.isSecureContext && !!navigator.mediaDevices?.getUserMedia
    && typeof MediaRecorder !== "undefined";
}
