import type { ProjectChange } from "@/lib/helios/hexos";

/** La tarjeta de un cambio propuesto en un fichero del proyecto: qué fichero, las líneas que
 *  entran y salen, y los dos botones. Helios no puede escribirlo; lo escribe HexOS al aprobar. */
export function ProjectChangeCard({ change, busy, error, onDecide }: {
  change: ProjectChange; busy: boolean; error: string; onDecide: (approve: boolean) => void;
}) {
  const verbo = change.kind === "create" ? "crear" : "cambiar";
  return <div className="access-backdrop">
    <div className="access-panel change-panel" role="dialog" aria-modal="true" aria-labelledby="change-title">
      <h2 id="change-title" className="panel-title">Helios propone {verbo} <code>{change.path}</code></h2>
      <p className="access-target">
        Proyecto «{change.projectName}» · <span className="change-mas">+{change.added}</span>{" "}
        <span className="change-menos">−{change.removed}</span>
        {change.kind === "replace" ? " · reemplaza el fichero entero" : ""}
      </p>
      <pre className="change-diff" aria-label="Líneas que cambian">
        {change.diff.map((linea, i) => <span key={i} data-linea={
          linea.startsWith("@@") ? "tramo" : linea.startsWith("+") ? "mas" : linea.startsWith("-") ? "menos" : "igual"
        }>{linea || " "}{"\n"}</span>)}
      </pre>
      {change.diffLines > change.diff.length && <p className="access-warn" role="alert">
        Se enseñan {change.diff.length} de {change.diffLines} líneas del cambio. Aprobarlo escribe el cambio entero.
      </p>}
      {error && <p className="attachment-error" role="alert">{error}</p>}
      <p className="access-note">
        Helios no puede escribirlo. Si lo apruebas, HexOS escribe el fichero dentro de la carpeta del
        proyecto, solo si sigue como estaba cuando se propuso, y lo relee para comprobarlo.
      </p>
      <div className="access-actions">
        <button type="button" disabled={busy} onClick={() => onDecide(false)}>Cancelar</button>
        <button type="button" className="access-save" disabled={busy} onClick={() => onDecide(true)}>
          {busy ? "Escribiendo…" : "Aprobar y escribir"}
        </button>
      </div>
    </div>
  </div>;
}
