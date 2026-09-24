import type { InferenceMetrics } from "@/lib/helios/metrics";

const integer = new Intl.NumberFormat("es-ES");
const decimal = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 });

export function InferenceFooter({ metrics }: { metrics?: InferenceMetrics }) {
  const used = metrics?.contextUsed;
  const capacity = metrics?.contextCapacity;
  const percent = used != null && capacity != null ? used / capacity * 100 : null;
  const speed = metrics?.tokensPerSecond;
  return <div className="inference-footer">
    <div className="inference-context" data-full={percent != null && percent >= 90}
      title="Tokens en la caché del modelo; el historial visible puede ser más largo.">
      <span>Contexto</span>
      <span className="inference-track" role="meter" aria-label="Ocupación del contexto"
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent == null ? undefined : Math.min(100, percent)}
        aria-valuetext={percent == null ? "Sin medición" : `${integer.format(used!)} de ${integer.format(capacity!)} tokens`}>
        <span style={{ width: `${Math.min(100, percent ?? 0)}%` }} />
      </span>
      <span>{percent == null ? "—" : `${Math.round(percent)} % · ${integer.format(used!)} / ${integer.format(capacity!)}`}</span>
    </div>
    <span title="Media del turno: tokens / tiempo de decodificación. Se actualiza tras cada generación; excluye prefill y herramientas.">
      Generación <strong>{speed == null ? "—" : decimal.format(speed)} tok/s</strong>
    </span>
  </div>;
}
