import assert from "node:assert/strict";
import test from "node:test";
import { inlines, parseReply, regroup, tokenize } from "../lib/helios/markdown";

test("el código progresivo conserva espacios y líneas sin revelar líneas enteras de golpe", () => {
  const source = '  const mensaje = "hola 🌍";\n\n    console.log(mensaje);';
  const tokens = tokenize(parseReply('```js\n' + source));
  assert.ok(tokens.every(token => Array.from(token.text).length <= 4));
  const restored = regroup(tokens)[0].lines.map(line => line.parts.map(part => part.text).join('')).join('\n');
  assert.equal(restored, source);
  const before = tokenize(parseReply('```js\nconst mensaje'));
  const after = tokenize(parseReply('```js\nconst mensaje = "más contenido que llega después";'));
  assert.deepEqual(after.slice(0, before.length - 1), before.slice(0, -1));
  assert.ok(after.length > before.length + 3);
});

test("un listado de vecinos sale como lista, no como párrafo", () => {
  // Salida real de Helios, 14/09/2026.
  const bloques = parseReply(
    "Aquí tienes la lista de vecinos sin nombre registrado:\n" +
    "* **192.168.1.203** (MAC: 6c:1f:f7:92:98:0f)\n" +
    "* **192.168.1.129** (MAC: fe:b1:96:7c:78:9f)");
  assert.deepEqual(bloques.map(b => b.kind), ["p", "ul"]);
  assert.equal(bloques[1].lines.length, 2);
  assert.deepEqual(bloques[1].lines[0][0], { text: "192.168.1.203", bold: true });
});

test("las listas numeradas no se mezclan con las de viñeta", () => {
  const bloques = parseReply("1. Primero\n2. Segundo\n* Otra cosa");
  assert.deepEqual(bloques.map(b => b.kind), ["ol", "ul"]);
  assert.equal(bloques[0].lines.length, 2);
});

test("negrita y código dentro de una línea", () => {
  assert.deepEqual(inlines("El disco `sda` está **mal**"), [
    { text: "El disco " }, { text: "sda", code: true },
    { text: " está " }, { text: "mal", bold: true },
  ]);
});

test("un asterisco suelto es un asterisco y no rompe nada", () => {
  assert.deepEqual(inlines("2 * 3 = 6"), [{ text: "2 * 3 = 6" }]);
});

test("las líneas seguidas forman un párrafo y la línea en blanco lo cierra", () => {
  const bloques = parseReply("Una frase\ny su continuación.\n\nOtro párrafo.");
  assert.equal(bloques.length, 2);
  assert.equal(bloques[0].lines[0][0].text, "Una frase y su continuación.");
});

test("el revelado avanza por palabras sin perder a qué lista pertenecen", () => {
  const tokens = tokenize(parseReply("Vecinos:\n* Uno\n* Dos"));
  const mitad = regroup(tokens.slice(0, tokens.findIndex(t => t.text === "Dos")));
  assert.deepEqual(mitad.map(b => b.index), [0, 1]);
  // Y conserva QUÉ es cada bloque: sin esto la lista se pintaba como párrafo.
  assert.deepEqual(mitad.map(b => b.kind), ["p", "ul"]);
  // La segunda viñeta todavía no está, y la primera no se ha mezclado con ella.
  assert.equal(mitad[1].lines.length, 1);
  assert.equal(mitad[1].lines[0].parts.map(p => p.text).join(""), "Uno");
});

test("un texto sin marcas sigue siendo un párrafo", () => {
  const bloques = parseReply("Hola.");
  assert.deepEqual(bloques, [{ kind: "p", lines: [[{ text: "Hola." }]] }]);
});

test("un bloque cercado conserva lenguaje, saltos y código JSX", () => {
  const bloques = parseReply("Aquí va:\n```jsx\n<div className=\"panel\">\n  Hola\n</div>\n```\nFin.");
  assert.deepEqual(bloques.map(b => b.kind), ["p", "code", "p"]);
  assert.equal(bloques[1].language, "jsx");
  assert.equal(bloques[1].lines.map(linea => linea[0].text).join("\n"), '<div className="panel">\n  Hola\n</div>');
});

test("un bloque cortado sin cerca final no se mezcla con el párrafo", () => {
  const bloques = parseReply("```tsx\nconst listo = true;");
  assert.equal(bloques.length, 1);
  assert.equal(bloques[0].kind, "code");
  assert.equal(bloques[0].lines[0][0].text, "const listo = true;");
});
