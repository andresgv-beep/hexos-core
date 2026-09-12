import assert from "node:assert/strict";
import test from "node:test";
import { parseTelemetry } from "../lib/helios/telemetry";

test("validates and bounds system telemetry before it reaches the interface", () => {
  const result = parseTelemetry({
    timestamp_ms: 10,
    cpu: { usage_pct: 140 },
    ram: { used_mb: 12000, total_mb: 32000 },
    gpu: { name: "GPU", usage_pct: 31.4, temperature_c: 62, power_w: 44.2, healthy: true },
    vram: { used_mb: 4200, total_mb: 8151 },
  });
  assert.equal(result.cpu.usagePct, 100);
  assert.equal(result.gpu.usagePct, 31.4);
  assert.equal(result.vram.totalMb, 8151);
  assert.throws(() => parseTelemetry({}), /Telemetría/);
});
