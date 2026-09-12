import assert from 'node:assert/strict';
import test from 'node:test';
import { orbTargetScale, previewSpeechAmplitude } from '../lib/helios/motion';

test('voice amplitude expands the sphere visibly and silence lets it contract', () => {
  const silent = orbTargetScale('responding', .8, 0, 0, true);
  const speaking = orbTargetScale('responding', .8, 1, 0, true);
  assert.ok(speaking / silent > 1.17, 'loud syllables must expand diameter by at least 17%');
  assert.ok(orbTargetScale('idle', .16, 0, 0, true) < silent);
});
test('preview has syllables and phrase pauses instead of a constant enlargement', () => {
  const samples = Array.from({ length: 880 }, (_, i) => previewSpeechAmplitude(i / 100));
  assert.ok(samples.every(value => value >= 0 && value <= 1));
  assert.ok(Math.max(...samples) > .7);
  assert.equal(previewSpeechAmplitude(4), 0);
  assert.equal(previewSpeechAmplitude(8.4), 0);
  assert.ok(samples.filter(value => value === 0).length > 150);
});
test('pause/reduced motion ignores time and amplitude changes', () => {
  const frozen = orbTargetScale('responding', .8, 0, 0, false);
  for (let i = 0; i < 20; i++) assert.equal(orbTargetScale('responding', .8, i / 20, i, false), frozen);
});
test('invalid amplitude cannot produce an invalid scale', () => {
  for (const value of [NaN, Infinity, -4, 5]) {
    const scale = orbTargetScale('responding', .8, value, 0, true);
    assert.ok(Number.isFinite(scale) && scale >= 1.08 && scale < 1.31);
  }
});
