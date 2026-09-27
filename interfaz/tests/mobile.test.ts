import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MobileWorkspace } from '../components/MobileWorkspace';

test('mobile presents the supplied single conversation and four panels', () => {
  const html = renderToStaticMarkup(createElement(MobileWorkspace, {
    previous: [{ role: 'user', text: 'Mensaje compartido' }], turns: [], notes: [],
    artifact: null, busy: false, error: '', onBrowseNotes() {}, onPreview() {},
  }));
  for (const label of ['Notas','Chat','Código','Visualización','Mensaje compartido']) assert.ok(html.includes(label));
  assert.equal(html.match(/Mensaje compartido/g)?.length, 1);
  assert.ok(html.includes('Conversación continua'));
  assert.ok(!html.includes('mobile-heading'));
  assert.ok(!html.includes('Tu única conversación'));
});
