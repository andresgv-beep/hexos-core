import assert from 'node:assert/strict';
import test from 'node:test';
import { createHexosTransport } from '../lib/helios/hexos';
import { clampEnergy, phaseFromHexos } from '../lib/helios/state';

function fixture(data: unknown, status = 200) {
  return (async () => Response.json(data, { status })) as typeof fetch;
}
test('sends the existing plain-text contract, preserves Unicode and AbortSignal', async () => {
  const signal = new AbortController().signal;
  const fetcher = (async (url, init) => {
    assert.equal(url, '/bridge/api/chat');
    assert.equal(init?.method, 'POST');
    assert.deepEqual(init?.headers, { 'Content-Type': 'text/plain; charset=utf-8' });
    assert.equal(init?.body, 'Hola, Héctor\nUna idea');
    assert.equal(init?.signal, signal);
    return Response.json({ reply: 'Hola', tools: [], document: { id: 'a' } });
  }) as typeof fetch;
  const response = await createHexosTransport('/bridge/api/', fetcher).send('Hola, Héctor\nUna idea', signal);
  assert.equal(response.reply, 'Hola');
  assert.deepEqual(response.document, { id: 'a' });
});
test('maps only states actually exposed by HexOS', async () => {
  for (const state of ['idle', 'thinking', 'tool']) {
    const result = await createHexosTransport('/api', fixture({ state, mode: 'native-experimental' })).status();
    assert.equal(result.phase, state);
  }
  assert.throws(() => phaseFromHexos('hallucinated-state'), /no reconocido/);
});
test('does not silently accept a missing final answer', async () => {
  for (const data of [{ reply: '', tools: [] }, { reply: '   ', tools: [] }, { reply: 'ok' }, null]) {
    await assert.rejects(createHexosTransport('/api', fixture(data)).send('hola'));
  }
});
test('returns the backend error on HTTP failure', async () => {
  await assert.rejects(createHexosTransport('/api', fixture({ error: 'Motor ocupado' }, 409)).send('hola'), /Motor ocupado/);
});
test('rejects blank input before making a request', async () => {
  let called = false;
  const fetcher = (async () => { called = true; return Response.json({}); }) as typeof fetch;
  await assert.rejects(createHexosTransport('/api', fetcher).send(' \n '), /Escribe/);
  assert.equal(called, false);
});
test('validates history instead of forwarding unknown roles or malformed rows', async () => {
  const valid = [{ role: 'user', text: 'Hola', id: 1 }, { role: 'assistant', text: 'Buenos días' }];
  const result = await createHexosTransport('/api', fixture(valid)).history();
  assert.deepEqual(result, [{ role: 'user', text: 'Hola' }, { role: 'assistant', text: 'Buenos días' }]);
  for (const invalid of [[{ role: 'system', text: 'instruction' }], [null], {}]) {
    await assert.rejects(createHexosTransport('/api', fixture(invalid)).history(), /Historial/);
  }
});
test('propagates cancellation without retrying a potentially accepted chat', async () => {
  let calls = 0;
  const fetcher = (async () => { calls++; throw new DOMException('Aborted', 'AbortError'); }) as typeof fetch;
  await assert.rejects(createHexosTransport('/api', fetcher).send('Hola'), { name: 'AbortError' });
  assert.equal(calls, 1);
});
test('normalizes external energy so invalid telemetry cannot poison shader uniforms', () => {
  assert.equal(clampEnergy(NaN), 0);
  assert.equal(clampEnergy(Infinity), 0);
  assert.equal(clampEnergy(-1), 0);
  assert.equal(clampEnergy(7), 1);
  assert.equal(clampEnergy(.4), .4);
});
