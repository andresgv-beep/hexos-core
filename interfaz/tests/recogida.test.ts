import assert from 'node:assert/strict';
import test from 'node:test';
import { esCorteDeRed, recogerRespuesta } from '../lib/helios/recogida';
import type { HeliosTransport, HistoryMessage } from '../lib/helios/hexos';

function transporte(fases: string[], mensajes: HistoryMessage[], { sinRed = 0 } = {}) {
  let consultas = 0;
  return { consultas: () => consultas, t: {
    async status() {
      consultas++;
      if (consultas <= sinRed) throw new TypeError('Load failed');
      return { phase: fases.shift() ?? 'idle' };
    },
    async historyPage() { return { messages: mensajes, nextBefore: null }; },
  } as unknown as HeliosTransport };
}
const sinEsperar = { esperar: async () => {} };

test('a network cut is told apart from an error HexOS reports', () => {
  assert.equal(esCorteDeRed(new TypeError('Load failed')), true);            // Safari y Chrome en iPhone
  assert.equal(esCorteDeRed(new TypeError('Failed to fetch')), true);        // Chrome
  assert.equal(esCorteDeRed(new TypeError('NetworkError when attempting to fetch resource.')), true);
  assert.equal(esCorteDeRed(new Error('Helios está ocupado')), false);
  assert.equal(esCorteDeRed(new TypeError('x is not a function')), false);
});

test('after a cut, the reply is collected once Helios finishes on the PC', async () => {
  const respuesta = { role: 'assistant' as const, text: '¡Hecho! Ya tienes tu Excel.', documents: [] };
  const { t, consultas } = transporte(['responding', 'tool', 'idle'],
    [{ role: 'user', text: 'Venga un Excel ahora a ver qué eres capaz' }, respuesta], { sinRed: 2 });
  assert.deepEqual(await recogerRespuesta(t, 'Venga un Excel ahora a ver qué eres capaz', sinEsperar), respuesta);
  assert.equal(consultas(), 5);
});

test('a reply to another question is not passed off as this one', async () => {
  const { t } = transporte([], [{ role: 'user', text: 'otra cosa' }, { role: 'assistant', text: 'Respuesta a otra cosa' }]);
  assert.equal(await recogerRespuesta(t, 'Venga un Excel', sinEsperar), null);
  const { t: sinRespuesta } = transporte([], [{ role: 'user', text: 'Venga un Excel' }]);
  assert.equal(await recogerRespuesta(sinRespuesta, 'Venga un Excel', sinEsperar), null);
});
