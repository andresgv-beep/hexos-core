import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ToolActivityPanel } from '../components/ToolActivityPanel';
import type { ToolActivity } from '../lib/helios/tools';

test('all recent tools have individual accessible controls and distinguishable states', () => {
  const tools: ToolActivity[] = ['nas.read','nas.search','note.save','media.prepare','profile.recall','web.search'].map((name, index) => ({
    id: String(index), name, status: index === 0 ? 'running' : index === 2 ? 'failed' : 'done', seconds: index === 0 ? null : 1.2,
  }));
  const html = renderToStaticMarkup(createElement(ToolActivityPanel, { tools }));
  assert.equal((html.match(/<button /g) ?? []).length, 6);
  for (const tool of tools) assert.ok(html.includes(`aria-label="${tool.name} · `));
  assert.match(html, /6 recientes · 1 en curso/);
  assert.match(html, /note.save · Con error/);
  assert.match(html, /<strong>nas.read<\/strong>/);
});
