"use client";

import { useLayoutEffect, useRef } from 'react';
import type { HistoryMessage } from '@/lib/helios/hexos';
import { TurnoVisible, type Turn } from './ConversationStream';
import { ReplyMarkdown, type CodeActions } from './ReplyMarkdown';

/** A single scroll surface; incoming text follows only while the reader is at the bottom. */
export function ContinuousChat({ previous, turns, historyError, hasEarlier, olderLoading, onLoadEarlier,
  onReplyComplete, onPreviewCode }: {
  previous: HistoryMessage[]; turns: Turn[]; historyError: string;
  hasEarlier: boolean; olderLoading: boolean; onLoadEarlier: () => Promise<void>;
  onReplyComplete: () => void;
} & CodeActions) {
  const viewport = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const anchor = useRef<{ height: number; top: number; count: number } | null>(null);
  useLayoutEffect(() => {
    const el = viewport.current;
    if (!el) return;
    if (anchor.current && previous.length !== anchor.current.count) {
      el.scrollTop = anchor.current.top + el.scrollHeight - anchor.current.height;
      anchor.current = null;
    } else if (following.current) el.scrollTop = el.scrollHeight;
  }, [previous, turns]);
  useLayoutEffect(() => {
    const el = viewport.current, body = content.current;
    if (!el || !body) return;
    const observer = new ResizeObserver(() => { if (following.current) el.scrollTop = el.scrollHeight; });
    observer.observe(body);
    return () => observer.disconnect();
  }, []);
  async function loadEarlier() {
    const el = viewport.current;
    if (el) anchor.current = { height: el.scrollHeight, top: el.scrollTop, count: previous.length };
    following.current = false;
    await onLoadEarlier();
  }
  return <div className="hud-chat-scroll" ref={viewport} aria-label="Conversación continua"
    onScroll={event => { const el = event.currentTarget;
      following.current = el.scrollHeight - el.scrollTop - el.clientHeight < 64; }}>
    <div ref={content} className="hud-chat-messages">
      {hasEarlier && <button className="history-code-open" disabled={olderLoading} onClick={() => void loadEarlier()}>
        {olderLoading ? 'Cargando mensajes…' : 'Cargar mensajes anteriores'}</button>}
      {historyError && <p role="status">{historyError}</p>}
      {previous.map((message, index) => <article key={`saved-${index}`} className={`hud-saved-message ${message.role}`}>
        <span className="message-author">{message.role === 'user' ? 'TÚ' : 'HELIOS'}</span>
        <ReplyMarkdown text={message.text} onPreviewCode={onPreviewCode} />
      </article>)}
      {turns.map((turn, index) => <TurnoVisible key={turn.id} turn={turn} settled={index < turns.length - 1}
        onReplyComplete={index === turns.length - 1 ? onReplyComplete : undefined}
        onPreviewCode={onPreviewCode} />)}
      {!previous.length && !turns.length && <div className="hud-welcome"><h2>Hablemos, socio.</h2>
        <p>Escribe a Helios o abre el historial para retomar una conversación.</p></div>}
    </div>
  </div>;
}
