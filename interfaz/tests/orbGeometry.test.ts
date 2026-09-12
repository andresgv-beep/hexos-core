import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createOrbGeometry, createOrbitGeometry } from "../components/orb/geometry";

test("builds the denser reference-inspired geometry", () => {
  const geometry = createOrbGeometry();
  const orbit = createOrbitGeometry(0);
  assert.equal(geometry.points.instanceCount, 4200);
  assert.equal(geometry.comets.instanceCount, 576);
  assert.ok(geometry.lines.getAttribute("position").count > 14000);
  assert.equal(orbit.points.instanceCount, 760);
  assert.equal(orbit.line.getAttribute("position").count, 761);
  geometry.points.dispose(); geometry.lines.dispose(); geometry.comets.dispose();
  orbit.points.dispose(); orbit.line.dispose();
});

test("bounds the restored bloom and animation cost", async () => {
  const [orb, bloom] = await Promise.all([
    readFile(new URL("../components/orb/HeliosOrb.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/orb/Bloom.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(orb, /MAX_FPS = 30/);
  assert.match(orb, /frameloop="demand"/);
  assert.match(orb, /dpr=\{2\}/);
  assert.match(orb, /<Bloom \/>/);
  assert.match(bloom, /new EffectComposer\(gl\)/);
  assert.match(bloom, /setPixelRatio\(viewport\.dpr\)/);
  assert.doesNotMatch(bloom, /WebGLRenderTarget|samples:|maxSamples/);
});

// The bug behind both the white-out and the vanished stars: three gives each
// ShaderMaterial its own copy of the `uniforms` object, so driving them through
// a single material's ref left points, comets and orbits frozen at their initial
// values — uViewportHeight stuck at 1 turned every sprite into a screen-sized quad.
test("every material is driven, not just the one behind a ref", async () => {
  const orb = await readFile(new URL("../components/orb/HeliosOrb.tsx", import.meta.url), "utf8");
  const declared = orb.match(/<shaderMaterial/g) ?? [];
  const bound = orb.match(/<shaderMaterial ref=\{bindMaterial\}/g) ?? [];
  assert.ok(declared.length >= 5);
  assert.equal(bound.length, declared.length);
  assert.match(orb, /for \(const instance of materials\.current\)/);
  assert.doesNotMatch(orb, /materialRef/);
});

// Additive light on a transparent canvas: a constant alpha of 1 saturates
// wherever anything draws, painting an opaque near-black patch over the page.
test("emitted alpha tracks brightness instead of being a constant", async () => {
  const shaders = await readFile(new URL("../components/orb/shaders.ts", import.meta.url), "utf8");
  assert.match(shaders, /vec4 emit\(vec3 c\)[^\n]*max\(max\(c\.r, c\.g\), c\.b\)/);
  assert.doesNotMatch(shaders, /gl_FragColor = vec4\([^;]*, 1\.\);/);
});
