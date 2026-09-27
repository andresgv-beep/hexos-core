"use client";
import { useCallback, useLayoutEffect, useRef, useState } from "react";
import type { HistoryMessage } from "@/lib/helios/hexos";
import type { ReplyArtifact } from "@/lib/helios/preview";
import type { NoteDetail } from "@/lib/helios/core";
import { ReplyMarkdown } from "./ReplyMarkdown";
import { TurnoVisible, type Turn } from "./ConversationStream";
import { CodeWorkspace } from "./CodeWorkspace";

const panels = ["Notas", "Chat", "Código", "Visualización"];
/** Presentation only: no second transport, conversation or agent. */
export function MobileWorkspace({ previous, turns, notes, artifact, busy, error, onBrowseNotes,
  onPreview, hasEarlier, olderLoading, onLoadEarlier, onOpenFiles }: {
  previous: HistoryMessage[]; turns: Turn[]; notes: NoteDetail[]; artifact: ReplyArtifact | null;
  busy: boolean; error: string; onBrowseNotes: () => void;
  onPreview: (code: string, language?: string) => void;
  hasEarlier?: boolean; olderLoading?: boolean; onLoadEarlier?: () => Promise<void>;
  onOpenFiles?: () => void;
}) {
  const [page, setPage] = useState(1);
  const rail = useRef<HTMLDivElement>(null);
  const chat = useRef<HTMLElement>(null);
  const following = useRef(true);
  const selectedPage = useRef(1);
  const attachRail = useCallback((element: HTMLDivElement | null) => {
    rail.current = element;
    if (element) element.scrollLeft = element.clientWidth;
  }, []);
  useLayoutEffect(() => {
    if (chat.current && following.current) chat.current.scrollTop = chat.current.scrollHeight;
  }, [previous, turns]);
  useLayoutEffect(() => {
    const element = rail.current;
    if (!element) return;
    let width = element.clientWidth;
    const observer = new ResizeObserver(() => {
      if (element.clientWidth !== width) {
        width = element.clientWidth;
        element.scrollLeft = selectedPage.current * width;
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  function go(index: number) {
    selectedPage.current = index;
    rail.current?.scrollTo({ left: index * rail.current.clientWidth,
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
    setPage(index);
  }
  async function loadEarlier() {
    const element = chat.current;
    const height = element?.scrollHeight ?? 0;
    const top = element?.scrollTop ?? 0;
    following.current = false;
    await onLoadEarlier?.();
    requestAnimationFrame(() => { if (element) element.scrollTop = top + element.scrollHeight - height; });
  }
  return <section className="mobile-workspace" aria-label="Helios móvil">
    <nav className="mobile-tabs" aria-label="Secciones de Helios">
      {panels.map((label, index) => <button key={label} type="button" aria-current={page === index ? 'page' : undefined}
        onClick={() => go(index)}>{label}</button>)}
    </nav>
    <div className="mobile-rail" ref={attachRail} onScroll={event => { const el = event.currentTarget;
      if (el.clientWidth) {
        const index = Math.max(0, Math.min(3, Math.round(el.scrollLeft / el.clientWidth)));
        selectedPage.current = index; setPage(index);
      } }}>
      <section className="mobile-page" aria-label="Notas">
        <h2>Notas</h2><button className="history-code-open" onClick={onBrowseNotes}>Consultar notas guardadas</button>
        {!notes.length && <p>Abre una nota del núcleo o pídesela a Helios. La encontrarás aquí.</p>}
        {notes.map(note => <article key={note.id} className="mobile-note"><h3>{note.title}</h3>
          <ReplyMarkdown text={note.body} /></article>)}
      </section>
      <section className="mobile-page mobile-chat" aria-label="Conversación continua" ref={chat}
        onScroll={event => { const el = event.currentTarget;
          following.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100; }}>
        {error && <p role="alert">{error}</p>}
        {onOpenFiles && <button className="history-code-open" onClick={onOpenFiles}>Archivos del NAS</button>}
        {hasEarlier && <button type="button" className="history-code-open" disabled={olderLoading}
          onClick={() => void loadEarlier()}>{olderLoading ? "Cargando mensajes…" : "Cargar mensajes anteriores"}</button>}
        {!previous.length && !turns.length && <p>Habla con Helios. Tu conversación continúa aquí.</p>}
        {previous.map((message, index) => <article className={`history-entry ${message.role}`} key={index}>
          <span className="message-author">{message.role === 'user' ? 'TÚ' : 'HELIOS'}</span>
          <ReplyMarkdown text={message.text} onPreviewCode={onPreview} />
        </article>)}
        {turns.map(turn => <TurnoVisible key={turn.id} turn={turn} onPreviewCode={onPreview} />)}
      </section>
      {[2, 3].map(index => <section className="mobile-page mobile-artifact" aria-label={panels[index]} key={index}>
        {artifact ? <CodeWorkspace artifact={artifact} busy={busy} canUndo={false} onUndo={() => {}}
          onClose={() => go(1)} onCreatePreview={onPreview}
          fixedMode={index === 2 ? 'code' : 'preview'} />
          : <div><h2>{panels[index]}</h2><p>Cuando Helios genere una implementación, aparecerá aquí.</p></div>}
      </section>)}
    </div>
  </section>;
}
