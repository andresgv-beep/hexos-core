import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ContinuousChat } from '../components/ContinuousChat';

test('continuous chat retains saved history and every session turn including failures', () => {
  const html = renderToStaticMarkup(createElement(ContinuousChat, {
    previous: [{role: 'user', text: 'Mensaje guardado'}],
    turns: [
      {id: 1, text: 'Primera pregunta', reply: 'Primera respuesta'},
      {id: 2, text: 'Segunda pregunta', error: 'Error de conexión'},
      {id: 3, text: 'Tercera pregunta', pending: true},
    ], historyError: '', hasEarlier: true, olderLoading: false,
    onLoadEarlier: async () => {}, onReplyComplete() {},
  }));
  for (const text of ['Mensaje guardado', 'Primera pregunta', 'Primera respuesta', 'Segunda pregunta', 'Error de conexión', 'Tercera pregunta', 'Cargar mensajes anteriores']) assert.ok(html.includes(text), text);
  assert.doesNotMatch(html, /stream-turn leaving/);
});
