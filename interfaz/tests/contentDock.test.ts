import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ContentDock } from '../components/ContentDock';

const actions = { fileRequest: null, busy: false, canUndo: false, onUndo() {}, onExpandCode() {}, onExpandFile() {}, onImprove() {}, onPreview() {} };
test('content dock exposes three destinations without inventing file content', () => {
  const html = renderToStaticMarkup(createElement(ContentDock, { ...actions, artifact: null }));
  for (const label of ['Código', 'Interfaz', 'NAS']) assert.ok(html.includes(label));
  assert.doesNotMatch(html, /<dialog|<iframe|download=/);
});
test('code stays escaped and can be downloaded and expanded from the dock', () => {
  const html = renderToStaticMarkup(createElement(ContentDock, { ...actions, artifact: { reply: '', code: '<script>alert(1)</script>', language: 'html' } }));
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /download="helios.html"/);
  assert.match(html, /Abrir implementación en ventana/);
  assert.match(html, /Copiar código/);
});
