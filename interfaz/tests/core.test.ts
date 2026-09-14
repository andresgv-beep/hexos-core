import assert from 'node:assert/strict';
import test from 'node:test';
import { coreSectionForTools, createCoreClient, noteAsMarkdown, noteFilename } from '../lib/helios/core';

function fixture(data: unknown, status = 200) {
  return (async () => Response.json(data, { status })) as typeof fetch;
}

test('un total que no se pudo contar llega como null, no como cero', async () => {
  const overview = await createCoreClient('/api', fixture({
    sections: [{ key: 'notas', label: 'Notas', total: 3, pending: 1, tool: 'note.list' },
               { key: 'perfil', label: 'Perfil', total: null, unknown: 'hera no responde', tool: 'x' }],
    favorites: [], note: 'No incluye archivos del NAS.',
  })).overview();
  assert.equal(overview.sections[0].total, 3);
  assert.equal(overview.sections[0].pending, 1);
  // Cero diría «no tiene hechos». null dice «no se pudo saber», que es otra cosa.
  assert.equal(overview.sections[1].total, null);
  assert.equal(overview.sections[1].unknown, 'hera no responde');
});

test('los favoritos llegan con lo justo para pintar la tira', async () => {
  const overview = await createCoreClient('/api', fixture({
    sections: [], favorites: [{ kind: 'nota', id: 'a1', title: 'Cable de sda', state: 'pendiente', updated_at: '2026-09-14' }], note: '',
  })).overview();
  assert.deepEqual(overview.favorites, [{ kind: 'nota', id: 'a1', title: 'Cable de sda', state: 'pendiente', updatedAt: '2026-09-14' }]);
});

test('una fila de nota sin id se descarta en vez de pintarse a medias', async () => {
  const notes = await createCoreClient('/api', fixture([
    { id: 'a1', title: 'Una', body: 'x', state: 'pendiente', favorite: true, tags: ['casa'], updated_at: 't', revision: 2, truncated: true },
    { title: 'Sin id' },
  ])).notes();
  assert.equal(notes.length, 1);
  assert.equal(notes[0].favorite, true);
  assert.deepEqual(notes[0].tags, ['casa']);
});

test('un error del servidor llega con su motivo', async () => {
  await assert.rejects(createCoreClient('/api', fixture({ error: 'nota inexistente' }, 404)).note('x'),
                       /nota inexistente/);
});

test('el núcleo se abre por lo que se ejecutó, no por lo que se dijo', () => {
  assert.equal(coreSectionForTools([{ name: 'note.save' }]), 'notas');
  assert.equal(coreSectionForTools([{ name: 'core.overview' }]), '');
  assert.equal(coreSectionForTools([{ name: 'report.list' }]), 'informes');
  // Un turno que no tocó lo guardado no abre nada, diga lo que diga la respuesta.
  assert.equal(coreSectionForTools([{ name: 'nas.read' }, { name: 'network.local' }]), null);
  assert.equal(coreSectionForTools([]), null);
  // Manda la última que tocó el núcleo: es donde acabó el turno.
  assert.equal(coreSectionForTools([{ name: 'note.list' }, { name: 'work.list' }]), 'fichas');
});

test('la nota se descarga como documento sin perder nada', () => {
  const md = noteAsMarkdown({ title: 'Cable de sda', body: 'Línea uno\nLínea dos', state: 'pendiente', tags: ['nas'], updatedAt: '2026-09-14T10:00:00Z' });
  assert.match(md, /^# Cable de sda/);
  assert.match(md, /Estado: pendiente/);
  assert.match(md, /Etiquetas: nas/);
  assert.match(md, /Línea uno\nLínea dos/);
});

test('el nombre de archivo sale del título sin acentos ni sorpresas', () => {
  assert.equal(noteFilename('Revisión del NAS: /volume1'), 'revision-del-nas-volume1.md');
  assert.equal(noteFilename('  '), 'nota.md');
  assert.equal(noteFilename('¿?¡!'), 'nota.md');
});
