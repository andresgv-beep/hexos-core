"use client";

import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import type { HistoryMessage } from "@/lib/helios/hexos";
import type { MessageWindow } from "./FloatingMessage";

export function ChatHistory({ previous, messages, historyError, onClose }: {
  previous: HistoryMessage[];
  messages: MessageWindow[];
  historyError: string;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return <dialog ref={dialog} className="chat-history" aria-labelledby="history-title" onCancel={event => { event.preventDefault(); onClose(); }}>
    <header className="history-heading"><div><span className="message-author">HELIOS</span><h2 id="history-title">Nuestra conversación</h2></div><button className="icon-button" onClick={onClose} aria-label="Cerrar historial y seguir conversando"><X size={22} /></button></header>
    <div className="history-messages">
      {historyError && <p role="status">{historyError}</p>}
      {!previous.length && !messages.length && <p className="history-empty">Aquí podrás volver a leer nuestra conversación.</p>}
      {previous.map((message, index) => <div key={`previous-${index}`} className={`history-entry ${message.role}`}><span className="message-author">{message.role === "user" ? "TÚ" : "HELIOS"}</span><p>{message.text}</p></div>)}
      {messages.map(message => <div key={message.id} className="history-turn">
        <div className="history-entry user"><span className="message-author">TÚ</span><p>{message.text}</p></div>
        <div className="history-entry assistant"><span className="message-author">HELIOS</span><p>{message.pending ? "Helios está pensando…" : message.reply || message.error || "Sin respuesta recibida."}</p></div>
      </div>)}
    </div>
    <footer className="history-footer"><span>Los mensajes absorbidos siguen aquí.</span><button onClick={onClose}>Seguir conversando</button></footer>
  </dialog>;
}
