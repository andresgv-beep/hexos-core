import test from "node:test";
import assert from "node:assert/strict";
import { PREVIEW_DESIGN_WIDTH, previewScale } from "../components/PreviewFrame";

test("la maqueta se reduce entera en paneles estrechos y no se amplía en anchos", () => {
  assert.equal(previewScale(550), 550 / PREVIEW_DESIGN_WIDTH);
  assert.equal(previewScale(PREVIEW_DESIGN_WIDTH), 1);
  assert.equal(previewScale(1900), 1);
  assert.equal(previewScale(0), 1);   // antes de medir, tamaño natural
});
