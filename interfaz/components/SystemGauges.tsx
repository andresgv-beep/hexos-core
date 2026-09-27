import type { SystemTelemetry } from '@/lib/helios/telemetry';

/** Cada rosco con su propio degradado encendido: se distinguen de un vistazo. */
const TONES = {
  CPU: ['#fff0b8', '#ffb43a'],
  GPU: ['#ffd08a', '#ff6a2b'],
  VRAM: ['#fff7dc', '#f4c46a'],
} as const;

export function SystemGauges({ telemetry }: { telemetry: SystemTelemetry }) {
  const percent = (used: number, total: number) => total > 0 ? Math.min(100, used / total * 100) : 0;
  const gauges = [
    { label: 'CPU', value: telemetry.cpu.usagePct },
    { label: 'GPU', value: telemetry.gpu.usagePct },
    { label: 'VRAM', value: percent(telemetry.vram.usedMb, telemetry.vram.totalMb) },
  ] as const;
  const ram = percent(telemetry.ram.usedMb, telemetry.ram.totalMb);
  return <div className="hud-system-gauges">
    <div className="hud-gauge-row">{gauges.map(({ label, value }) => <div className="hud-gauge" key={label}>
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
      </div><span>{label}</span>
    </div>)}</div>
    <div className="hud-ram-label"><span>RAM</span><span>{(telemetry.ram.usedMb / 1024).toFixed(1)} / {(telemetry.ram.totalMb / 1024).toFixed(1)} GB</span></div>
    <div className="hud-ram-segments" role="meter" aria-label="RAM" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(ram)}>
      {Array.from({ length: 20 }, (_, i) => <i key={i} data-filled={i < Math.round(ram / 5)} />)}</div>
    <p className="hud-gpu-detail">{telemetry.gpu.name}{telemetry.gpu.temperatureC !== null && ` · ${Math.round(telemetry.gpu.temperatureC)} °C`}</p>
  </div>;
}
