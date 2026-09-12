import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { LIGHT_CORE_SIGMA, MIN_LIGHT_PIXELS } from "../components/orb/lightSampling";
import { createOrbGeometry, createOrbitGeometry } from "../components/orb/geometry";

function pixelPhaseVariation(sigma: number) {
  const flux: number[] = [];
  for (let y = 0; y < 16; y++) for (let x = 0; x < 16; x++) {
    let sum = 0;
    for (let j = -8; j <= 8; j++) for (let i = -8; i <= 8; i++) {
      sum += Math.exp(-((i - x / 16) ** 2 + (j - y / 16) ** 2) / (2 * sigma ** 2));
    }
    flux.push(sum);
  }
  return (Math.max(...flux) - Math.min(...flux)) / (flux.reduce((a, b) => a + b) / flux.length);
}

test("minimum luminous core remains stable while crossing pixel boundaries", () => {
  assert.ok(pixelPhaseVariation(8 / Math.sqrt(480)) > .5);
  assert.ok(pixelPhaseVariation(MIN_LIGHT_PIXELS * LIGHT_CORE_SIGMA) < .001);
});

// The clamp that holds a distant light at MIN_*_PIXELS must be paired with an
// equal loss of intensity. Without it ~4000 additive sprites each painted up to
// 20x their true area at full strength, saturating the frame to solid white.
test("enlarging a sub-pixel light conserves its total energy", async () => {
  const shaders = await readFile(new URL("../components/orb/shaders.ts", import.meta.url), "utf8");
  for (const stage of [/export const pointVertex = [\s\S]*?\n`;/, /export const cometVertex = [\s\S]*?\n`;/]) {
    const source = shaders.match(stage)?.[0] ?? "";
    assert.match(source, /conservation = min\(wanted \/ diameter, 1\.\)/);
    assert.match(source, /vLight = [^;]*conservation \* conservation/);
  }
});

test("nodes, comets and orbit lights use complete instanced quad attributes", () => {
  const orb = createOrbGeometry(), orbit = createOrbitGeometry(0);
  for (const geometry of [orb.points, orb.comets, orbit.points]) {
    assert.equal(geometry.isInstancedBufferGeometry, true);
    assert.equal(geometry.getAttribute("position").count, 6);
    assert.ok(geometry.instanceCount > 0);
    for (const [name, attribute] of Object.entries(geometry.attributes)) {
      if (name !== "position") assert.equal(attribute.count, geometry.instanceCount, name);
      assert.ok(Array.from(attribute.array).every(Number.isFinite), name);
    }
    geometry.dispose();
  }
  orb.lines.dispose(); orbit.line.dispose();
});
