"use client";

import { useEffect, useRef, useState } from "react";
import { ProgressiveReply } from "./ProgressiveReply";
import { ReplyMarkdown } from "./ReplyMarkdown";
import type { CodeActions } from "./ReplyMarkdown";

export interface Turn {
  id: number;
  text: string;
  reply?: string;
  error?: string;
  pending?: boolean;
  preview?: string;
  streamed?: boolean;
  generationStatus?: string;
  /** Lo que Helios anuncia que va a hacer, mientras lo hace. Palabras suyas. */
  progress?: string[];
  /** Solo cuando la respuesta NO se sostiene entera en lo comprobado. */
  caveat?: { note: string; tools: string[] };
}

const SALIDA_MS = 420;

/** La conversación, bajo el logo y sin marco: un turno a la vez.
 *
 *  Un turno entra, el anterior se va. Lo que se fue no se pierde —está en el
 *  historial, tras la esfera—, pero deja de ocupar la pantalla, porque lo que
 *  uno quiere tener delante son las notas y los informes, no lo ya leído. */
export function ConversationStream({ turn, onReplyComplete, onImproveCode, onPreviewCode }:
  { turn: Turn | null; onReplyComplete?: (id: number) => void } & CodeActions) {
  const [saliente, setSaliente] = useState<Turn | null>(null);
  const anterior = useRef<Turn | null>(null);
  useEffect(() => {
    const previo = anterior.current;
    anterior.current = turn;
    if (!previo || !turn || previo.id === turn.id) return;
    setSaliente(previo);
    const temporizador = setTimeout(() => setSaliente(null), SALIDA_MS);
    return () => clearTimeout(temporizador);
  }, [turn]);

  if (!turn && !saliente) return null;
  return <section className="conversation-stream" aria-label="Conversación con Helios" aria-live="polite">
    {saliente && <TurnoVisible turn={saliente} saliendo onImproveCode={onImproveCode} onPreviewCode={onPreviewCode} />}
    {turn && <TurnoVisible key={turn.id} turn={turn} onReplyComplete={onReplyComplete}
      onImproveCode={onImproveCode} onPreviewCode={onPreviewCode} />}
  </section>;
}

export function TurnoVisible({ turn, saliendo, onReplyComplete, onImproveCode, onPreviewCode }:
  { turn: Turn; saliendo?: boolean; onReplyComplete?: (id: number) => void } & CodeActions) {
  return <article className={`stream-turn${saliendo ? " leaving" : ""}`} aria-hidden={saliendo || undefined}>
    <p className="stream-question"><span className="message-author">TÚ</span>{turn.text}</p>
    <div className="stream-body">
      {!!turn.progress?.length && <ul className="reply-progress">
        {turn.progress.map((linea, i) => <li key={i}>{linea}</li>)}
      </ul>}
      {turn.pending && <p className="reply-status" role="status">
        {turn.generationStatus || (turn.progress?.length ? "Helios está en ello…" : "Helios está pensando…")}
      </p>}
      {(turn.preview || turn.reply) && (saliendo
        ? <ReplyMarkdown text={turn.reply || turn.preview || ""} onImproveCode={onImproveCode} onPreviewCode={onPreviewCode} />
        : <div className={turn.pending ? "reply-preview" : undefined}
            aria-label={turn.pending ? "Respuesta en generación" : undefined}>
          <ProgressiveReply text={turn.reply || turn.preview || ""} live={Boolean(turn.pending)}
            onComplete={() => onReplyComplete?.(turn.id)}
            onImproveCode={onImproveCode} onPreviewCode={onPreviewCode} />
        </div>)}
      {/* El reparo viaja pegado a la respuesta: es lo que evita creerse lo que no pasó. */}
      {turn.caveat && <p className="reply-caveat" role="note">
        {turn.caveat.note}
        {turn.caveat.tools.length > 0 && <> Sin comprobar: {turn.caveat.tools.join(", ")}.</>}
      </p>}
      {turn.error && <p className="reply-status" role="alert">{turn.error}</p>}
    </div>
  </article>;
}
