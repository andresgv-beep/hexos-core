"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FileText, Search, Star, X } from "lucide-react";
import { createCoreClient, type CoreClient, type NoteDetail, type NoteSummary } from "@/lib/helios/core";

const defaultClient = createCoreClient("/api/helios");

/** Short, human dates. The archive is scanned, not audited: "ayer" reads faster
 *  than a timestamp, and the exact moment is one click away inside the note. */
function cuando(iso: string) {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  const days = Math.floor((Date.now() - at.getTime()) / 86400000);
  if (days <= 0) return `Hoy, ${at.toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" })}`;
  if (days === 1) return "Ayer";
  if (days === 2) return "Anteayer";
  if (days < 7) return `Hace ${days} días`;
  if (days < 31) return "Este mes";
  return at.toLocaleDateString("es", { day: "numeric", month: "short" });
}

/** El núcleo abierto: una ventana sobre la derecha con todo lo que Helios guarda.
 *  Sustituye al modal, que tapaba la esfera entera para mirar sus propias notas. */
export function CoreViewer({ client = defaultClient, open, marked, reload, width = 490, onClose, onOpenNote }: {
  client?: CoreClient;
  open: boolean;
  /** La nota que Helios está señalando ahora. Pasajero, nunca un estado guardado. */
  marked?: string | null;
  reload: number;
  width?: number;
  onClose: () => void;
  onOpenNote: (note: NoteDetail) => void;
}) {
  const [notes, setNotes] = useState<NoteSummary[]>([]);
  const [query, setQuery] = useState("");
  const [soloFavoritas, setSoloFavoritas] = useState(false);
  const [error, setError] = useState("");
  const list = useRef<HTMLUListElement>(null);
  const rows = useRef<Record<string, HTMLLIElement | null>>({});

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    client.notes(soloFavoritas ? { favorite: true } : undefined, controller.signal)
      .then(found => { setNotes(found); setError(""); })
      .catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "No se pudieron leer las notas."); });
    return () => controller.abort();
  }, [client, open, reload, soloFavoritas]);

  useEffect(() => {
    if (!open) return;
    const salir = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", salir);
    return () => document.removeEventListener("keydown", salir);
  }, [open, onClose]);

  // Scroll first, mark after: a highlight that lands mid-scroll slides past the
  // eye unseen, which defeats the point of pointing at it.
  useEffect(() => {
    if (!open || !marked) return;
    const row = rows.current[marked];
    if (!row) return;
    row.classList.remove("marked");
    row.scrollIntoView({ behavior: "smooth", block: "center" });
    let done = false;
    const settle = () => { if (done) return; done = true; row.classList.add("marked"); };
    const timer = setTimeout(settle, 480);
    list.current?.addEventListener("scrollend", settle, { once: true });
    return () => { clearTimeout(timer); done = true; };
  }, [open, marked, notes]);

  const abrir = useCallback(async (id: string) => {
    // Sin esto un fallo se ve como «pulso y no pasa nada», que es peor que el error.
    try { onOpenNote(await client.note(id)); setError(""); }
    catch (e) { setError(e instanceof Error ? e.message : "No se pudo abrir la nota."); }
  }, [client, onOpenNote]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? notes.filter(n => n.title.toLowerCase().includes(q) || n.body.toLowerCase().includes(q)) : notes;
  }, [notes, query]);

  if (!open) return null;
  return <aside className="viewer-dock" style={{ width: `${width}px` }} aria-label="Núcleo de Helios">
    <div className="window-glass viewer-glass">
      <header className="window-heading">
        <span className="window-dot" />
        <span className="viewer-title">NÚCLEO · {notes.length} NOTAS</span>
        <button className="icon-button" onClick={onClose} aria-label="Cerrar el núcleo"><X size={16} /></button>
      </header>
      <div className="viewer-search">
        <Search size={14} aria-hidden="true" />
        <input value={query} onChange={event => setQuery(event.target.value)}
          placeholder="Buscar en el núcleo…" aria-label="Buscar en el núcleo" />
        <button type="button" className={`viewer-filter${soloFavoritas ? " on" : ""}`}
          onClick={() => setSoloFavoritas(value => !value)} aria-pressed={soloFavoritas}
          title="Ver solo las ancladas" aria-label="Ver solo las notas ancladas">
          <Star size={14} fill={soloFavoritas ? "currentColor" : "none"} />
        </button>
      </div>
      {error && <p className="attachment-error" role="alert">{error}</p>}
      <ul className="viewer-list" ref={list}>
        {shown.map(note => <li key={note.id} ref={el => { rows.current[note.id] = el; }}>
          <button type="button" className="viewer-row" onClick={() => void abrir(note.id)}>
            <FileText size={16} className="viewer-icon" aria-hidden="true" />
            <span className="viewer-name">{note.title}</span>
            <span className="viewer-date">{cuando(note.updatedAt)}</span>
          </button>
          <span className={`viewer-star${note.favorite ? " on" : ""}`}
            title={note.favorite ? "Anclada: sale en el aro del núcleo" : "Sin anclar"}>
            <Star size={15} fill={note.favorite ? "currentColor" : "none"} aria-hidden="true" />
            <span className="sr-only">{note.favorite ? "Anclada" : "Sin anclar"}</span>
          </span>
        </li>)}
        {!shown.length && <li className="viewer-empty">
          {notes.length ? "Nada que coincida."
            : soloFavoritas ? "Sin notas ancladas. Pídele a Helios que ancle una."
            : "Todavía no hay notas."}
        </li>}
      </ul>
    </div>
  </aside>;
}
