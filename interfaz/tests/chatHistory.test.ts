import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatHistory } from "../components/ChatHistory";

test("history includes earlier messages and absorbed replies while a new answer is pending", () => {
  const html = renderToStaticMarkup(createElement(ChatHistory, {
    previous: [{ role: "user", text: "Pregunta anterior" }, { role: "assistant", text: "Respuesta anterior" }],
    messages: [
      { id: 1, text: "Pregunta absorbida", reply: "Respuesta conservada", minimized: true, slot: 0, x: 0, y: 0 },
      { id: 2, text: "Nueva pregunta", pending: true, minimized: false, slot: 1, x: 0, y: 0 },
    ],
    historyError: "", onClose() {},
  }));
  for (const text of ["Pregunta anterior", "Respuesta anterior", "Pregunta absorbida", "Respuesta conservada", "Nueva pregunta", "Helios está pensando", "Cerrar historial y seguir conversando"]) assert.ok(html.includes(text));
});
