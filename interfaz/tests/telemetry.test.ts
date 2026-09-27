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

test("cpu details are optional: an older backend reads as unknown, not zero", () => {
  const base = { timestamp_ms: 10, ram: { used_mb: 1, total_mb: 2 },
    gpu: { name: "GPU", usage_pct: 1, temperature_c: null, power_w: null, healthy: true }, vram: { used_mb: 1, total_mb: 2 } };
  const old = parseTelemetry({ ...base, cpu: { usage_pct: 12 } });
  assert.deepEqual([old.cpu.cores, old.cpu.load1m, old.cpu.temperatureC], [null, null, null]);
  const now = parseTelemetry({ ...base, cpu: { usage_pct: 12, cores: 16, load_1m: 1.24, temperature_c: 61.8 } });
  assert.deepEqual([now.cpu.cores, now.cpu.load1m, now.cpu.temperatureC], [16, 1.24, 61.8]);
});
