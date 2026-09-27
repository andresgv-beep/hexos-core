export interface SystemTelemetry {
  timestampMs: number;
  /** Núcleos, carga y temperatura son null si el backend no los sabe (o es anterior). */
  cpu: { usagePct: number; name: string | null; frequencyMhz: number | null; cores: number | null; load1m: number | null; temperatureC: number | null };
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
  const maybe = (entry: unknown) => typeof entry === "number" && Number.isFinite(entry) ? Math.max(0, entry) : null;
  if (typeof gpu.name !== "string" || typeof gpu.healthy !== "boolean") throw new Error("Telemetría de GPU no válida");
  return {
    timestampMs: finite(root.timestamp_ms),
    cpu: { usagePct: Math.min(100, finite(cpu.usage_pct)), name: typeof cpu.name === "string" && cpu.name.trim() ? cpu.name.trim() : null,
      frequencyMhz: maybe(cpu.frequency_mhz), cores: maybe(cpu.cores), load1m: maybe(cpu.load_1m), temperatureC: maybe(cpu.temperature_c) },
    ram: { usedMb: finite(ram.used_mb), totalMb: finite(ram.total_mb) },
    gpu: { name: gpu.name, usagePct: Math.min(100, finite(gpu.usage_pct)), temperatureC: optional(gpu.temperature_c), powerW: optional(gpu.power_w), healthy: gpu.healthy },
    vram: { usedMb: finite(vram.used_mb), totalMb: finite(vram.total_mb) },
  };
}

/** «AMD Ryzen 7 5700X 8-Core Processor» → «Ryzen 7 5700X»; «NVIDIA GeForce RTX 4070 Ti» → «RTX 4070 Ti». */
export function shortHardwareName(name: string) {
  return name.replace(/\((?:R|TM)\)|®|™/gi, "")
    .replace(/^(?:AMD|Intel|NVIDIA)\s+/i, "").replace(/^(?:GeForce|Radeon)\s+/i, "")
    .replace(/\s+\d+-Core Processor$/i, "").replace(/\s+(?:CPU\s+)?@.*$/i, "").replace(/\s+Processor$/i, "")
    .replace(/^Core\s+/i, "Core ").replace(/\s{2,}/g, " ").trim();
}
