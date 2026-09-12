import { clampEnergy, type HeliosPhase } from './state';

/** Preview-only envelope: short syllables grouped into phrases with real pauses.
 * A future audio analyser can replace this sampler without React frame updates.
 */
export function previewSpeechAmplitude(time: number): number {
  const phrase = time % 4.4;
  if (phrase > 3.5) return 0;
  const fade = Math.min(1, phrase / .22, (3.5 - phrase) / .28);
  const syllable = Math.pow(.5 + .5 * Math.sin(time * 12.8 + Math.sin(time * 2.1)), 2);
  const inflection = .65 + .35 * Math.sin(time * 3.7) ** 2;
  return clampEnergy(fade * (.12 + syllable * .88) * inflection);
}

export function orbTargetScale(phase: HeliosPhase, energy: number, amplitude: number, time: number, motion: boolean): number {
  const activity = clampEnergy(energy);
  const base = phase === 'responding' ? 1.08 : phase === 'listening' ? 1.025 : phase === 'thinking' || phase === 'tool' ? 1.04 : .96;
  if (!motion) return base;
  const breath = Math.sin(time * 1.35) * (.007 + activity * .008);
  return base + clampEnergy(amplitude) * (.1 + activity * .14) + breath;
}
