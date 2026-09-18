import assert from "node:assert/strict";
import test from "node:test";
import { extractHtmlPreview, extractReplyArtifact, previewDocument } from "../lib/helios/preview";

test("extrae la última maqueta HTML de una respuesta con varios bloques", () => {
  const html = extractHtmlPreview("```jsx\n<App />\n```\n```html\n<main>Vista</main>\n```");
  assert.equal(html, "<main>Vista</main>");
});

test("la vista queda sin red, formularios ni acceso al origen", () => {
  const doc = previewDocument("<button>Probar</button>");
  assert.match(doc, /default-src 'none'/);
  assert.match(doc, /connect-src 'none'/);
  assert.match(doc, /form-action 'none'/);
  assert.match(doc, /<button>Probar<\/button>/);
});

test("separa conversación, código principal y maqueta", () => {
  const result = extractReplyArtifact("He corregido dos problemas.\n\n```tsx\nexport const App = () => <main />;\n```\n\n```html\n<main>Vista</main>\n```");
  assert.equal(result?.reply, "He corregido dos problemas.");
  assert.equal(result?.language, "tsx");
  assert.equal(result?.code, "export const App = () => <main />;");
  assert.equal(result?.previewHtml, "<main>Vista</main>");
});
