"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

/** Revelado visual del contrato HTTP actual —la respuesta llega entera—, no
 *  streaming de tokens.
 *
 *  Por palabras y con desvanecido, no letra a letra: carácter a carácter parecía
 *  una máquina de escribir, y lo que se quiere es que el texto aparezca. Cada
 *  palabra entra con su propia animación al montarse. */
export function ProgressiveReply({ text, onComplete }: { text: string; onComplete?: () => void }) {
  // Se parte conservando los espacios, para no rehacer el texto al juntarlo.
  const words = useMemo(() => text.split(/(\s+)/), [text]);
  const [visible, setVisible] = useState(0);
  const paragraph = useRef<HTMLParagraphElement>(null);
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
        const anterior = words[cursor - 2] ?? "";
        timer = setTimeout(step, /[.!?\n]$/.test(anterior) ? 190 : 52);
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
    <p ref={paragraph} className="helios-answer">
      <span className="sr-only">{text}</span>
      <span aria-hidden="true">{words.slice(0, visible).map((palabra, i) =>
        /^\s+$/.test(palabra)
          ? palabra
          : <span key={i} className="reveal-word">{palabra}</span>)}</span>
    </p>
    {!complete && <button className="reveal-all" onClick={() => finish.current()}>Mostrar todo</button>}
  </>;
}
