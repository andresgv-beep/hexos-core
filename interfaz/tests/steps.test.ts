import assert from 'node:assert/strict';
import test from 'node:test';
import { addStep, isNewGeneration, stepFromDiscarded } from '../lib/helios/steps';

test('live text that only grows is the same generation; a restart is a new one', () => {
  const primero = 'Para que la interfaz sea realmente moderna voy a aplicar';
  assert.equal(isNewGeneration(primero, primero + ' las técnicas de ttk'), false);
  assert.equal(isNewGeneration(primero, ''), true);
  assert.equal(isNewGeneration(primero, 'He propuesto el cambio en gui.py'), true);
  assert.equal(isNewGeneration('', 'Hola'), false);
  assert.equal(isNewGeneration('Vale.', ''), false);
});

test('discarded text stays as one step line, without code or markup', () => {
  assert.equal(stepFromDiscarded('Para que sea **moderna** voy a aplicar las técnicas de `ttk`. Mi plan es este:\n1. Uno'),
    'Para que sea moderna voy a aplicar las técnicas de ttk.');
  assert.equal(stepFromDiscarded('He analizado la imagen y tienes razón:\n```python\nx = 1\n```'), 'He analizado la imagen y tienes razón…');
  assert.equal(stepFromDiscarded('```python\nprint(1)\n```'), '');
  assert.equal(stepFromDiscarded('<|channel>thought<tool_call|>'), '');
  const largo = stepFromDiscarded('palabra '.repeat(80));
  assert.ok(largo.length <= 160 && largo.endsWith('…'));
});

test('the same notice is not listed twice when it arrives both live and as an announcement', () => {
  let pasos = addStep(undefined, 'Voy a leer el contenido de main.py.');
  pasos = addStep(pasos, 'Voy a leer el contenido de main.py');
  pasos = addStep(pasos, '');
  pasos = addStep(pasos, 'Voy a ejecutar el programa.');
  assert.deepEqual(pasos, ['Voy a leer el contenido de main.py.', 'Voy a ejecutar el programa.']);
});
