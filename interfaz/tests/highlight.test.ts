import assert from "node:assert/strict";
import test from "node:test";
import { highlightCode } from "../lib/helios/highlight";

test("el resaltado JSX conserva exactamente el código original", () => {
  const source = "const Panel = () => <div className=\"bg-blue-500\">{42}</div>;";
  const tokens = highlightCode(source, "jsx");
  assert.equal(tokens.map(token => token.text).join(""), source);
  assert.deepEqual(tokens.find(token => token.text === "const"), { text: "const", kind: "keyword" });
  assert.ok(tokens.some(token => token.text === "div" && token.kind === "tag"));
  assert.ok(tokens.some(token => token.text === "className" && token.kind === "attribute"));
});

test("comentarios, cadenas y números reciben colores distintos", () => {
  const tokens = highlightCode("// estado\nconst total = 12;\nconst nombre = 'Helios';", "js");
  assert.ok(tokens.some(token => token.text === "// estado" && token.kind === "comment"));
  assert.ok(tokens.some(token => token.text === "12" && token.kind === "number"));
  assert.ok(tokens.some(token => token.text === "'Helios'" && token.kind === "string"));
});
