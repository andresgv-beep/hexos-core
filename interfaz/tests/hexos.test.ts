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
test('a code review can think for one turn without changing AUTO', async () => {
  const fetcher = (async (url, init) => {
    assert.equal(url, '/api/chat');
    assert.deepEqual(init?.headers, { 'Content-Type': 'application/json' });
    assert.deepEqual(JSON.parse(String(init?.body)), { text: 'Revisa el componente', thinking: true });
    return Response.json({ reply: 'Revisado', tools: [] });
  }) as typeof fetch;
  assert.equal((await createHexosTransport('/api', fetcher).send('Revisa el componente', undefined, undefined, true)).reply, 'Revisado');
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
  // Sin `resume` no hay nada que retomar y la interfaz no debe inventarse un turno.
  assert.equal(guardado.resume, undefined);
  const conRetomar = await createHexosTransport('/api', fixture({ saved: true, device: 'd', user: 'u',
    host: 'h', resume: 'revisa el estado de synology 1' })).saveAccess({ device: 'd', user: 'u', password: 'x' });
  assert.equal(conRetomar.resume, 'revisa el estado de synology 1');
  const vacio = await createHexosTransport('/api', fixture({ saved: true, device: 'd', user: 'u',
    host: 'h', resume: '   ' })).saveAccess({ device: 'd', user: 'u', password: 'x' });
  assert.equal(vacio.resume, undefined);
  const reanudado = await createHexosTransport('/api', fixture({ saved: true, device: 'd', user: 'u',
    host: 'h', resume: 'diagnostica d', resumed_request: 'diagnostica d',
    resumed: { reply: 'Diagnóstico terminado.', tools: [] } }))
    .saveAccess({ device: 'd', user: 'u', password: 'x' });
  assert.equal(reanudado.resumedRequest, 'diagnostica d');
  assert.equal(reanudado.resumed?.reply, 'Diagnóstico terminado.');
  // Sin contraseña no se llega a enviar nada.
  await assert.rejects(() => t.saveAccess({ device: 'a', user: 'b', password: '' }));
  await assert.rejects(() => t.saveAccess({ device: '', user: 'b', password: 'x' }));
  // Y si el backend no lo confirma, no se da por guardado.
  await assert.rejects(() => createHexosTransport('/api', fixture({ ok: true }))
    .saveAccess({ device: 'a', user: 'b', password: 'x' }));
});

test('dismissing an access request sends no credential at all', async () => {
  let enviado: unknown = null;
  const fetcher = (async (_url: string, init: RequestInit) => {
    enviado = JSON.parse(String(init.body));
    return Response.json({ dismissed: 'synology 1', saved: false });
  }) as unknown as typeof fetch;
  await createHexosTransport('/api', fetcher).dismissAccess('synology 1');
  assert.deepEqual(enviado, { device: 'synology 1', dismiss: true });
});

test('reads what Helios announces mid-turn, and ignores what is not usable', async () => {
  const d = await createHexosTransport('/api', fixture({ state: 'thinking', mode: 'native-experimental',
    progress: { turn_id: 't1', messages: [
      { id: 'p1', text: 'Voy a revisar el diagnóstico de ambos NAS.' },
      { id: 'p2', text: '   ' },            // vacío: no se enseña
      { text: 'sin id' },                    // sin id no se puede deduplicar
      'suelto',
    ] } })).status();
  assert.equal(d.progress.turnId, 't1');
  assert.deepEqual(d.progress.messages, [{ id: 'p1', text: 'Voy a revisar el diagnóstico de ambos NAS.' }]);
  // Y un estado sin progreso no rompe nada.
  const vacio = await createHexosTransport('/api', fixture({ state: 'idle', mode: 'json' })).status();
  assert.deepEqual(vacio.progress, { turnId: null, messages: [] });
});

test('reads how the turn closed, and ignores a malformed closure', async () => {
  const t = createHexosTransport('/api', fixture({ reply: 'Hecho.', tools: [],
    closure: { reason: 'parcial', note: 'Alguna operación no llegó a su objetivo.',
               unverified: [{ tool: 'device_identify', verification: 'no_cumplida' }, { mal: 1 }] } }));
  const d = await t.send('haz algo');
  assert.equal(d.closure?.reason, 'parcial');
  // Las entradas sin herramienta no se cuelan como si fueran pasos reales.
  assert.deepEqual(d.closure?.unverified.map(u => u.tool), ['device_identify']);
  const sin = await createHexosTransport('/api', fixture({ reply: 'Hecho.', tools: [] })).send('x');
  assert.equal(sin.closure, undefined);
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

// Pedir «muéstrame la nota» abría el menú y describía la nota en el chat, pero no
// la abría: el id viajaba en la traza de herramientas y se descartaba al parsear.
test('surfaces which notes the turn read or wrote, ignoring the ones that failed', async () => {
  const fetcher = (async () => Response.json({
    reply: 'Aquí la tienes',
    tools: [
      { tool: 'note.list', result: { notes: [{ id: 'no-es-esta' }] } },
      { tool: 'note.get', result: { id: 'abc123', title: 'Disco sda' } },
      { tool: 'note.get', result: { id: 'abc123' } },
      { tool: 'note.get', result: { id: 'rota' }, failed: true },
      { tool: 'note.save', result: { id: 'nueva' } },
      { tool: 'note.get', result: 'sin forma de nota' },
    ],
  })) as typeof fetch;
  const reply = await createHexosTransport('/bridge/api/', fetcher).send('muéstrame la nota');
  // Solo note.get y note.save, sin repetir, sin las fallidas y sin note.list.
  assert.deepEqual(reply.notes, ['abc123', 'nueva']);
});

test('a turn that touched no note reports none instead of guessing', async () => {
  const fetcher = (async () => Response.json({ reply: 'Hecho', tools: [{ tool: 'nas.read' }] })) as typeof fetch;
  const reply = await createHexosTransport('/bridge/api/', fetcher).send('mira el NAS');
  assert.deepEqual(reply.notes, []);
});

// note.show existe porque el catálogo no tenía ninguna herramienta cuyo efecto
// fuese la pantalla: al pedir «ábrela», Helios solo sabía volcar el texto al chat.
test('note.show opens the note and note.hide closes what it names', async () => {
  const fetcher = (async () => Response.json({
    reply: 'Abierta',
    tools: [{ tool: 'note.show', result: { id: 'abc', title: 'Disco sda', shown: true } }],
  })) as typeof fetch;
  const reply = await createHexosTransport('/bridge/api/', fetcher).send('ábrela');
  assert.deepEqual(reply.notes, ['abc']);
  assert.equal(reply.closeNotes, null);
});

test('closing every note is said once, not by listing them all', async () => {
  const todas = (async () => Response.json({
    reply: 'Recogido', tools: [{ tool: 'note.hide', result: { hidden: 'todas' } }],
  })) as typeof fetch;
  assert.equal((await createHexosTransport('/bridge/api/', todas).send('cierra las notas')).closeNotes, 'todas');

  const una = (async () => Response.json({
    reply: 'Cerrada',
    tools: [{ tool: 'note.hide', result: { hidden: 'abc' } },
            { tool: 'note.hide', result: { hidden: 'rota' }, failed: true }],
  })) as typeof fetch;
  // La fallida no cuenta: cerrar una ventana que sigue ahí confunde más que el error.
  assert.deepEqual((await createHexosTransport('/bridge/api/', una).send('cierra esa')).closeNotes, ['abc']);
});
