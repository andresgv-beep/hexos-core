import assert from 'node:assert/strict';
import test from 'node:test';
import { createHexosTransport } from '../lib/helios/hexos';
import { clampEnergy, phaseFromHexos } from '../lib/helios/state';
import { mergeToolActivities } from '../lib/helios/tools';

test('live status exposes sanitized preview, progress and the exact cancellation target', async () => {
  const status = await createHexosTransport('/api', fixture({ state: 'thinking', mode: 'native-experimental',
    generation: { request_id: 'one', text: 'Hola', phase: 'generating', processed: 512,
      total: 1024, cancellable: true, cancelling: false } })).status();
  assert.deepEqual(status.generation, { requestId: 'one', text: 'Hola', phase: 'generating',
    processed: 512, total: 1024, cancellable: true, cancelling: false });
});

test('identified chat and cancel reach the server without aborting the terminal response', async () => {
  const seen: string[] = [];
  const fetcher = (async (url, init) => {
    seen.push(String(url));
    const body = JSON.parse(String(init?.body));
    assert.equal(body.request_id, 'one');
    return String(url).endsWith('/cancel') ? Response.json({ ok: true })
      : Response.json({ reply: '[Respuesta interrumpida]', tools: [], cancelled: true });
  }) as typeof fetch;
  const transport = createHexosTransport('/api', fetcher);
  assert.equal(await transport.cancel?.('one'), true);
  const result = await transport.send('Hola', undefined, undefined, undefined, undefined, 'one');
  assert.equal(result.cancelled, true);
  assert.deepEqual(seen, ['/api/cancel', '/api/chat']);
});

test('aborting an identified HTTP wait also requests server cancellation', async () => {
  const controller = new AbortController();
  const calls: string[] = [];
  const fetcher = (async (url, init) => {
    calls.push(String(url));
    if (String(url).endsWith('/cancel')) return Response.json({ ok: true });
    return new Promise<Response>((_, reject) => init?.signal?.addEventListener('abort',
      () => reject(new DOMException('Aborted', 'AbortError')), { once: true }));
  }) as typeof fetch;
  const request = createHexosTransport('/api', fetcher).send('Hola', controller.signal,
    undefined, undefined, undefined, 'one');
  controller.abort();
  await assert.rejects(request, { name: 'AbortError' });
  assert.deepEqual(calls, ['/api/chat', '/api/cancel']);
});

function fixture(data: unknown, status = 200) {
  return (async () => Response.json(data, { status })) as typeof fetch;
}
test('an incomplete backend response remains explicitly incomplete in the UI', async () => {
  const result = await createHexosTransport('/api', fixture({
    reply: 'Código parcial', tools: [], incomplete: true,
  })).send('Genera código');
  assert.equal(result.incomplete, true);
});
test('the first keystroke can warm the model without waiting for ready', async () => {
  const seen: { url: string; body: unknown }[] = [];
  const fetcher = (async (url, init) => {
    seen.push({ url: String(url), body: JSON.parse(String(init?.body)) });
    return Response.json({ state: 'loading', ready: false }, { status: 202 });
  }) as typeof fetch;
  assert.equal(await createHexosTransport('/api', fetcher).warmup(), 'loading');
  assert.deepEqual(seen, [{ url: '/api/model/warmup', body: {} }]);
});
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
test('keeps the visible request separate from private code context', async () => {
  const fetcher = (async (_url, init) => {
    assert.deepEqual(JSON.parse(String(init?.body)), {
      text: 'Edita el código completo: const App = () => null',
      thinking: true,
      display_text: 'pon modo oscuro',
    });
    return Response.json({ reply: 'Listo', tools: [] });
  }) as typeof fetch;
  await createHexosTransport('/api', fetcher).send(
    'Edita el código completo: const App = () => null', undefined, undefined, true, 'pon modo oscuro');
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

test('history pages preserve the earlier cursor and validate the response', async () => {
  const urls: string[] = [];
  const fetcher = (async (url) => {
    urls.push(String(url));
    return Response.json({ messages: [{ id: 'old', role: 'user', text: 'Anterior' }], next_before: 40 });
  }) as typeof fetch;
  const transport = createHexosTransport('/api', fetcher);
  assert.deepEqual(await transport.historyPage?.(100), {
    messages: [{ role: 'user', text: 'Anterior' }], nextBefore: 40,
  });
  assert.deepEqual(urls, ['/api/history?limit=100&before=100']);
  for (const data of [ { messages: [], next_before: -1 }, { messages: [{ role: 'system', text: 'x' }], next_before: null } ]) {
    await assert.rejects(createHexosTransport('/api', fixture(data)).historyPage!(), /historial/);
  }
});

test('status tells apart no project, a project, and a HexOS without projects', async () => {
  const base = { state: 'idle', mode: 'native-experimental', window: 'agente' };
  assert.equal((await createHexosTransport('/api', fixture({ ...base, project: 'motor-cuda' })).status()).project, 'motor-cuda');
  assert.equal((await createHexosTransport('/api', fixture({ ...base, project: null })).status()).project, null);
  // Un HexOS anterior no manda el campo: la interfaz no debe enseñar proyectos.
  assert.equal((await createHexosTransport('/api', fixture(base)).status()).project, undefined);
});

test('projects are listed, created and switched through their own routes', async () => {
  const seen: Array<[string, unknown]> = [];
  const fetcher = (async (url, init) => {
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    seen.push([String(url), body]);
    if (String(url).endsWith('/projects') && !body) {
      return Response.json({ active: 'uno', root: '~/Helios/proyectos', projects: [
        { id: 'uno', name: 'Uno', folder: '/home/x/Helios/proyectos/uno', created: 'a', used: 'b' }, { roto: true }] });
    }
    if (String(url).endsWith('/projects')) return Response.json({ active: 'dos', created: {} });
    return Response.json({ active: body.id });
  }) as typeof fetch;
  const transport = createHexosTransport('/api', fetcher);
  assert.deepEqual(await transport.projects?.(), { active: 'uno', root: '~/Helios/proyectos',
    projects: [{ id: 'uno', name: 'Uno', folder: '/home/x/Helios/proyectos/uno', used: 'b' }] });
  assert.equal(await transport.createProject?.('Dos'), 'dos');
  assert.equal(await transport.createProject?.('Tres', ' ~/repo '), 'dos');
  assert.equal(await transport.setProject?.('uno'), 'uno');
  assert.equal(await transport.setProject?.(null), null);
  assert.deepEqual(seen.slice(1), [['/api/projects', { name: 'Dos' }], ['/api/projects', { name: 'Tres', folder: '~/repo' }],
    ['/api/project', { id: 'uno' }], ['/api/project', { id: null }]]);
  await assert.rejects(async () => transport.createProject?.('   '), /nombre/);
});

test('service keys are saved, tested and removed without ever coming back', async () => {
  const seen: Array<[string, unknown]> = [];
  const ajustes = (configured: boolean) => ({ web: { search: configured ? 'Tavily' : 'DuckDuckGo', providers: [
    { id: 'tavily', name: 'Tavily', kind: 'busqueda', site: 'https://app.tavily.com', note: 'Gratis', placeholder: 'tvly-…',
      configured, hint: configured ? '…abcd' : null }, 'basura'] } });
  const fetcher = (async (url, init) => {
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    seen.push([String(url), body]);
    if (String(url).endsWith('/test')) return Response.json({ ok: true, provider: 'tavily', results: 1 });
    return Response.json(ajustes(Boolean(body?.key)));
  }) as typeof fetch;
  const transport = createHexosTransport('/api', fetcher);
  assert.equal((await transport.settings?.())?.web.search, 'DuckDuckGo');
  const guardado = await transport.saveServiceKey?.('tavily', 'tvly-secreta');
  assert.deepEqual(guardado?.web.providers, [{ id: 'tavily', name: 'Tavily', kind: 'busqueda', site: 'https://app.tavily.com',
    note: 'Gratis', placeholder: 'tvly-…', configured: true, hint: '…abcd' }]);
  assert.equal(await transport.testService?.('tavily'), 1);
  assert.equal((await transport.saveServiceKey?.('tavily', null))?.web.providers[0].configured, false);
  assert.deepEqual(seen, [['/api/settings', null], ['/api/settings/web', { provider: 'tavily', key: 'tvly-secreta' }],
    ['/api/settings/web/test', { provider: 'tavily' }], ['/api/settings/web', { provider: 'tavily', key: null }]]);
  await assert.rejects(async () => createHexosTransport('/api', fixture({ web: {} })).settings?.(), /no válidos/);
  await assert.rejects(async () => createHexosTransport('/api', fixture({ error: 'la clave de Tavily no es válida' }, 409))
    .testService?.('tavily'), /no es válida/);
});

test('a proposed download reaches its card and is decided through its own route', async () => {
  const { parseDownloadRequest } = await import('../lib/helios/hexos');
  const manual = { name: 'manual.pdf', host: 'example.com', url: 'https://example.com/manual.pdf', kind: 'PDF', bytes: 2018052,
    requested: 'https://example.com/manual.pdf', content_type: 'application/pdf', summary: 'descargar manual.pdf' };
  const planos = { name: 'planos.zip', host: 'example.org', url: 'https://example.org/planos.zip', kind: 'ZIP', bytes: null };
  const pendiente = { plan_id: 'd1', summary: 'descargar 2 ficheros (tamaño sin declarar): manual.pdf, planos.zip',
    folder: '~/Helios/descargas', items: [manual, planos] };
  assert.deepEqual(parseDownloadRequest(pendiente), { planId: 'd1', summary: pendiente.summary, folder: '~/Helios/descargas',
    items: [{ name: 'manual.pdf', host: 'example.com', url: 'https://example.com/manual.pdf', kind: 'PDF', bytes: 2018052 },
            { name: 'planos.zip', host: 'example.org', url: 'https://example.org/planos.zip', kind: 'ZIP', bytes: null }] });
  // Una lista a medias no se enseña: lo que se aprueba es lo que se ve.
  for (const malo of [null, undefined, 'x', {}, { ...pendiente, plan_id: 7 }, { ...pendiente, items: [] }, { ...pendiente, items: undefined },
                      { ...pendiente, items: [manual, { ...planos, url: undefined }] }, { ...pendiente, items: [manual, 'basura'] }])
    assert.equal(parseDownloadRequest(malo), null);
  const estado = { state: 'idle', mode: 'native-experimental' };
  assert.equal((await createHexosTransport('/api', fixture(estado)).status()).downloadRequest, undefined);
  assert.equal((await createHexosTransport('/api', fixture({ ...estado, download_request: pendiente })).status())
    .downloadRequest?.planId, 'd1');
  const seen: Array<[string, unknown]> = [];
  const fetcher = (async (url, init) => {
    seen.push([String(url), JSON.parse(String(init?.body))]);
    return Response.json({ summary: pendiente.summary, executed: true, verified: false, check: 'x', files: [
      { name: 'manual.pdf', executed: true, verified: true, refused: null, check: '2,0 MB en ~/Helios/descargas/manual.pdf' },
      { name: 'planos.zip', executed: false, verified: false, refused: 'la fuente respondió HTTP 403', check: 'no se ha guardado nada' }, 'basura'] });
  }) as typeof fetch;
  const hecho = await createHexosTransport('/api', fetcher).decideDownload?.('d1', true);
  assert.deepEqual([hecho?.executed, hecho?.verified], [true, false]);
  assert.deepEqual(hecho?.files, [
    { name: 'manual.pdf', executed: true, verified: true, refused: undefined, check: '2,0 MB en ~/Helios/descargas/manual.pdf' },
    { name: 'planos.zip', executed: false, verified: false, refused: 'la fuente respondió HTTP 403', check: 'no se ha guardado nada' }]);
  assert.deepEqual(seen, [['/api/download', { plan_id: 'd1', approve: true }]]);
});

test('the person is told how each downloaded file ended, the failed one by name', async () => {
  const { downloadReply } = await import('../lib/helios/hexos');
  const bien = { name: 'manual.pdf', executed: true, verified: true, check: '2,0 MB en ~/Helios/descargas/manual.pdf' };
  const caido = { name: 'planos.zip', executed: false, verified: false, refused: 'la fuente respondió HTTP 403' };
  const raro = { name: 'foto.png', executed: true, verified: false, check: '1 kB en ~/Helios/descargas/foto.png' };
  const base = { summary: 'descargar…', executed: true, verified: true };
  assert.equal(downloadReply({ ...base, files: [bien] }), 'Descargado y comprobado: 2,0 MB en ~/Helios/descargas/manual.pdf. Lo tienes en Descargas.');
  assert.equal(downloadReply({ ...base, executed: false, files: [caido] }), 'No se descargó: la fuente respondió HTTP 403.');
  assert.match(downloadReply({ ...base, files: [raro] }), /no coincide con lo recibido.*No te fíes/);
  assert.equal(downloadReply({ ...base, files: [bien, { ...bien, name: 'otro.pdf' }] }),
    'Descargados y comprobados los 2 ficheros. Los tienes en Descargas.\n\n- `manual.pdf`: descargado y comprobado\n- `otro.pdf`: descargado y comprobado');
  const mezcla = downloadReply({ ...base, verified: false, files: [bien, caido, raro] });
  assert.match(mezcla, /^Descargados y comprobados 1 de 3 ficheros\./);
  assert.match(mezcla, /- `planos\.zip`: no se descargó: la fuente respondió HTTP 403\n- `foto\.png`: se descargó, pero lo guardado no coincide/);
  assert.match(downloadReply({ ...base, executed: false, verified: false, files: [caido, caido] }), /^No se descargó ninguno de los 2 ficheros\./);
  assert.equal(downloadReply({ summary: 'descargar 2 ficheros', executed: false, cancelled: true, files: [] }),
    'Cancelado: descargar 2 ficheros. No se ha descargado nada.');
});

test('downloaded files are listed and addressed by id, to view or to save', async () => {
  const fila = { id: 'a b/1', name: 'manual.pdf', kind: 'PDF', bytes: 2018052, ts: '2026-11-16T09:21:56+00:00',
    source: 'example.com', url: 'https://example.com/manual.pdf', on_disk: true, viewable: true, readable: true };
  const transport = createHexosTransport('/api/helios', fixture({ folder: '~/Helios/descargas', downloads: [fila, 'basura', { name: 'sin id' }] }));
  assert.deepEqual(await transport.downloads?.(), { folder: '~/Helios/descargas', files: [{ id: 'a b/1', name: 'manual.pdf',
    kind: 'PDF', bytes: 2018052, ts: '2026-11-16T09:21:56+00:00', source: 'example.com', onDisk: true, viewable: true, readable: true, preview: false }] });
  assert.equal(transport.downloadUrl?.('a b/1'), '/api/helios/downloads/a%20b%2F1');
  assert.equal(transport.downloadUrl?.('x', true), '/api/helios/downloads/x/download');
  await assert.rejects(async () => createHexosTransport('/api', fixture({})).downloads?.(), /no válida/);
});

test('pending project changes reach the card only when they are well formed', async () => {
  const { parseProjectChange } = await import('../lib/helios/hexos');
  const fichero = { path: 'src/main.cu', kind: 'edit', added: 1, removed: 1,
    diff: ['@@ -3 +3 @@', '-  return 0;', '+  return 1;', 7], diff_lines: 3 };
  const pendiente = { plan_id: 'p1', summary: '2 ficheros (+3 −1): src/main.cu, README.md', project_name: 'Motor',
    added: 3, removed: 1, changes: [fichero, { path: 'README.md', kind: 'create', added: 2, removed: 0, diff: ['+# Motor'] },
      { path: 'malo.txt', kind: 'delete' }, 'basura'] };
  assert.deepEqual(parseProjectChange(pendiente), { planId: 'p1', summary: '2 ficheros (+3 −1): src/main.cu, README.md',
    projectName: 'Motor', added: 3, removed: 1, changes: [
      { path: 'src/main.cu', kind: 'edit', added: 1, removed: 1, diff: ['@@ -3 +3 @@', '-  return 0;', '+  return 1;'], diffLines: 3 },
      { path: 'README.md', kind: 'create', added: 2, removed: 0, diff: ['+# Motor'], diffLines: 1 }] });
  for (const malo of [null, undefined, 'x', {}, { ...pendiente, changes: [] }, { ...pendiente, plan_id: 7 },
    { ...pendiente, changes: [{ path: 'x', kind: 'delete' }] }])
    assert.equal(parseProjectChange(malo), null);
});

test('a turn keeps every call, also when the same tool runs eight times', async () => {
  const { turnToolActivities } = await import('../lib/helios/tools');
  const lectura = (i: number, status: 'running' | 'done') => ({ id: `${i}-project.read`, name: 'project.read', status, seconds: status === 'done' ? .1 : null });
  let vistas = turnToolActivities([], [lectura(0, 'done'), lectura(1, 'running')]);
  vistas = turnToolActivities(vistas, [0, 1, 2, 3, 4, 5, 6].map(i => lectura(i, 'done')).concat(lectura(7, 'running')));
  assert.equal(vistas.length, 8);
  assert.deepEqual(vistas.map(tool => tool.status), [...Array(7).fill('done'), 'running']);
});

test('documents Helios creates in a turn come with a link to see them and one to save them', async () => {
  const id = 'a'.repeat(32), otro = 'b'.repeat(32);
  const fetcher = (async () => Response.json({ reply: 'Hecho.', tools: [
    { tool: 'document.create', result: { id, name: 'Cuentas.xlsx', kind: 'Excel', bytes: 5361 } },
    { tool: 'document.create', result: { id: otro, name: 'Informe.pdf', kind: 'PDF', bytes: 44839 } },
    { tool: 'document.create', failed: true, result: { error: 'x' } },
    { tool: 'document.create', result: { id: '../x', name: 'malo' } },
    { tool: 'note.save', result: { id: 'c'.repeat(32), name: 'nota' } },
  ] })) as typeof fetch;
  const result = await createHexosTransport('/api/helios', fetcher).send('Hazme un Excel');
  assert.deepEqual(result.documents, [
    { id, name: 'Cuentas.xlsx', kind: 'Excel', bytes: 5361,
      viewUrl: `/api/helios/downloads/${id}/preview`, saveUrl: `/api/helios/downloads/${id}/download` },
    { id: otro, name: 'Informe.pdf', kind: 'PDF', bytes: 44839,
      viewUrl: `/api/helios/downloads/${otro}`, saveUrl: `/api/helios/downloads/${otro}/download` },
  ]);
});

test('a reloaded conversation keeps each reply\'s documents', async () => {
  const id = 'd'.repeat(32);
  const fetcher = (async () => Response.json({ next_before: null, messages: [
    { role: 'user', text: 'hazme un excel' },
    { role: 'assistant', text: 'Aquí lo tienes.', documents: [{ id, name: 'Cuentas.xlsx', kind: 'Excel', bytes: 5361 }] },
    { role: 'assistant', text: 'Otra.', documents: [{ id: '../x', name: 'malo' }] },
  ] })) as typeof fetch;
  const page = await createHexosTransport('/api/helios', fetcher).historyPage!();
  assert.deepEqual(page.messages[1].documents, [{ id, name: 'Cuentas.xlsx', kind: 'Excel', bytes: 5361,
    viewUrl: `/api/helios/downloads/${id}/preview`, saveUrl: `/api/helios/downloads/${id}/download` }]);
  assert.equal(page.messages[0].documents, undefined);
  assert.deepEqual(page.messages[2].documents, []);
});
