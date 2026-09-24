"use client";

import { HudAccents } from "./HudAccents";

import { useEffect, useState } from "react";
import { Activity, Boxes, Brain, Cpu, MemoryStick, Microchip } from "lucide-react";
import { SystemGauges } from "./SystemGauges";
import { parseTelemetry, type SystemTelemetry } from "@/lib/helios/telemetry";

function percent(used: number, total: number) {
  return total > 0 ? Math.min(100, used * 100 / total) : 0;
}

function gigabytes(value: number) {
  return `${(value / 1024).toFixed(1)} GB`;
}

function Metric({ icon, label, value, detail, amount }: {
  icon: React.ReactNode; label: string; value: string; detail?: string; amount: number;
}) {
  return <div className="system-metric">
    <div className="metric-heading"><span>{icon}{label}</span><strong>{value}</strong></div>
    <div className="metric-track" aria-hidden="true"><span style={{ width: `${amount}%` }} /></div>
    {detail && <span className="metric-detail">{detail}</span>}
  </div>;
}

export function SystemMonitor({ autoEnabled, autoBusy = false, onToggleAuto, coreTotal, coreOpen = false, onToggleCore, hud = false }: {
  hud?: boolean;
  autoEnabled: boolean | null;
  autoBusy?: boolean;
  onToggleAuto: () => void;
  /** Cuántas notas guarda el núcleo. `null` cuando aún no se sabe: no es cero. */
  coreTotal?: number | null;
  coreOpen?: boolean;
  /** Sin esto la entrada no se pinta, así que el panel sigue sirviendo a solas. */
  onToggleCore?: () => void;
}) {
  const [telemetry, setTelemetry] = useState<SystemTelemetry | null>(null);
  const [online, setOnline] = useState(true);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let request: AbortController | undefined;
    async function update() {
      if (disposed || document.hidden) return;
      request = new AbortController();
      try {
        const response = await fetch("/api/helios/telemetry", { cache: "no-store", signal: request.signal });
        if (!response.ok) throw new Error("Telemetría no disponible");
        const parsed = parseTelemetry(await response.json());
        if (!disposed) { setTelemetry(parsed); setOnline(true); }
      } catch {
        if (!disposed && !request.signal.aborted) setOnline(false);
      } finally {
        if (!disposed && !document.hidden) timer = setTimeout(update, 2000);
      }
    }
    function visibility() {
      clearTimeout(timer);
      request?.abort();
      if (!document.hidden) void update();
    }
    void update();
    document.addEventListener("visibilitychange", visibility);
    return () => { disposed = true; clearTimeout(timer); request?.abort(); document.removeEventListener("visibilitychange", visibility); };
  }, []);
  const cpu = telemetry?.cpu.usagePct ?? 0;
  const gpu = telemetry?.gpu.usagePct ?? 0;
  const ram = telemetry ? percent(telemetry.ram.usedMb, telemetry.ram.totalMb) : 0;
  const vram = telemetry ? percent(telemetry.vram.usedMb, telemetry.vram.totalMb) : 0;
  return <aside className="system-monitor" aria-label="Consumo del sistema">
    {hud && <HudAccents />}
    <div className="monitor-title">
      <Activity size={17} /><span>SISTEMA</span><span className={`monitor-status ${online ? "online" : ""}`} />
    </div>
    <div className="monitor-content">
      {!telemetry && <p className="monitor-loading">{online ? "Leyendo recursos…" : "Telemetría desconectada"}</p>}
      {telemetry && (hud ? <SystemGauges telemetry={telemetry} /> : <>
        <Metric icon={<Cpu size={15} />} label="CPU" value={`${Math.round(cpu)}%`} amount={cpu} />
        <Metric icon={<MemoryStick size={15} />} label="RAM" value={`${Math.round(ram)}%`} amount={ram} detail={`${gigabytes(telemetry.ram.usedMb)} / ${gigabytes(telemetry.ram.totalMb)}`} />
        <Metric icon={<Microchip size={15} />} label="GPU" value={`${Math.round(gpu)}%`} amount={gpu} detail={telemetry.gpu.temperatureC === null ? telemetry.gpu.name : `${Math.round(telemetry.gpu.temperatureC)} °C · ${telemetry.gpu.name}`} />
        <Metric icon={<MemoryStick size={15} />} label="VRAM" value={`${Math.round(vram)}%`} amount={vram} detail={`${gigabytes(telemetry.vram.usedMb)} / ${gigabytes(telemetry.vram.totalMb)}`} />
      </>)}
      {!online && <p className="monitor-offline">Datos temporalmente no disponibles</p>}
    </div>
    {onToggleCore && <div className="monitor-core">
      <button className={`auto-thinking${coreOpen ? " active" : ""}`} type="button" aria-pressed={coreOpen}
        onClick={onToggleCore} aria-expanded={coreOpen}
        aria-label={coreOpen ? "Cerrar el núcleo" : "Abrir el núcleo"}>
        <Boxes size={29} strokeWidth={1.45} aria-hidden="true" />
        <span><strong>NÚCLEO</strong><small>{coreTotal === null || coreTotal === undefined ? "—" : `${coreTotal} notas`}</small></span>
        <i aria-hidden="true" />
      </button>
    </div>}
    {autoEnabled !== null && <div className="monitor-auto">
      <button className={`auto-thinking${autoEnabled ? " active" : ""}`} type="button" aria-pressed={autoEnabled}
        disabled={autoBusy} onClick={onToggleAuto}
        aria-label={autoEnabled ? "Desactivar pensamiento automático" : "Activar pensamiento automático"}
        title={autoEnabled ? "Pensamiento automático activado" : "Pensamiento automático desactivado"}>
        <Brain size={31} strokeWidth={1.45} aria-hidden="true" />
        <span><strong>AUTO</strong><small>{autoBusy ? "Sincronizando" : autoEnabled ? "Activado" : "Desactivado"}</small></span>
        <i aria-hidden="true" />
      </button>
    </div>}
  </aside>;
}
