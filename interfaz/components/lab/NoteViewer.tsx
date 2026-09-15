"use client";

import { useEffect, useRef } from "react";
import { FileText, Search, Star, X } from "lucide-react";

export interface ViewerNote {
  id: string; title: string; updatedAt: string; favorite: boolean;
}

/** The archive, as a window over the right of the screen. It borrows the floating
 *  windows' glass so it reads as the same furniture, without their positioning. */
export function NoteViewer({ notes, marked, query, width, onQuery, onToggleFavorite, onClose, onOpen }: {
  notes: ViewerNote[];
  /** The note Helios is pointing at right now. Transient, never a stored state. */
  marked: string | null;
  query: string;
  width: number;
  onQuery: (value: string) => void;
  onToggleFavorite: (id: string) => void;
  onClose: () => void;
  onOpen: (id: string) => void;
}) {
  const list = useRef<HTMLUListElement>(null);
  const rows = useRef<Record<string, HTMLLIElement | null>>({});

  // Scroll first, mark after. A highlight that lands mid-scroll slides past the
  // eye and is missed, which defeats the whole point of pointing.
  useEffect(() => {
    if (!marked) return;
    const row = rows.current[marked];
    if (!row) return;
    row.classList.remove("marked");
    row.scrollIntoView({ behavior: "smooth", block: "center" });
    let done = false;
    const settle = () => { if (done) return; done = true; row.classList.add("marked"); };
    const timer = setTimeout(settle, 480);
    list.current?.addEventListener("scrollend", settle, { once: true });
    return () => { clearTimeout(timer); done = true; };
  }, [marked]);

  return <aside className="viewer-dock" style={{ width: `${width}px` }} aria-label="Núcleo de Helios">
    <div className="window-glass viewer-glass">
      <header className="window-heading">
        <span className="window-dot" />
        <span className="viewer-title">NÚCLEO · {notes.length} NOTAS</span>
        <button className="icon-button" onClick={onClose} aria-label="Cerrar el visor"><X size={16} /></button>
      </header>
      <div className="viewer-search">
        <Search size={14} aria-hidden="true" />
        <input value={query} onChange={event => onQuery(event.target.value)}
          placeholder="Buscar en el núcleo…" aria-label="Buscar en el núcleo" />
      </div>
      <ul className="viewer-list" ref={list}>
        {notes.map(note => <li key={note.id} ref={el => { rows.current[note.id] = el; }}>
          <button type="button" className="viewer-row" onDoubleClick={() => onOpen(note.id)}>
            <FileText size={16} className="viewer-icon" aria-hidden="true" />
            <span className="viewer-name">{note.title}</span>
            <span className="viewer-date">{note.updatedAt}</span>
          </button>
          <button type="button" className={`viewer-star ${note.favorite ? "on" : ""}`}
            onClick={() => onToggleFavorite(note.id)}
            aria-pressed={note.favorite}
            aria-label={`${note.favorite ? "Quitar de" : "Anclar a"} las favoritas: ${note.title}`}>
            <Star size={15} />
          </button>
        </li>)}
        {!notes.length && <li className="viewer-empty">Nada que coincida.</li>}
      </ul>
    </div>
  </aside>;
}
