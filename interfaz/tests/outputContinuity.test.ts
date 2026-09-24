import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('partial replies cannot replace either the working code or its preview', () => {
  const source = readFileSync(new URL('../components/HeliosExperience.tsx', import.meta.url), 'utf8');
  assert.match(source, /if \(!result.cancelled && !result.incomplete && options\?\.previewSource\)/);
  assert.match(source, /else if \(!result.cancelled && !result.incomplete\)/);
});

test('progressive code keeps the same highlighted renderer while the stream grows', () => {
  const source = readFileSync(new URL('../components/ProgressiveReply.tsx', import.meta.url), 'utf8');
  const code = source.slice(source.indexOf('if (bloque.kind === "code")'), source.indexOf('const lineas ='));
  assert.match(code, /<ReplyCode/);
  assert.doesNotMatch(code, /<Palabra|<\/ReplyCode>/);
  assert.match(code, /complete && !live/);
});
