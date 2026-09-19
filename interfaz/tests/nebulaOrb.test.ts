import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = readFile(new URL("../components/orb/NebulaOrb.tsx", import.meta.url), "utf8");

test("el núcleo limita resolución y frecuencia con una sola pasada WebGL", async () => {
  const orb = await source;
  assert.match(orb, /const MAX_FPS = 30/);
  assert.match(orb, /const MAX_DPR = 1\.4/);
  assert.match(orb, /drawArrays\(gl\.TRIANGLES, 0, 3\)/);
  assert.doesNotMatch(orb, /three|EffectComposer|Bloom/);
});

test("el exterior es transparente y evita calcular ruido fuera del halo", async () => {
  const orb = await source;
  assert.match(orb, /if\(sd>\.18\)\{outColor=vec4\(0\.\);return;\}/);
  assert.match(orb, /outColor=vec4\(col\*opacity,opacity\)/);
  assert.doesNotMatch(orb, /outColor=vec4\(col,1\.\)/);
});

test("los estados de Helios alimentan el shader sin inventar estados visuales", async () => {
  const orb = await source;
  for (const phase of ["idle", "listening", "thinking", "tool", "responding", "error"]) {
    assert.match(orb, new RegExp(`${phase}:`));
  }
  assert.match(orb, /phases\[props\.signal\.phase\]\.color/);
  assert.match(orb, /orbTargetScale\(props\.signal\.phase/);
});
