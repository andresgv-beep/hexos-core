import type { SystemTelemetry } from '@/lib/helios/telemetry';

export function SystemGauges({ telemetry }: { telemetry: SystemTelemetry }) {
  const percent = (used: number, total: number) => total > 0 ? Math.min(100, used / total * 100) : 0;
  const gauges = [
    { label: 'CPU', value: telemetry.cpu.usagePct },
    { label: 'GPU', value: telemetry.gpu.usagePct },
    { label: 'VRAM', value: percent(telemetry.vram.usedMb, telemetry.vram.totalMb) },
  ];
  const ram = percent(telemetry.ram.usedMb, telemetry.ram.totalMb);
  return <div className="hud-system-gauges">
    <div className="hud-gauge-row">{gauges.map(({ label, value }) => <div className="hud-gauge" key={label}>
      <div className="hud-gauge-dial">
        <svg viewBox="0 0 78 78" fill="none" aria-hidden="true">
          <circle cx="39" cy="39" r="36" stroke="var(--hud-tick)" strokeWidth="3" strokeDasharray="2 4" />
          <circle cx="39" cy="39" r="28" stroke="var(--hud-track)" strokeWidth="7" />
          <circle cx="39" cy="39" r="28" pathLength="100" stroke={label === 'VRAM' ? 'var(--hud-pink)' : 'var(--hud-accent)'} strokeWidth="7" strokeDasharray={`${value} 100`} transform="rotate(-90 39 39)" />
          <circle cx="39" cy="39" r="18" stroke="var(--hud-tick)" />
        </svg><strong>{Math.round(value)}%</strong>
      </div><span>{label}</span>
    </div>)}</div>
    <div className="hud-ram-label"><span>RAM</span><span>{(telemetry.ram.usedMb / 1024).toFixed(1)} / {(telemetry.ram.totalMb / 1024).toFixed(1)} GB</span></div>
    <div className="hud-ram-segments" aria-label={`RAM ${Math.round(ram)}%`}>{Array.from({ length: 20 }, (_, i) => <i key={i} data-filled={i < Math.round(ram / 5)} />)}</div>
    <p className="hud-gpu-detail">{telemetry.gpu.name}{telemetry.gpu.temperatureC !== null && ` · ${Math.round(telemetry.gpu.temperatureC)} °C`}</p>
  </div>;
}
