import type { ProjectChange } from "@/lib/helios/hexos";

const VERBO = { create: "nuevo", replace: "entero", edit: "cambio" } as const;

/** La tarjeta de los cambios propuestos en el proyecto: cada fichero con las líneas que entran y
 *  salen, y dos botones para todos a la vez. Helios no puede escribirlos; los escribe HexOS al aprobar. */
export function ProjectChangeCard({ change, busy, error, onDecide }: {
  change: ProjectChange; busy: boolean; error: string; onDecide: (approve: boolean) => void;
}) {
  const varios = change.changes.length > 1;
  const cortados = change.changes.filter(c => c.diffLines > c.diff.length).length;
  return <div className="access-backdrop">
    <div className="access-panel change-panel" role="dialog" aria-modal="true" aria-labelledby="change-title">
      <h2 id="change-title" className="panel-title">
        {varios ? `Helios propone ${change.changes.length} ficheros`
          : <>Helios propone {change.changes[0].kind === "create" ? "crear" : "cambiar"} <code>{change.changes[0].path}</code></>}
      </h2>
      <p className="access-target">
        Proyecto «{change.projectName}» · <span className="change-mas">+{change.added}</span>{" "}
        <span className="change-menos">−{change.removed}</span>
      </p>
      <div className="change-files">
        {change.changes.map(fichero => <section key={fichero.path} aria-label={fichero.path}>
          {varios && <h3 className="change-file">
            <code>{fichero.path}</code>
            <span>{VERBO[fichero.kind]} · <span className="change-mas">+{fichero.added}</span>{" "}
              <span className="change-menos">−{fichero.removed}</span></span>
          </h3>}
          {!varios && fichero.kind === "replace" && <p className="access-target">Reemplaza el fichero entero.</p>}
          <pre className="change-diff">
            {fichero.diff.map((linea, i) => <span key={i} data-linea={
              linea.startsWith("@@") ? "tramo" : linea.startsWith("+") ? "mas" : linea.startsWith("-") ? "menos" : "igual"
            }>{linea || " "}{"\n"}</span>)}
          </pre>
        </section>)}
      </div>
      {cortados > 0 && <p className="access-warn" role="alert">
        {varios ? `En ${cortados} de los ficheros` : "Aquí"} solo se enseñan las primeras 400 líneas del cambio.
        Aprobarlo escribe el cambio entero.
      </p>}
      {error && <p className="attachment-error" role="alert">{error}</p>}
      <p className="access-note">
        Helios no puede escribirlo. Si lo apruebas, HexOS escribe {varios ? "todos los ficheros" : "el fichero"} dentro
        de la carpeta del proyecto, solo si {varios ? "siguen" : "sigue"} como {varios ? "estaban" : "estaba"} cuando
        se propuso, y lo relee para comprobarlo.
      </p>
      <div className="access-actions">
        <button type="button" disabled={busy} onClick={() => onDecide(false)}>Cancelar</button>
        <button type="button" className="access-save" disabled={busy} onClick={() => onDecide(true)}>
          {busy ? "Escribiendo…" : varios ? `Aprobar y escribir los ${change.changes.length}` : "Aprobar y escribir"}
        </button>
      </div>
    </div>
  </div>;
}
