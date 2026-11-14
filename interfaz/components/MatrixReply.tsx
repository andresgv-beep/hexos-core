"use client";

import { useEffect, useRef } from "react";
import { ReplyMarkdown } from "./ReplyMarkdown";
import { runMatrix } from "@/lib/helios/matrixEffect";

/**
 * Una respuesta que cae en cascada hasta formarse: el efecto que Helios activa con
 * [[matrix]]. Lo pinta la interfaz sobre el texto ya escrito; el modelo solo pone la
 * marca. Mientras la respuesta llega se ve la lluvia; al completarse, cada gota deja
 * en su sitio las letras por las que pasa. Al acabar queda texto normal, copiable.
 */
export function MatrixReply({ text, live, onComplete }: { text: string; live: boolean; onComplete?: () => void }) {
  const caja = useRef<HTMLDivElement>(null);
  const lienzo = useRef<HTMLCanvasElement>(null);
  const hecho = useRef(onComplete);
  useEffect(() => { hecho.current = onComplete; }, [onComplete]);
  useEffect(() => {
    const box = caja.current, canvas = lienzo.current;
    if (!box || !canvas) return;
    return runMatrix(box, canvas, live, () => hecho.current?.());
  // El texto solo se mide una vez, ya completo: mientras llega solo hay lluvia.
  }, [live]);
  return <div ref={caja} className={`matrix-reply${live ? " matrix-live" : ""}`}
    aria-label={live ? "Respuesta en generación" : undefined}>
    {/* Mientras llega no se pinta el texto: la clave cambia al completarse y React lo
        monta de cero, así los spans puestos a mano no chocan con un repintado. */}
    <div className="matrix-text" key={live ? "live" : "done"}>{!live && <ReplyMarkdown text={text} />}</div>
    {live && <span className="sr-only">{text}</span>}
    <canvas ref={lienzo} aria-hidden="true" />
  </div>;
}
