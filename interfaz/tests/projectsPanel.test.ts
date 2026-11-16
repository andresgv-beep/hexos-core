import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { NewProjectForm, ProjectsPanel, carpetaPropuesta } from '../components/ProjectsPanel';

const proyectos = [{ id: 'calc', name: 'calculadora v2', folder: '/home/x/Helios/proyectos/calculadora-v2', used: 'b' }];
const nada = async () => true;

test('the projects panel offers a new project from a + in its heading, not from a form of its own', () => {
  for (const fixed of [true, false]) {
    const html = renderToStaticMarkup(createElement(ProjectsPanel, { projects: proyectos, active: 'calc', busy: false, error: '',
      fixed, onSelect() {}, onCreate: nada }));
    assert.match(html, /<button[^>]*class="vision-project-add"[^>]*aria-label="Proyecto nuevo"[^>]*aria-haspopup="dialog"/);
    assert.ok(!html.includes('<form'), 'the name and folder fields only exist while a project is being created');
    assert.ok(!html.includes('Carpeta') && !html.includes('role="dialog" aria-modal'));
    assert.ok(html.includes('calculadora v2') && html.includes('Sin proyecto'));
  }
  const ocupado = renderToStaticMarkup(createElement(ProjectsPanel, { projects: proyectos, active: null, busy: true,
    error: 'ya hay un proyecto con ese nombre', onSelect() {}, onCreate: nada }));
  assert.match(ocupado, /class="vision-project-add"[^>]*disabled=""/);
  assert.ok(ocupado.includes('ya hay un proyecto con ese nombre'), 'an error from the list still shows in the panel');
});

test('the new project window asks for the name and shows where the folder will go', () => {
  const html = renderToStaticMarkup(createElement(NewProjectForm, { root: '~/Helios/proyectos', busy: false,
    error: 'un error de antes', onCreate: nada, onClose() {} }));
  assert.match(html, /role="dialog" aria-modal="true" aria-labelledby="project-new-title"/);
  for (const texto of ['Proyecto nuevo', 'Nombre', 'Carpeta', '~/Helios/proyectos/…', 'Cancelar', 'Crear proyecto'])
    assert.ok(html.includes(texto), texto);
  assert.match(html, /<button type="submit"[^>]*disabled=""/, 'nothing to create without a name');
  assert.ok(!html.includes('un error de antes'), 'an earlier error is not this attempt\'s');
});

test('the proposed folder follows the same rule HexOS uses for the name', () => {
  assert.equal(carpetaPropuesta('~/Helios/proyectos', 'Calculadora v2'), '~/Helios/proyectos/calculadora-v2');
  assert.equal(carpetaPropuesta('~/Helios/proyectos', '  Diseño  Ñandú!! '), '~/Helios/proyectos/diseno-nandu');
  assert.equal(carpetaPropuesta('~/Helios/proyectos', '   '), '');
  assert.equal(carpetaPropuesta('~/Helios/proyectos', '¿¡!?'), '');
});
