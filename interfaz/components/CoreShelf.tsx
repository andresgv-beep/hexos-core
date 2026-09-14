"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { Star, X } from "lucide-react";
import { createCoreClient,
         type CoreClient, type CoreOverview, type NoteDetail, type NoteSummary } from "@/lib/helios/core";

const defaultClient = createCoreClient("/api/helios");

/** El núcleo de Helios: la tira de favoritos bajo la esfera y, al abrirse, lo que
 *  guarda en su propio equipo. Lee por su cuenta, sin gastar un turno del modelo. */
export function CoreShelf({ client = defaultClient, open, section, onOpen, onClose, reload, onOpenNote }:
  { client?: CoreClient; open: boolean; section: string; onOpen: (section: string) => void;
    onClose: () => void; reload: number; onOpenNote: (note: NoteDetail) => void }) {
  const [overview, setOverview] = useState<CoreOverview | null>(null);
  const [notes, setNotes] = useState<NoteSummary[]>([]);
  const [error, setError] = useState("");

  const refresh = useCallback((signal?: AbortSignal) => {
    client.overview(signal).then(data => { setOverview(data); setError(""); })
      .catch(e => { if (!signal?.aborted) setError(e instanceof Error ? e.message : "No se pudo leer el núcleo."); });
  }, [client]);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh, reload]);

  useEffect(() => {
    if (!open || section !== "notas") return;
    const controller = new AbortController();
    client.notes(undefined, controller.signal).then(setNotes)
      .catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "No se pudieron leer las notas."); });
    return () => controller.abort();
  }, [client, open, section, reload]);

  useEffect(() => {
    if (!open) return;
    const salir = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", salir);
    return () => document.removeEventListener("keydown", salir);
  }, [open, onClose]);

  async function abrirNota(id: string) {
    // Sin esto un fallo se veía como «pulso y no pasa nada», que es peor que el error.
    try { onOpenNote(await client.note(id)); setError(""); onClose(); }
    catch (e) { setError(e instanceof Error ? e.message : "No se pudo abrir la nota."); }
  }

  // El panel sale del árbol a propósito. La tira vive dentro del compositor, que
  // lleva un transform, y un ancestro transformado convierte `position: fixed` en
  // relativo a él: el panel quedaba anclado a la barra de escribir y se salía por
  // abajo de la pantalla. Montado en el body, `fixed` vuelve a ser la ventana.
  const favoritos = overview?.favorites ?? [];
  // «¿Estamos ya en el navegador?». En el servidor no hay body al que portar.
  const montado = useSyncExternalStore(() => () => {}, () => true, () => false);
  const tira = <>
      <button type="button" className={`core-trigger ${open ? "selected" : ""}`}
        aria-expanded={open} onClick={() => (open ? onClose() : onOpen(""))}>
        Núcleo
        {overview && <span className="core-count">{overview.sections
          .reduce((total, s) => total + (s.total ?? 0), 0)}</span>}
      </button>
      {favoritos.map(item => <button key={item.id} type="button" className="core-favorite"
        onClick={() => { onOpen("notas"); void abrirNota(item.id); }}>
        <Star size={14} aria-hidden="true" />
        <span className="core-favorite-title">{item.title}</span>
      </button>)}
      {!favoritos.length && overview && <span className="core-empty">
        Sin favoritos. Pídele a Helios que ancle una nota.
      </span>}
  </>;

  const panel = <div className="core-backdrop">
      <div className="core-panel" role="dialog" aria-modal="true" aria-labelledby="core-title">
        <div className="panel-heading">
          <h2 id="core-title">Núcleo de Helios</h2>
          <button className="icon-button" onClick={onClose} aria-label="Cerrar el núcleo"><X size={20} /></button>
        </div>
        {error && <p className="attachment-error" role="alert">{error}</p>}
        <div className="core-sections">
          {(overview?.sections ?? []).map(s => <button key={s.key} type="button"
            className={`core-section ${section === s.key ? "selected" : ""}`}
            onClick={() => onOpen(s.key)}>
            <span className="core-section-label">{s.label}</span>
            {/* Un total que no se pudo contar no se pinta como cero: se dice que no se sabe. */}
            <span className="core-section-total">{s.total === null ? "—" : s.total}</span>
            {s.total === null && s.unknown && <span className="core-section-note">{s.unknown}</span>}
            {s.unreadable ? <span className="core-section-note">
              {s.unreadable} sin poder leerse</span> : null}
            {s.pending ? <span className="core-section-note">{s.pending} pendiente(s)</span> : null}
          </button>)}
        </div>
        {section === "notas" && <ul className="core-list">
          {notes.map(note => <li key={note.id}>
            <button type="button" onClick={() => void abrirNota(note.id)}>
              <span className="core-list-title">{note.favorite ? "★ " : ""}{note.title}</span>
              <span className="core-list-excerpt">{note.body}{note.truncated ? "…" : ""}</span>
            </button>
          </li>)}
          {!notes.length && <li className="core-empty">Todavía no hay notas.</li>}
        </ul>}
        {overview && <p className="core-note-disclaimer">{overview.note}</p>}
      </div>
    </div>;

  return <>
    <div className="core-shelf" aria-label="Favoritos del núcleo">
      {tira}
    </div>
    {open && montado && createPortal(panel, document.body)}
  </>;
}
