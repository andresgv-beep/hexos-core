import type { ProjectChange } from "@/lib/helios/hexos";

export type ChangeState = "pendiente" | "escrito" | "cancelado" | "fallo";

const ESTADO: Record<ChangeState, string> = {
  pendiente: "Revisar y aprobar", escrito: "Escrito", cancelado: "Cancelado", fallo: "No se escribió",
};

/** Un cambio en el código, en una línea: qué ficheros y cuántas líneas entran y salen. Sustituye
 *  a la frase «Aprobado: cambiar main.py…» y es la puerta a la ventana con el detalle. */
export function ChangeChip({ change, state, detail, onOpen }: {
  change: ProjectChange; state: ChangeState; detail?: string; onOpen: () => void;
}) {
  const ficheros = change.changes.length === 1 ? change.changes[0].path : `${change.changes.length} ficheros`;
  return <button type="button" className="change-chip" data-state={state} onClick={onOpen}
    title={detail ?? (state === "pendiente" ? "Abrir los cambios para revisarlos" : "Ver los cambios")}
    aria-label={`${ESTADO[state]}: ${ficheros}, ${change.added} líneas añadidas y ${change.removed} quitadas`}>
    <span className="change-chip-file">{ficheros}</span>
    <span className="change-chip-count">
      <span className="change-mas">+{change.added}</span> <span className="change-menos">−{change.removed}</span>
    </span>
    <span className="change-chip-state">{ESTADO[state]}</span>
  </button>;
}
