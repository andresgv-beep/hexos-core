import assert from 'node:assert/strict';
import test from 'node:test';

test('serves the HUD shell with existing controls and no orb', async () => {
  const { default: worker } = await import('../dist/server/index.js');
  const response = await worker.fetch(new Request('http://localhost/', { headers: { accept: 'text/html' } }), {
    ASSETS: { fetch: async () => new Response('Not found', { status: 404 }) },
  }, { waitUntil() {}, passThroughOnException() {} });
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /<html lang="es"/);
  assert.match(html, /Helios · Espacio de trabajo/);
  // Las ventanas ya no son la conversación: son notas e informes. El chat vive en
  // la columna y no aparece en el HTML inicial porque todavía no hay turno.
  assert.match(html, /Notas e informes abiertos/);
  assert.match(html, /Favoritos del núcleo/);
  assert.match(html, /Mensaje para Helios/);
  assert.match(html, /Conectando con Helios/);
  assert.match(html, /Historial/);
  assert.match(html, /Contenido y actividad/);
  assert.doesNotMatch(html, /Ajustar luminosidad|nebula-orb|orb-history-trigger/);
  assert.doesNotMatch(html, /Todo empieza contigo|Probar estados|UN ESPACIO PARA CONVERSAR|HECHO DE CONEXIONES/);
  assert.doesNotMatch(html, /Pausar movimiento|Probar conversación|PRUEBA VISUAL/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Your site is taking shape/);
  // Sin turno no se fabrica una respuesta ni el hueco de la conversación.
  assert.doesNotMatch(html, /conversation-stream|helios-answer/);
});
