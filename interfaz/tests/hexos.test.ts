import assert from 'node:assert/strict';
import test from 'node:test';
import { createHexosTransport } from '../lib/helios/hexos';
import { clampEnergy, phaseFromHexos } from '../lib/helios/state';
import { mergeToolActivities } from '../lib/helios/tools';

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
test('reads the thinking channel, and null when the engine has none', async () => {
  const conCanal = await createHexosTransport('/api', fixture({ state: 'idle', mode: 'native-experimental', thinking: true })).status();
  assert.equal(conCanal.thinking, true);
  // El adaptador JSON no tiene canal: null, no false, para no ofrecer un botón muerto.
  const sinCanal = await createHexosTransport('/api', fixture({ state: 'idle', mode: 'json', thinking: null })).status();
  assert.equal(sinCanal.thinking, null);
});

test('reads the credential request so the dialog can appear mid-turn', async () => {
  const pedido = await createHexosTransport('/api', fixture({ state: 'thinking', mode: 'native-experimental',
    credential_request: { device: 'synology 1', host: 'servidorsrv1.ddns.net', pinned: true } })).status();
  assert.equal(pedido.credentialRequest?.device, 'synology 1');
  assert.equal(pedido.credentialRequest?.host, 'servidorsrv1.ddns.net');
  assert.equal(pedido.credentialRequest?.pinned, true);
  const sin = await createHexosTransport('/api', fixture({ state: 'idle', mode: 'json' })).status();
  assert.equal(sin.credentialRequest, null);
});

test('sends the access only when it is complete, and confirms where it went', async () => {
  const t = createHexosTransport('/api', fixture({ saved: true, device: 'synology 1', user: 'helios',
    host: 'servidorsrv1.ddns.net', pinned: true }));
  const guardado = await t.saveAccess({ device: 'synology 1', user: 'helios', password: 'x',
    host: 'servidorsrv1.ddns.net' });
  assert.equal(guardado.host, 'servidorsrv1.ddns.net');
  assert.equal(guardado.pinned, true);
  // Sin contraseña no se llega a enviar nada.
  await assert.rejects(() => t.saveAccess({ device: 'a', user: 'b', password: '' }));
  await assert.rejects(() => t.saveAccess({ device: '', user: 'b', password: 'x' }));
  // Y si el backend no lo confirma, no se da por guardado.
  await assert.rejects(() => createHexosTransport('/api', fixture({ ok: true }))
    .saveAccess({ device: 'a', user: 'b', password: 'x' }));
});

test('confirms the thinking change instead of assuming it worked', async () => {
  const transporte = createHexosTransport('/api', fixture({ thinking: false, persisted: true }));
  assert.equal(await transporte.setThinking(false), false);
  // Sin confirmación del backend, el botón no debe cambiar de estado.
  await assert.rejects(() => createHexosTransport('/api', fixture({ ok: true })).setThinking(true));
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

test('exposes only bounded tool lifecycle data to the interface', async () => {
  const status = await createHexosTransport('/api', fixture({
    state: 'tool', mode: 'native-experimental', active_tools: [
      { tool: 'nas.read', status: 'running', arguments: { password: 'secret' }, result: { private: true } },
      { tool: '', status: 'running' },
    ],
  })).status();
  assert.deepEqual(status.tools, [{ id: '0-nas.read', name: 'nas.read', status: 'running', seconds: null }]);
  assert.equal('arguments' in status.tools[0], false);

  const reply = await createHexosTransport('/api', fixture({ reply: 'Listo', tools: [
    { tool: 'network.local', failed: false, seconds: .42, result: { addresses: [] } },
    { tool: 'document.read', failed: true, seconds: 2 },
  ] })).send('Comprueba');
  assert.deepEqual(reply.tools.map(tool => [tool.name, tool.status]), [['network.local', 'done'], ['document.read', 'failed']]);
});

test('keeps a six-tool constellation and updates repeated tools in place', () => {
  const previous = [
    { id: 'ssh', name: 'nas.read', status: 'done' as const, seconds: 2 },
    { id: 'net', name: 'network.local', status: 'done' as const, seconds: 1 },
  ];
  const merged = mergeToolActivities(previous, [
    { id: 'new-net', name: 'network.local', status: 'running', seconds: null },
    { id: 'doc', name: 'document.read', status: 'done', seconds: .4 },
  ]);
  assert.deepEqual(merged.map(tool => [tool.id, tool.name, tool.status]), [
    ['ssh', 'nas.read', 'done'], ['net', 'network.local', 'running'], ['doc', 'document.read', 'done'],
  ]);
});
