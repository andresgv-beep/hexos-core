import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MediaCard } from '../components/MediaCard';
import { createMediaClient, parseMediaJobs, remaining } from '../lib/helios/media';

const running = { id: 'j1', batch_id: 'b1', title: 'Parque Jurásico 3', state: 'running', label: 'Convirtiendo',
  paused: false, updated_at: 1, percent: 64.2, eta_seconds: 720, size_before_gb: 21.9, estimated_gb: 7.1 };

test('only well-formed jobs reach the card', () => {
  const jobs = parseMediaJobs({ jobs: [running, { id: 'x' }, null, { ...running, id: 'j2', percent: 'mucho' }] });
  assert.equal(jobs.length, 2);
  assert.equal(jobs[0].batchId, 'b1');
  assert.equal(jobs[1].percent, undefined);
  assert.deepEqual(parseMediaJobs('nada'), []);
});

test('a converting film shows progress, sizes, time left and queue controls', () => {
  const html = renderToStaticMarkup(createElement(MediaCard, { jobs: parseMediaJobs({ jobs: [running] }), onControl: async () => {} }));
  assert.match(html, /Parque Jurásico 3/);
  assert.match(html, /Convirtiendo · 64 %/);
  assert.match(html, /aria-valuenow="64"/);
  assert.match(html, /21,9 GB/);
  assert.match(html, /~7,1 GB/);
  assert.match(html, /12 min/);
  assert.match(html, /Pausar la cola/);
  assert.match(html, /Cancelar/);
});

test('pausing is told as the queue, not the running film', () => {
  const html = renderToStaticMarkup(createElement(MediaCard, { jobs: parseMediaJobs({ jobs: [{ ...running, paused: true }] }), onControl: async () => {} }));
  assert.match(html, /Convirtiendo · cola en pausa/);
  assert.match(html, /Reanudar la cola/);
});

test('a finished film has its result and no controls', () => {
  const html = renderToStaticMarkup(createElement(MediaCard, { jobs: parseMediaJobs({ jobs: [{ ...running, state: 'completed',
    label: 'Terminada', percent: 100, eta_seconds: undefined, estimated_gb: undefined, size_after_gb: 7.2 }] }), onControl: async () => {} }));
  assert.match(html, /Después/);
  assert.match(html, /7,2 GB/);
  assert.doesNotMatch(html, /<button/);
});

test('controls post the batch and the operation only', async () => {
  const calls: [string, RequestInit | undefined][] = [];
  const client = createMediaClient('/api/helios', (async (url: string, init?: RequestInit) => {
    calls.push([url, init]);
    return new Response(JSON.stringify({ jobs: [] }), { status: 200 });
  }) as typeof fetch);
  await client.control('b1', 'pause');
  assert.equal(calls[0][0], '/api/helios/media/control');
  assert.deepEqual(JSON.parse(String(calls[0][1]?.body)), { batch_id: 'b1', operation: 'pause' });
});

test('time left reads in minutes and hours', () => {
  assert.equal(remaining(20), '1 min');
  assert.equal(remaining(720), '12 min');
  assert.equal(remaining(3900), '1 h 05 min');
});

test('the tasks panel splits what runs from what finished, and says when there is nothing', async () => {
  const { TasksPanel } = await import('../components/TasksPanel');
  const jobs = parseMediaJobs({ jobs: [running, { ...running, id: 'j2', batch_id: 'b2', title: 'Las dos Torres', state: 'completed', label: 'Terminada' }] });
  const html = renderToStaticMarkup(createElement(TasksPanel, { media: jobs, onControl: async () => {}, onClose() {} }));
  assert.match(html, /1 en curso/);
  assert.ok(html.indexOf('En curso') < html.indexOf('Parque Jurásico 3'));
  assert.ok(html.indexOf('Recientes') < html.indexOf('Las dos Torres'));
  const empty = renderToStaticMarkup(createElement(TasksPanel, { media: [], onControl: async () => {}, onClose() {} }));
  assert.match(empty, /No hay tareas en segundo plano/);
});
