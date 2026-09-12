export interface SystemTelemetry {
  timestampMs: number;
  cpu: { usagePct: number };
  ram: { usedMb: number; totalMb: number };
  gpu: { name: string; usagePct: number; temperatureC: number | null; powerW: number | null; healthy: boolean };
  vram: { usedMb: number; totalMb: number };
}

function finite(value: unknown, minimum = 0): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error("Telemetría no válida");
  return Math.max(minimum, value);
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Telemetría no válida");
  return value as Record<string, unknown>;
}

export function parseTelemetry(value: unknown): SystemTelemetry {
  const root = record(value), cpu = record(root.cpu), ram = record(root.ram);
  const gpu = record(root.gpu), vram = record(root.vram);
  const optional = (entry: unknown) => entry === null ? null : finite(entry);
  if (typeof gpu.name !== "string" || typeof gpu.healthy !== "boolean") throw new Error("Telemetría de GPU no válida");
  return {
    timestampMs: finite(root.timestamp_ms),
    cpu: { usagePct: Math.min(100, finite(cpu.usage_pct)) },
    ram: { usedMb: finite(ram.used_mb), totalMb: finite(ram.total_mb) },
    gpu: { name: gpu.name, usagePct: Math.min(100, finite(gpu.usage_pct)), temperatureC: optional(gpu.temperature_c), powerW: optional(gpu.power_w), healthy: gpu.healthy },
    vram: { usedMb: finite(vram.used_mb), totalMb: finite(vram.total_mb) },
  };
}
