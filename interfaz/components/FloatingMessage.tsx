"use client";

import { useEffect, useRef, type RefObject, type KeyboardEvent, type PointerEvent } from "react";
import { GripHorizontal, Minus, X } from "lucide-react";
import { ProgressiveReply } from "./ProgressiveReply";

export interface MessageWindow {
  id: number;
  text: string;
  reply?: string;
  error?: string;
  pending?: boolean;
  absorbing?: boolean;
  slot: number;
  x: number;
  y: number;
  minimized: boolean;
}

export function FloatingMessage({ message, onMove, onMinimize, onClose, onFocus, front, orbTarget, onAbsorbed }: {
  message: MessageWindow;
  orbTarget?: RefObject<HTMLButtonElement | null>;
  onAbsorbed?: (id: number) => void;
  onMove: (id: number, x: number, y: number) => void;
  onMinimize: (id: number) => void;
  onClose: (id: number) => void;
  onFocus: (id: number) => void;
  front: boolean;
}) {
  const card = useRef<HTMLElement>(null);
  const drag = useRef<{ id: number; x: number; y: number; originX: number; originY: number } | null>(null);
  useEffect(() => {
    if (!message.absorbing || !onAbsorbed) return;
    const element = card.current;
    const target = orbTarget?.current;
    if (!element || !target || window.matchMedia("(prefers-reduced-motion: reduce)").matches || !element.animate) {
      onAbsorbed(message.id);
      return;
    }
    const start = element.getBoundingClientRect();
    const end = target.getBoundingClientRect();
    // Measure the actual dragged card and the sphere centre, including mobile layout.
    const x = end.left + end.width / 2;
    const y = end.top + end.height / 2;
    const savedStyle = element.style.cssText;
    element.style.position = "fixed";
    element.style.setProperty("transform", "none", "important");
    element.style.margin = "0";
    element.style.right = "auto";
    element.style.bottom = "auto";
    element.style.left = `${start.left}px`;
    element.style.top = `${start.top}px`;
    element.style.width = `${start.width}px`;
    element.style.height = `${start.height}px`;
    const glass = element.querySelector<HTMLElement>(".window-glass")!;
    // Shrink the original glass without stretching it or filling a large oval.
    const collapse = glass.animate([
      { transform: "scale(1)", opacity: 1, borderRadius: "17px" },
      { transform: "scale(.18)", opacity: .5, borderRadius: "24px", offset: .7 },
      { transform: "scale(.035)", opacity: 0, borderRadius: "50%" },
    ], { duration: 340, easing: "cubic-bezier(.4,0,.3,1)", fill: "forwards" });
    const spark = document.createElement("div");
    spark.className = "absorption-spark";
    spark.setAttribute("aria-hidden", "true");
    spark.style.left = `${start.left + start.width / 2 - 9}px`;
    spark.style.top = `${start.top + start.height / 2 - 9}px`;
    document.body.appendChild(spark);
    const dx = x - (start.left + start.width / 2);
    const dy = y - (start.top + start.height / 2);
    const flight = spark.animate([
      { transform: "translate(0, 0) scale(.4)", opacity: 0, offset: 0 },
      { transform: "translate(0, 0) scale(.4)", opacity: 0, offset: .18 },
      { transform: "translate(0, 0) scale(1)", opacity: 1, offset: .34 },
      { transform: `translate(${dx * .45}px, ${dy * .45 - 28}px) scale(.8)`, opacity: .9, offset: .65 },
      { transform: `translate(${dx}px, ${dy}px) scale(.12)`, opacity: 0, offset: 1 },
    ], { duration: 1050, easing: "cubic-bezier(.4,0,.25,1)", fill: "forwards" });
    flight.onfinish = () => onAbsorbed(message.id);
    return () => {
      flight.onfinish = null;
      flight.cancel(); collapse.cancel(); spark.remove();
      element.style.cssText = savedStyle;
    };
  }, [message.absorbing, message.id, onAbsorbed, orbTarget]);
  function move(x: number, y: number) {
    const element = card.current;
    if (!element || !element.parentElement) return;
    const area = element.parentElement.getBoundingClientRect();
    const bounds = element.getBoundingClientRect();
    const baseX = bounds.left - area.left - message.x;
    const baseY = bounds.top - area.top - message.y;
    onMove(message.id,
      Math.max(-baseX, Math.min(area.width - bounds.width - baseX, x)),
      Math.max(-baseY, Math.min(area.height - bounds.height - baseY, y)));
  }
  function begin(event: PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0 || window.matchMedia("(max-width: 700px)").matches) return;
    onFocus(message.id);
    drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, originX: message.x, originY: message.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function keyboardMove(event: KeyboardEvent<HTMLButtonElement>) {
    const directions: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    const direction = directions[event.key];
    if (!direction || window.matchMedia("(max-width: 700px)").matches) return;
    event.preventDefault();
    const step = event.shiftKey ? 40 : 12;
    move(message.x + direction[0] * step, message.y + direction[1] * step);
  }
  return <article ref={card} className={`message-window slot-${message.slot}${message.absorbing ? " absorbing" : ""}`} inert={message.absorbing || undefined} style={{ transform: `translate(${message.x}px, ${message.y}px)`, zIndex: front ? 5 : 2 }} aria-label={`Conversación ${message.id}`} onPointerDown={() => onFocus(message.id)} onFocus={() => onFocus(message.id)}>
    <div className="window-glass">
      <header className="window-heading">
        <button className="window-drag" aria-label={`Mover ventana ${message.id} con las flechas`} onPointerDown={begin} onPointerMove={event => {
          const current = drag.current;
          if (current && current.id === event.pointerId) move(current.originX + event.clientX - current.x, current.originY + event.clientY - current.y);
        }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }} onLostPointerCapture={() => { drag.current = null; }} onKeyDown={keyboardMove}>
          <span className="window-dot" /><span>HELIOS · {String(message.id).padStart(2, "0")}</span><GripHorizontal size={16} />
        </button>
        <button className="icon-button" aria-label={`Minimizar conversación ${message.id}`} onClick={() => onMinimize(message.id)}><Minus size={16} /></button>
        <button className="icon-button" aria-label={`Cerrar conversación ${message.id}`} onClick={() => onClose(message.id)}><X size={16} /></button>
      </header>
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users need to focus this region to scroll long messages. */}
      <div className="window-content" role="region" tabIndex={0} aria-label="Mensajes">
        {message.pending && <p className="reply-status" role="status">Helios está pensando…</p>}
        {message.reply && <ProgressiveReply key={message.reply} text={message.reply} />}
        {message.error && <p className="reply-status" role="alert">{message.error}</p>}
        <details className="original-message"><summary>Tu mensaje</summary><p>{message.text}</p></details>
      </div>
    </div>
  </article>;
}
