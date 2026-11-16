"use client";

import type { DownloadRequest } from "@/lib/helios/hexos";

const megas = new Intl.NumberFormat("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function peso(bytes: number | null): string {
  if (bytes === null) return "sin declarar";
  return bytes < 1_000_000 ? `${Math.max(1, Math.round(bytes / 1000))} kB` : `${megas.format(bytes / 1_000_000)} MB`;
}

/** La descarga que Helios propone. Lo que se enseña es lo que HexOS ha visto en el servidor,
 *  no lo que Helios dice que hay: nombre, origen, tipo y tamaño antes de que entre nada. */
export function DownloadCard({ plan, busy, error, onDecide }: {
  plan: DownloadRequest; busy: boolean; error: string; onDecide: (approve: boolean) => void;
}) {
  return <div className="access-backdrop">
    <div className="access-panel" role="dialog" aria-modal="true" aria-labelledby="download-title">
      <h2 id="download-title" className="panel-title">Helios propone descargar un fichero</h2>
      <dl className="download-facts">
        <dt>Nombre</dt><dd>{plan.name}</dd>
        <dt>Origen</dt><dd>{plan.host}</dd>
        <dt>Tipo</dt><dd>{plan.kind}</dd>
        <dt>Tamaño</dt><dd>{peso(plan.bytes)}</dd>
        <dt>Destino</dt><dd>{plan.folder}</dd>
      </dl>
      <p className="access-target download-url">{plan.url}</p>
      {plan.bytes === null && <p className="access-warn" role="alert">
        El servidor no dice cuánto pesa. Si pasa de 50 MB no se guardará.
      </p>}
      {error && <p className="attachment-error" role="alert">{error}</p>}
      <p className="access-note">
        Helios no puede bajarlo. Si lo apruebas, lo descarga HexOS, lo guarda sin abrirlo ni ejecutarlo
        y comprueba lo guardado. Si es un PDF con texto, Helios podrá leerlo después.
      </p>
      <div className="access-actions">
        <button type="button" disabled={busy} onClick={() => onDecide(false)}>Cancelar</button>
        <button type="button" className="access-save" disabled={busy} onClick={() => onDecide(true)}>
          {busy ? "Descargando…" : "Aprobar y descargar"}</button>
      </div>
    </div>
  </div>;
}
