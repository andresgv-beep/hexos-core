"use client";

import type { DownloadRequest } from "@/lib/helios/hexos";

const megas = new Intl.NumberFormat("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function peso(bytes: number | null): string {
  if (bytes === null) return "sin declarar";
  return bytes < 1_000_000 ? `${Math.max(1, Math.round(bytes / 1000))} kB` : `${megas.format(bytes / 1_000_000)} MB`;
}

/** Lo que Helios propone descargar: un fichero, o varios que se aprueban juntos. Lo que se
 *  enseña es lo que HexOS ha visto en el servidor, no lo que Helios dice que hay: nombre,
 *  origen, tipo y tamaño de cada uno antes de que entre nada. */
export function DownloadCard({ plan, busy, error, onDecide }: {
  plan: DownloadRequest; busy: boolean; error: string; onDecide: (approve: boolean) => void;
}) {
  const varios = plan.items.length > 1;
  const uno = plan.items[0];
  const sinPeso = plan.items.filter(f => f.bytes === null).length;
  const total = plan.items.reduce((suma, f) => suma + (f.bytes ?? 0), 0);
  return <div className="access-backdrop">
    <div className="access-panel" role="dialog" aria-modal="true" aria-labelledby="download-title">
      <h2 id="download-title" className="panel-title">
        {varios ? `Helios propone descargar ${plan.items.length} ficheros` : "Helios propone descargar un fichero"}</h2>
      {varios ? <>
        <ol className="download-items">
          {plan.items.map(f => <li key={f.url}>
            <strong>{f.name}</strong>
            <small>{[f.kind, peso(f.bytes), f.host].filter(Boolean).join(" · ")}</small>
            <small className="download-url">{f.url}</small>
          </li>)}
        </ol>
        <dl className="download-facts">
          <dt>En total</dt><dd>{sinPeso ? `${peso(total)} y ${sinPeso === 1 ? "uno" : sinPeso} sin declarar` : peso(total)}</dd>
          <dt>Destino</dt><dd>{plan.folder}</dd>
        </dl>
      </> : <>
        <dl className="download-facts">
          <dt>Nombre</dt><dd>{uno.name}</dd>
          <dt>Origen</dt><dd>{uno.host}</dd>
          <dt>Tipo</dt><dd>{uno.kind}</dd>
          <dt>Tamaño</dt><dd>{peso(uno.bytes)}</dd>
          <dt>Destino</dt><dd>{plan.folder}</dd>
        </dl>
        <p className="access-target download-url">{uno.url}</p>
      </>}
      {sinPeso > 0 && <p className="access-warn" role="alert">
        {varios ? `El servidor no dice cuánto ${sinPeso === 1 ? "pesa uno de ellos" : `pesan ${sinPeso} de ellos`}. El que pase de 50 MB no se guardará.`
          : "El servidor no dice cuánto pesa. Si pasa de 50 MB no se guardará."}
      </p>}
      {error && <p className="attachment-error" role="alert">{error}</p>}
      <p className="access-note">
        {varios ? "Helios no puede bajarlos. Si lo apruebas, HexOS los descarga uno a uno, los guarda sin abrirlos ni ejecutarlos y comprueba lo guardado. Los PDF con texto podrá leerlos Helios después. Se aprueban o se cancelan todos a la vez."
          : "Helios no puede bajarlo. Si lo apruebas, lo descarga HexOS, lo guarda sin abrirlo ni ejecutarlo y comprueba lo guardado. Si es un PDF con texto, Helios podrá leerlo después."}
      </p>
      <div className="access-actions">
        <button type="button" disabled={busy} onClick={() => onDecide(false)}>Cancelar</button>
        <button type="button" className="access-save" disabled={busy} onClick={() => onDecide(true)}>
          {busy ? "Descargando…" : varios ? `Aprobar y descargar los ${plan.items.length}` : "Aprobar y descargar"}</button>
      </div>
    </div>
  </div>;
}
