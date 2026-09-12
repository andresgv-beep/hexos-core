"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

/** Visual reveal for the current complete-response HTTP contract, not token streaming. */
export function ProgressiveReply({ text }: { text: string }) {
  const characters = useMemo(() => Array.from(text), [text]);
  const [visible, setVisible] = useState(0);
  const paragraph = useRef<HTMLParagraphElement>(null);
  const follow = useRef(true);
  const finish = useRef<() => void>(() => {});
  useEffect(() => {
    let cursor = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    function showAll() {
      clearTimeout(timer);
      cursor = characters.length;
      setVisible(cursor);
    }
    finish.current = showAll;
    function step() {
      if (document.hidden) return;
      if (preference.matches) { showAll(); return; }
      const container = paragraph.current?.closest(".window-content");
      if (container) follow.current = container.scrollHeight - container.scrollTop - container.clientHeight < 60;
      cursor = Math.min(cursor + 3, characters.length);
      setVisible(cursor);
      if (cursor < characters.length) {
        const pause = /[.!?\n]/.test(characters[cursor - 1]) ? 140 : 45;
        timer = setTimeout(step, pause);
      }
    }
    function resume() {
      clearTimeout(timer);
      if (!document.hidden && cursor < characters.length) timer = setTimeout(step, 45);
    }
    function reduce() { if (preference.matches) showAll(); }
    timer = setTimeout(step, 45);
    document.addEventListener("visibilitychange", resume);
    preference.addEventListener("change", reduce);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", resume);
      preference.removeEventListener("change", reduce);
    };
  }, [characters]);
  useLayoutEffect(() => {
    const container = paragraph.current?.closest(".window-content");
    if (container && follow.current) container.scrollTop = container.scrollHeight;
  }, [visible]);
  const complete = visible >= characters.length;
  return <>
    <p ref={paragraph} className="helios-answer"><span className="sr-only">{text}</span><span aria-hidden="true">{characters.slice(0, visible).join("")}{!complete && <span className="reply-cursor" />}</span></p>
    {!complete && <button className="reveal-all" onClick={() => finish.current()}>Mostrar todo</button>}
  </>;
}
