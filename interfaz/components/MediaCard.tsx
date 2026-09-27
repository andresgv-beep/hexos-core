"use client";

import { useState } from "react";
import { Film, Pause, Play, X } from "lucide-react";
import { gigabytes, isActive, remaining, type MediaControl, type MediaJob } from "@/lib/helios/media";

/** La tarjeta viva de la cola de vídeo: se mueve sola mientras convierte. */
export function MediaCard({ jobs, onControl }: {
  jobs: MediaJob[];
  onControl: (batchId: string, operation: MediaControl) => Promise<void>;
}) {
  if (!jobs.length) return null;
  return <div className="media-cards">{jobs.map(job => <MediaJobCard key={job.id} job={job} onControl={onControl} />)}</div>;
}

function MediaJobCard({ job, onControl }: { job: MediaJob; onControl: (batchId: string, operation: MediaControl) => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");
  const active = isActive(job);
  async function run(operation: MediaControl) {
    setBusy(true); setError("");
    try { await onControl(job.batchId, operation); setConfirming(false); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo aplicar."); }
    finally { setBusy(false); }
  }
  // Pausar no para la conversión en marcha: impide empezar la siguiente película.
  const estado = !job.paused || !active ? job.label : job.state === "queued" ? "En pausa" : `${job.label} · cola en pausa`;
  const tamaños: [string, string][] = [];
  if (job.sizeBeforeGb !== undefined) tamaños.push(["Antes", gigabytes(job.sizeBeforeGb)]);
  if (job.sizeAfterGb !== undefined) tamaños.push(["Después", gigabytes(job.sizeAfterGb)]);
  else if (job.estimatedGb !== undefined) tamaños.push(["Estimado", `~${gigabytes(job.estimatedGb)}`]);
  if (active && job.etaSeconds !== undefined) tamaños.push(["Queda", remaining(job.etaSeconds)]);
  return <article className="media-card" data-state={job.state} data-paused={job.paused || undefined} aria-label={`${job.title}: ${estado}`}>
    <span className="media-card-icon" aria-hidden="true"><Film size={22} /></span>
    <div className="media-card-body">
      <h3>{job.title}</h3>
      <p className="media-card-state"><span aria-hidden="true" />{estado}{job.percent !== undefined && active ? ` · ${Math.round(job.percent)} %` : ""}</p>
      {job.percent !== undefined && <div className="media-card-track" role="progressbar" aria-label={`Progreso de ${job.title}`}
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(job.percent)}>
        <span style={{ width: `${job.percent}%` }} /></div>}
      {!!tamaños.length && <dl>{tamaños.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>}
      {job.error && <p className="media-card-error" role="alert">{job.error}</p>}
      {error && <p className="media-card-error" role="alert">{error}</p>}
      {active && job.state !== "cancel_requested" && <div className="media-card-actions">
        {job.paused
          ? <button type="button" disabled={busy} onClick={() => void run("resume")}><Play size={14} aria-hidden="true" /> Reanudar la cola</button>
          : <button type="button" disabled={busy} title="La película en curso termina; la siguiente no empieza"
              onClick={() => void run("pause")}><Pause size={14} aria-hidden="true" /> Pausar la cola</button>}
        {confirming
          ? <><button type="button" className="danger" disabled={busy} onClick={() => void run("cancel")}>Sí, cancelar</button>
              <button type="button" disabled={busy} onClick={() => setConfirming(false)}>No</button></>
          : <button type="button" disabled={busy} onClick={() => setConfirming(true)}><X size={14} aria-hidden="true" /> Cancelar</button>}
      </div>}
    </div>
  </article>;
}
