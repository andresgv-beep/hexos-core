"use client";

import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { parseReply, regroup, tokenize, type Token } from "@/lib/helios/markdown";
import { ReplyCode } from "./ReplyMarkdown";
import type { CodeActions } from "./ReplyMarkdown";

/** Revelado visual del contrato HTTP actual —la respuesta llega entera—, no
 *  streaming de tokens.
 *
 *  Por palabras y con desvanecido, no letra a letra: carácter a carácter parecía
 *  una máquina de escribir, y lo que se quiere es que el texto aparezca. Cada
 *  palabra entra con su propia animación al montarse. */
export function ProgressiveReply({ text, onComplete, onImproveCode, onPreviewCode }: {
  text: string; onComplete?: () => void;
} & CodeActions) {
  // Helios escribe en Markdown: se interpreta antes de revelar, para que una lista
  // sea una lista y no un párrafo con asteriscos dentro.
  const words = useMemo(() => tokenize(parseReply(text)), [text]);
  const [visible, setVisible] = useState(0);
  const paragraph = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const finish = useRef<() => void>(() => {});
  const completionReported = useRef(false);
  useEffect(() => {
    let cursor = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    function showAll() {
      clearTimeout(timer);
      cursor = words.length;
      setVisible(cursor);
    }
    finish.current = showAll;
    function step() {
      if (document.hidden) return;
      if (preference.matches) { showAll(); return; }
      const container = paragraph.current?.closest(".window-content, .stream-body");
      if (container) follow.current = container.scrollHeight - container.scrollTop - container.clientHeight < 60;
      // De dos en dos: una palabra y el espacio que la sigue.
      cursor = Math.min(cursor + 2, words.length);
      setVisible(cursor);
      if (cursor < words.length) {
        const anterior = words[cursor - 2]?.text ?? "";
        timer = setTimeout(step, /[.!?]$/.test(anterior) ? 190 : 52);
      }
    }
    function resume() {
      clearTimeout(timer);
      if (!document.hidden && cursor < words.length) timer = setTimeout(step, 52);
    }
    function reduce() { if (preference.matches) showAll(); }
    timer = setTimeout(step, 52);
    document.addEventListener("visibilitychange", resume);
    preference.addEventListener("change", reduce);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", resume);
      preference.removeEventListener("change", reduce);
    };
  }, [words]);
  useLayoutEffect(() => {
    const container = paragraph.current?.closest(".window-content, .stream-body");
    if (container && follow.current) container.scrollTop = container.scrollHeight;
  }, [visible]);
  const complete = visible >= words.length;
  useEffect(() => {
    if (complete && !completionReported.current) {
      completionReported.current = true;
      onComplete?.();
    }
  }, [complete, onComplete]);
  return <>
    <div ref={paragraph} className="helios-answer">
      {/* El texto entero para quien usa lector de pantalla. No se puede seleccionar:
          si no, copiar la respuesta la copiaba dos veces. */}
      {!complete && <span className="sr-only">{text}</span>}
      <div aria-hidden={!complete}>{regroup(words.slice(0, visible)).map(bloque => {
        if (bloque.kind === "code") {
          const codigo = bloque.lines.map(linea => linea.parts.map(parte => parte.text).join("")).join("\n");
          return <ReplyCode key={bloque.index} code={codigo} language={bloque.language} copy={complete}
            onImprove={complete ? onImproveCode : undefined} onPreview={complete ? onPreviewCode : undefined}>
            {!complete && bloque.lines.map((linea, i) => <Fragment key={linea.index}>
              {i > 0 && "\n"}
              {linea.parts.map((parte, j) => <Palabra key={j} token={parte} />)}
            </Fragment>)}
          </ReplyCode>;
        }
        const lineas = bloque.lines.map(linea =>
          <Fragment key={linea.index}>{linea.parts.map((parte, i) =>
            <Palabra key={i} token={parte} />)}</Fragment>);
        if (bloque.kind === "p") return <p key={bloque.index}>{lineas}</p>;
        const Lista = bloque.kind === "ol" ? "ol" : "ul";
        return <Lista key={bloque.index}>{bloque.lines.map(linea =>
          <li key={linea.index}>{linea.parts.map((parte, i) => <Palabra key={i} token={parte} />)}</li>)}</Lista>;
      })}</div>
    </div>
    {!complete && <button className="reveal-all" onClick={() => finish.current()}>Mostrar todo</button>}
  </>;
}

function Palabra({ token }: { token: Token }) {
  if (/^\s+$/.test(token.text)) return token.text;
  const contenido = token.code ? <code>{token.text}</code>
    : token.bold ? <strong>{token.text}</strong> : token.text;
  return <span className="reveal-word">{contenido}</span>;
}
