import type { SystemTelemetry } from '@/lib/helios/telemetry';

/** Cada rosco con su propio degradado encendido: se distinguen de un vistazo. */
const TONES = {
  CPU: ['#fff0b8', '#ffb43a'],
  GPU: ['#ffd08a', '#ff6a2b'],
  VRAM: ['#fff7dc', '#f4c46a'],
} as const;

const gb = (mb: number) => (mb / 1024).toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const decimal = (value: number) => value.toLocaleString('es-ES', { maximumFractionDigits: 1 });

export function SystemGauges({ telemetry }: { telemetry: SystemTelemetry }) {
  const percent = (used: number, total: number) => total > 0 ? Math.min(100, used / total * 100) : 0;
  const { cpu, gpu, vram, ram } = telemetry;
  // Debajo de cada rosco, lo que el porcentaje no dice: temperatura, consumo, lo que queda.
  const gauges = [
    { label: 'CPU', value: cpu.usagePct, lines: [
      cpu.temperatureC !== null ? `${Math.round(cpu.temperatureC)} °C` : null,
      cpu.cores !== null ? `${cpu.cores} hilos` : null,
      cpu.load1m !== null ? `carga ${decimal(cpu.load1m)}` : null] },
    { label: 'GPU', value: gpu.usagePct, lines: [
      gpu.temperatureC !== null ? `${Math.round(gpu.temperatureC)} °C` : null,
      gpu.powerW !== null ? `${Math.round(gpu.powerW)} W` : null] },
    { label: 'VRAM', value: percent(vram.usedMb, vram.totalMb), lines: [
      `${gb(vram.usedMb)} / ${gb(vram.totalMb)} GB`,
      `quedan ${gb(Math.max(0, vram.totalMb - vram.usedMb))} GB`] },
  ] as const;
  const ramPct = percent(ram.usedMb, ram.totalMb);
  return <div className="hud-system-gauges">
    <div className="hud-gauge-row">{gauges.map(({ label, value, lines }) => <div className="hud-gauge" key={label}>
      <div className="hud-gauge-dial">
        <svg viewBox="0 0 78 78" fill="none" aria-hidden="true">
          <defs>
            <linearGradient id={`gauge-${label}`} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor={TONES[label][0]} /><stop offset="1" stopColor={TONES[label][1]} />
            </linearGradient>
          </defs>
          <circle cx="39" cy="39" r="36" className="hud-gauge-ticks" strokeWidth="2" strokeDasharray="2 4" />
          <circle cx="39" cy="39" r="28" className="hud-gauge-track" strokeWidth="6" />
          <circle cx="39" cy="39" r="28" pathLength="100" stroke={`url(#gauge-${label})`} strokeWidth="6" strokeLinecap="round"
            strokeDasharray={`${Math.max(value, 0.5)} 100`} transform="rotate(-90 39 39)" className="hud-gauge-fill" />
        </svg><strong>{Math.round(value)}%</strong>
      </div>
      <span>{label}</span>
      <ul className="hud-gauge-facts">{lines.filter(Boolean).map(line => <li key={line}>{line}</li>)}</ul>
    </div>)}</div>
    <div className="hud-ram-label"><span>RAM</span><span>{gb(ram.usedMb)} / {gb(ram.totalMb)} GB · quedan {gb(Math.max(0, ram.totalMb - ram.usedMb))} GB</span></div>
    <div className="hud-ram-bar" role="meter" aria-label="RAM" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(ramPct)}>
      <span style={{ width: `${ramPct}%` }} /></div>
    <p className="hud-gpu-detail">{gpu.name}</p>
  </div>;
}
