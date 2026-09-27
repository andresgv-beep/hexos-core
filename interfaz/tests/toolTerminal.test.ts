import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ToolTerminal } from '../components/ToolTerminal';
import type { ToolActivity } from '../lib/helios/tools';

const tools: ToolActivity[] = [
  { id: '0', name: 'media.options', status: 'done', seconds: 0.3 },
  { id: '1', name: 'media.prepare', status: 'failed', seconds: 0.5 },
  { id: '2', name: 'media.start', status: 'running', seconds: null },
];

test('while the turn works every call shows its state and time', () => {
  const html = renderToStaticMarkup(createElement(ToolTerminal, { tools, live: true }));
  assert.equal((html.match(/<li /g) ?? []).length, 3);
  assert.match(html, /3 llamadas · 1 en curso · 1 con error/);
  assert.match(html, /<span>media\.<\/span>start/);
  assert.match(html, /data-status="failed".*error/);
  assert.match(html, /0,3 s/);
  assert.match(html, /aria-expanded="true"/);
});

test('a finished turn folds its calls into one line', () => {
  const done = tools.map(tool => ({ ...tool, status: 'done' as const, seconds: tool.seconds ?? 1.2 }));
  const html = renderToStaticMarkup(createElement(ToolTerminal, { tools: done, live: false }));
  assert.equal((html.match(/<li /g) ?? []).length, 0);
  assert.match(html, /3 llamadas · 2,0 s/);
  assert.match(html, /aria-expanded="false"/);
});

test('no calls, no terminal', () => {
  assert.equal(renderToStaticMarkup(createElement(ToolTerminal, { tools: [], live: true })), '');
});
