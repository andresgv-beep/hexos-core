import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ConversationStream, type Turn } from "../components/ConversationStream";
import { ReplyMarkdown } from "../components/ReplyMarkdown";
import { CodeWorkspace } from "../components/CodeWorkspace";

test("el espacio de código ofrece maximizar sin cambiar el artefacto", () => {
  const html = renderToStaticMarkup(createElement(CodeWorkspace, {
    artifact: { reply: '', code: '<main>Actual</main>', language: 'html' },
    busy: false, canUndo: false, onUndo() {}, onClose() {}, onCreatePreview() {},
  }));
  assert.match(html, /Maximizar implementación/);
  assert.match(html, /Actual/);
});

function render(turn: Partial<Turn>) {
  return renderToStaticMarkup(createElement(ConversationStream, {
    turn: { id: 1, text: "Mi pregunta", ...turn },
  }));
}

test("la columna enseña la respuesta real y conserva la pregunta", () => {
  const html = render({ reply: "Respuesta real <script>no ejecutar</script>" });
  assert.match(html, /class="helios-answer"/);
  assert.match(html, /Respuesta real &lt;script&gt;no ejecutar&lt;\/script&gt;/);
  assert.match(html, /Mi pregunta/);
  assert.doesNotMatch(html, /<script>|Helios está pensando/);
});

test("un envío en curso o fallido no fabrica una respuesta", () => {
  const pendiente = render({ pending: true });
  assert.match(pendiente, /Helios está pensando/);
  assert.doesNotMatch(pendiente, /class="helios-answer"/);
  const fallido = render({ error: "No se pudo recibir la respuesta." });
  assert.match(fallido, /role="alert"/);
  assert.match(fallido, /Mi pregunta/);
  assert.doesNotMatch(fallido, /class="helios-answer"/);
});

test("mientras trabaja, enseña lo que él anuncia", () => {
  const html = render({ pending: true, progress: ["Voy a consultar el NAS.", "Ahora los contenedores."] });
  assert.match(html, /Voy a consultar el NAS\./);
  assert.match(html, /Helios está en ello/);
});

test("el texto progresivo pasa por el revelador y no aparece en ráfagas crudas", () => {
  const html = render({ pending: true, preview: "Primera ráfaga recibida", streamed: true });
  assert.match(html, /aria-label="Respuesta en generación"/);
  assert.match(html, /class="sr-only">Primera ráfaga recibida/);
  // Mientras llega texto nada entra ni sale alrededor: ni «Mostrar todo» ni la línea de estado.
  assert.doesNotMatch(html, /class="reveal-all"/);
  assert.doesNotMatch(html, /role="status"/);
});

test("antes del primer texto se ve el estado; con la respuesta entera se ofrece mostrarla toda", () => {
  assert.match(render({ pending: true, generationStatus: "Leyendo contexto…" }), /Leyendo contexto…/);
  assert.match(render({ reply: "Respuesta completa ya recibida del todo" }), /class="reveal-all"/);
});

test("el reparo viaja pegado a la respuesta, no se pierde en la mudanza", () => {
  const html = render({ reply: "Lo he guardado.", caveat: { note: "No consta ninguna escritura.", tools: ["nas.read"] } });
  assert.match(html, /role="note"/);
  assert.match(html, /No consta ninguna escritura\./);
  assert.match(html, /Sin comprobar: nas\.read\./);
});

test("sin turno no se pinta nada", () => {
  assert.equal(renderToStaticMarkup(createElement(ConversationStream, { turn: null })), "");
});

test("el código cercado se pinta como bloque y nunca como HTML ejecutable", () => {
  const html = renderToStaticMarkup(createElement(ReplyMarkdown, { text: "```jsx\n<script>alert(1)</script>\n```" }));
  assert.match(html, /class="reply-code"/);
  assert.match(html, /class="syntax-tag"/);
  assert.match(html, /&lt;/);
  assert.match(html, /script/);
  assert.match(html, />jsx</);
  assert.doesNotMatch(html, /<script>/);
});

test("un bloque de código ofrece la vista, sin un «Mejorar» sin intención", () => {
  const html = renderToStaticMarkup(createElement(ReplyMarkdown, {
    text: "```jsx\n<App />\n```", onPreviewCode() {},
  }));
  assert.doesNotMatch(html, />Mejorar</);
  assert.match(html, />Crear vista</);
});

test("el código y la interfaz comparten una ventana con dos modos", () => {
  const html = renderToStaticMarkup(createElement(CodeWorkspace, {
    artifact: { reply: "Listo", code: "<h1>Panel</h1>", language: "html", previewHtml: "<h1>Panel</h1>" },
    busy: false, canUndo: true, onUndo() {}, onClose() {}, onCreatePreview() {},
  }));
  assert.match(html, /sandbox="allow-scripts"/);
  assert.match(html, /Mover espacio de código con las flechas/);
  assert.match(html, /> Código</);
  assert.match(html, /> Interfaz</);
  assert.match(html, /Vista previa de la interfaz generada/);
  assert.match(html, /Deshacer<\/button>/);
  assert.doesNotMatch(html, /allow-same-origin|allow-forms/);
});
