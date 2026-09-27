import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { VoiceMode } from '../components/VoiceMode';
import { VoiceButton } from '../components/VoiceButton';

test('voice mode is a modal that listens, with the time limit and send or cancel', () => {
  const html = renderToStaticMarkup(createElement(VoiceMode, { onSend() {}, onCancel() {}, onError() {} }));
  assert.match(html, /role="dialog" aria-modal="true"/);
  assert.match(html, /Te escucho…/);
  assert.match(html, /0:00 \/ 0:30/);
  assert.match(html, />Enviar</);
  assert.match(html, />Cancelar</);
});

test('the microphone button only opens voice mode, and waits for the browser to confirm a microphone', () => {
  const html = renderToStaticMarkup(createElement(VoiceButton, { onOpen() {}, disabled: false }));
  assert.match(html, /aria-label="Hablar con Helios"/);
  assert.match(html, /disabled=""/);
});
