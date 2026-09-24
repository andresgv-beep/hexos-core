"use client";

import { type RefObject } from "react";
import { ReplyMarkdown } from "./ReplyMarkdown";
import { Download, Printer } from "lucide-react";
import { FloatingWindow, type WindowPlacement } from "./FloatingWindow";
import { noteAsMarkdown, noteFilename, type NoteDetail } from "@/lib/helios/core";

export interface NoteWindowState extends WindowPlacement {
  note: NoteDetail;
}

/** Una nota en una ventana: se queda delante, se mueve y se guarda en disco. */
export function NoteWindow({ state, front, orbTarget, onAbsorbed, onMove, onMinimize, onClose, onFocus }: {
  state: NoteWindowState;
  front: boolean;
  orbTarget?: RefObject<HTMLButtonElement | null>;
  onAbsorbed?: (id: string) => void;
  onMove: (id: string, x: number, y: number) => void;
  onMinimize: (id: string) => void;
  onClose: (id: string) => void;
  onFocus: (id: string) => void;
}) {
  const { note } = state;
  return <FloatingWindow placement={state} label={note.favorite ? `★ ${note.title}` : note.title}
    title={`Nota: ${note.title}`} front={front} orbTarget={orbTarget} onAbsorbed={onAbsorbed}
    onMove={onMove} onMinimize={onMinimize} onClose={onClose} onFocus={onFocus}>
    <NoteContent note={note} />
  </FloatingWindow>;
}

export function NoteContent({ note }: { note: NoteDetail }) {
  function descargar() {
    const blob = new Blob([noteAsMarkdown(note)], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const enlace = document.createElement("a");
    enlace.href = url;
    enlace.download = noteFilename(note.title);
    enlace.click();
    URL.revokeObjectURL(url);
  }
  return <>
    <p className="note-meta">
      {note.state}{note.tags.length ? ` · ${note.tags.join(", ")}` : ""}
      {note.revisions.length > 1 ? ` · ${note.revisions.length} versiones guardadas` : ""}
    </p>
    <div className="note-body"><ReplyMarkdown text={note.body} /></div>
    <div className="note-actions">
      <button type="button" onClick={descargar}><Download size={15} aria-hidden="true" /> Descargar .md</button>
      <button type="button" onClick={() => window.print()}><Printer size={15} aria-hidden="true" /> Imprimir o PDF</button>
    </div>
  </>;
}
