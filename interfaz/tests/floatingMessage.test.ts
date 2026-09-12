import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { FloatingMessage, type MessageWindow } from "../components/FloatingMessage";

function render(overrides: Partial<MessageWindow>) {
  return renderToStaticMarkup(createElement(FloatingMessage, {
    message: { id: 1, text: "Mi pregunta", slot: 0, x: 0, y: 0, minimized: false, ...overrides },
    front: true, onMove() {}, onMinimize() {}, onClose() {}, onFocus() {},
  }));
}

test("the window presents the actual reply and keeps the question collapsed", () => {
  const html = render({ reply: "Respuesta real <script>no ejecutar</script>" });
  assert.match(html, /class="helios-answer"/);
  assert.match(html, /Respuesta real &lt;script&gt;no ejecutar&lt;\/script&gt;/);
  assert.match(html, /<details class="original-message"><summary>Tu mensaje<\/summary><p>Mi pregunta<\/p><\/details>/);
  assert.doesNotMatch(html, /<script>|<details[^>]*open|Helios está pensando/);
});

test("pending and failed sends do not manufacture an assistant answer", () => {
  const pending = render({ pending: true });
  assert.match(pending, /Helios está pensando/);
  assert.doesNotMatch(pending, /class="helios-answer"/);
  const failed = render({ error: "No se pudo recibir la respuesta." });
  assert.match(failed, /role="alert"/);
  assert.match(failed, /Mi pregunta/);
  assert.doesNotMatch(failed, /class="helios-answer"/);
});
