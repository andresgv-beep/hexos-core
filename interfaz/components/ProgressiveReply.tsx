"use client";

import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { parseReply, regroup, tokenize, type Token } from "@/lib/helios/markdown";
import { ReplyCode } from "./ReplyMarkdown";
import type { CodeActions } from "./ReplyMarkdown";

/** Suaviza las actualizaciones progresivas del servidor: palabras en prosa y
 *  fragmentos pequeños en código, manteniendo un cursor visual independiente. */
export function ProgressiveReply({ text, live = false, onComplete, onPreviewCode }: {
  text: string; live?: boolean; onComplete?: () => void;
} & CodeActions) {
  // Helios escribe en Markdown: se interpreta antes de revelar, para que una lista
  // sea una lista y no un párrafo con asteriscos dentro.
  const words = useMemo(() => tokenize(parseReply(text)), [text]);
  const [visible, setVisible] = useState(0);
  const wordsRef = useRef(words);
  const cursor = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const wake = useRef<() => void>(() => {});
  const paragraph = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const finish = useRef<() => void>(() => {});
  const completionReported = useRef(false);
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    function showAll() {
      clearTimeout(timer.current);
      timer.current = undefined;
      cursor.current = wordsRef.current.length;
      setVisible(cursor.current);
    }
    finish.current = showAll;
    function step() {
      timer.current = undefined;
      if (document.hidden) return;
      if (preference.matches) { showAll(); return; }
      const container = paragraph.current?.closest(".window-content, .stream-body");
      if (container) follow.current = container.scrollHeight - container.scrollTop - container.clientHeight < 60;
      // De dos en dos: una palabra y el espacio que la sigue.
      cursor.current = Math.min(cursor.current + 2, wordsRef.current.length);
      setVisible(cursor.current);
      if (cursor.current < wordsRef.current.length) {
        const anterior = wordsRef.current[cursor.current - 2]?.text ?? "";
        const code = wordsRef.current[cursor.current - 2]?.kind === "code";
        timer.current = setTimeout(step, !code && /[.!?]$/.test(anterior) ? 190 : 52);
      }
    }
    function resume(delay = 52) {
      clearTimeout(timer.current);
      timer.current = undefined;
      if (!document.hidden && cursor.current < wordsRef.current.length)
        timer.current = setTimeout(step, delay);
    }
    wake.current = () => { if (!timer.current) resume(); };
    function reduce() { if (preference.matches) showAll(); }
    resume();
    const visibility = () => resume();
    document.addEventListener("visibilitychange", visibility);
    preference.addEventListener("change", reduce);
    return () => {
      clearTimeout(timer.current);
      timer.current = undefined;
      document.removeEventListener("visibilitychange", visibility);
      preference.removeEventListener("change", reduce);
    };
  }, []);
  // El objetivo crece con los fragmentos del motor, pero el cursor visual no se
  // reinicia. Así recepción y presentación tienen ritmos independientes.
  useEffect(() => {
    wordsRef.current = words;
    if (cursor.current > words.length) {
      cursor.current = words.length;
      setVisible(words.length);
    }
    wake.current();
  }, [words]);
  useLayoutEffect(() => {
    const container = paragraph.current?.closest(".window-content, .stream-body");
    if (container && follow.current) container.scrollTop = container.scrollHeight;
  }, [visible]);
  const complete = visible >= words.length;
  useEffect(() => {
    if (complete && !live && !completionReported.current) {
      completionReported.current = true;
      onComplete?.();
    }
  }, [complete, live, onComplete]);
  return <>
    <div ref={paragraph} className="helios-answer">
      {/* El texto entero para quien usa lector de pantalla. No se puede seleccionar:
          si no, copiar la respuesta la copiaba dos veces. */}
      {!complete && <span className="sr-only">{text}</span>}
      <div aria-hidden={!complete}>{regroup(words.slice(0, visible)).map(bloque => {
        if (bloque.kind === "code") {
          const codigo = bloque.lines.map(linea => linea.parts.map(parte => parte.text).join("")).join("\n");
          return <ReplyCode key={bloque.index} code={codigo} language={bloque.language} copy={complete}
            onPreview={complete && !live ? onPreviewCode : undefined} />;
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
