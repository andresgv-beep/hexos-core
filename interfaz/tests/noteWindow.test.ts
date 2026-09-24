import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { NoteWindow } from '../components/NoteWindow';
import { noteAsMarkdown } from '../lib/helios/core';

test('note viewer formats Markdown safely and preserves the source for download', () => {
  const body = '**Resumen**\n\n* Disco `sda`\n* <script>alert(1)</script>';
  const note = { id: 'test', title: 'Revisión', body, state: 'pendiente', favorite: false, tags: [], updatedAt: '', revision: 1, revisions: [] };
  const html = renderToStaticMarkup(createElement(NoteWindow, {
    state: { id: 'test', slot: 0, x: 0, y: 0, minimized: false, note }, front: true,
    onMove() {}, onMinimize() {}, onClose() {}, onFocus() {},
  }));
  assert.match(html, /<strong>Resumen<\/strong>/);
  assert.match(html, /<ul>/);
  assert.match(html, /<code>sda<\/code>/);
  assert.doesNotMatch(html, /<script>|\*\*Resumen\*\*/);
  assert.ok(noteAsMarkdown(note).includes(body));
});
