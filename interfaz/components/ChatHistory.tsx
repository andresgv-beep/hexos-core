"use client";

import { useEffect, useRef } from "react";
import { Code2, X } from "lucide-react";
import type { HistoryMessage } from "@/lib/helios/hexos";
import { extractReplyArtifact, type ReplyArtifact } from "@/lib/helios/preview";
import type { Turn } from "./ConversationStream";
import { ReplyMarkdown } from "./ReplyMarkdown";
import type { CodeActions } from "./ReplyMarkdown";

function AssistantReply({ text, onOpenArtifact, onImproveCode, onPreviewCode }: {
  text: string;
  onOpenArtifact: (artifact: ReplyArtifact) => void;
} & CodeActions) {
  const artifact = extractReplyArtifact(text);
  if (!artifact) return <ReplyMarkdown text={text} onImproveCode={onImproveCode} onPreviewCode={onPreviewCode} />;
  return <>
    <ReplyMarkdown text={artifact.reply || "He dejado el código completo en el espacio de trabajo."} />
    <button type="button" className="history-code-open" onClick={() => onOpenArtifact(artifact)}>
      <Code2 size={15} aria-hidden="true" /> Abrir implementación
    </button>
  </>;
}

export function ChatHistory({ previous, messages, historyError, onClose, onOpenArtifact, onImproveCode, onPreviewCode,
  hasEarlier, olderLoading, onLoadEarlier }: {
  previous: HistoryMessage[];
  messages: Turn[];
  historyError: string;
  onClose: () => void;
  onOpenArtifact: (artifact: ReplyArtifact) => void;
  hasEarlier?: boolean; olderLoading?: boolean; onLoadEarlier?: () => Promise<void>;
} & CodeActions) {
  const dialog = useRef<HTMLDialogElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  async function loadEarlier() {
    const element = scroll.current;
    const height = element?.scrollHeight ?? 0;
    const top = element?.scrollTop ?? 0;
    await onLoadEarlier?.();
    requestAnimationFrame(() => { if (element) element.scrollTop = top + element.scrollHeight - height; });
  }
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return <dialog ref={dialog} className="chat-history" aria-labelledby="history-title" onCancel={event => { event.preventDefault(); onClose(); }}>
    <header className="history-heading"><div><span className="message-author">HELIOS</span><h2 id="history-title">Nuestra conversación</h2></div><button className="icon-button" onClick={onClose} aria-label="Cerrar historial y seguir conversando"><X size={22} /></button></header>
    <div className="history-messages" ref={scroll}>
      {hasEarlier && <button type="button" className="history-code-open" disabled={olderLoading}
        onClick={() => void loadEarlier()}>{olderLoading ? "Cargando mensajes…" : "Cargar mensajes anteriores"}</button>}
      {historyError && <p role="status">{historyError}</p>}
      {!previous.length && !messages.length && <p className="history-empty">Aquí podrás volver a leer nuestra conversación.</p>}
      {previous.map((message, index) => <div key={`previous-${index}`} className={`history-entry ${message.role}`}><span className="message-author">{message.role === "user" ? "TÚ" : "HELIOS"}</span>{message.role === "assistant" ? <AssistantReply text={message.text} onOpenArtifact={onOpenArtifact} onImproveCode={onImproveCode} onPreviewCode={onPreviewCode} /> : <p>{message.text}</p>}</div>)}
      {messages.map(message => <div key={message.id} className="history-turn">
        <div className="history-entry user"><span className="message-author">TÚ</span><p>{message.text}</p></div>
        <div className="history-entry assistant"><span className="message-author">HELIOS</span>{message.pending
          ? <p>Helios está pensando…</p>
          : message.reply ? <AssistantReply text={message.reply} onOpenArtifact={onOpenArtifact} onImproveCode={onImproveCode} onPreviewCode={onPreviewCode} />
          : <p>{message.error || "Sin respuesta recibida."}</p>}</div>
      </div>)}
    </div>
    <footer className="history-footer"><span>Los turnos anteriores siguen aquí.</span><button onClick={onClose}>Seguir conversando</button></footer>
  </dialog>;
}
