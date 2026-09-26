import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { previewDocument } from "../lib/helios/preview";
import { compileTailwind, inlineTailwind, tailwindCandidates, usesTailwindCdn } from "../lib/helios/tailwindPreview";

const stylesheet = readFileSync("node_modules/tailwindcss/index.css", "utf8");
// Lo que Helios escribió de verdad: CDN de Tailwind, clases con variantes y opacidad.
const page = `<!DOCTYPE html>
<html lang="es" class="bg-zinc-950 text-zinc-200">
<head>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>tailwind.config = { theme: { extend: {} } }</script>
</head>
<body class="h-screen flex flex-col">
  <header class="h-12 border-b border-zinc-800 px-4 hover:bg-zinc-800 md:w-64 bg-blue-500/20">HELIOS_OS</header>
  <script>document.body.classList.add('tracking-tighter')</script>
</body>
</html>`;

test("detecta el CDN de Tailwind y solo ese", () => {
  assert.equal(usesTailwindCdn(page), true);
  assert.equal(usesTailwindCdn('<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>'), true);
  assert.equal(usesTailwindCdn('<div class="flex"></div>'), false);
  assert.equal(usesTailwindCdn('<script src="https://example.com/app.js"></script>'), false);
});

test("compila las clases de la página, también las que pone su script", async () => {
  assert.ok(tailwindCandidates(page).includes("hover:bg-zinc-800"));
  const css = await compileTailwind(page, stylesheet);
  for (const rule of [".bg-zinc-950", ".flex-col", ".border-zinc-800", "hover\\:bg-zinc-800", "md\\:w-64", ".tracking-tighter"]) {
    assert.ok(css.includes(rule), `falta ${rule}`);
  }
  assert.match(css, /--color-zinc-950:/);
});

test("sustituye el CDN por el CSS dentro del documento, con la CSP intacta", async () => {
  const css = await compileTailwind(page, stylesheet);
  const document = previewDocument(inlineTailwind(page, css));
  assert.equal(usesTailwindCdn(document), false);
  assert.doesNotMatch(document, /tailwind\.config/);
  assert.equal((document.match(/data-helios-tailwind/g) ?? []).length, 1);
  assert.match(document, /Content-Security-Policy[^>]*default-src 'none'/);
  // Una página sin CDN recibe el CSS igualmente, delante.
  assert.match(inlineTailwind("<p class='flex'></p>", ".flex{}"), /^<style data-helios-tailwind>/);
});
