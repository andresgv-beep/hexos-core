import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatHistory } from "../components/ChatHistory";

test("history includes earlier messages and absorbed replies while a new answer is pending", () => {
  const html = renderToStaticMarkup(createElement(ChatHistory, {
    previous: [{ role: "user", text: "Pregunta anterior" }, { role: "assistant", text: "Respuesta anterior" }],
    messages: [
      { id: 1, text: "Pregunta absorbida", reply: "Respuesta conservada" },
      { id: 2, text: "Nueva pregunta", pending: true },
    ],
    historyError: "", onClose() {}, onOpenArtifact() {},
  }));
  for (const text of ["Pregunta anterior", "Respuesta anterior", "Pregunta absorbida", "Respuesta conservada", "Nueva pregunta", "Helios está pensando", "Cerrar historial y seguir conversando"]) assert.ok(html.includes(text));
});

test("history keeps generated code outside the conversation and can reopen it", () => {
  const html = renderToStaticMarkup(createElement(ChatHistory, {
    previous: [{ role: "assistant", text: "Aquí tienes la propuesta.\n```tsx\nconst SecretPanel = () => <main />;\n```" }],
    messages: [], historyError: "", onClose() {}, onOpenArtifact() {},
  }));
  assert.match(html, /Aquí tienes la propuesta\./);
  assert.match(html, /Abrir implementación/);
  assert.doesNotMatch(html, /SecretPanel|class="reply-code"/);
});
