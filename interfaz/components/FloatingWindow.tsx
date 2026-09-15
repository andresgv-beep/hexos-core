"use client";

import { useEffect, useRef, type ReactNode, type RefObject, type KeyboardEvent, type PointerEvent } from "react";
import { GripHorizontal, Minus, X } from "lucide-react";

export interface WindowPlacement {
  id: string;
  slot: number;
  x: number;
  y: number;
  minimized: boolean;
  absorbing?: boolean;
}

/** La ventana, sin saber qué lleva dentro.
 *
 *  Antes era la conversación y solo la conversación. La conversación es efímera
 *  —un turno y se va— y lo que uno quiere tener delante y mover son las notas y
 *  los informes, así que la ventana se queda para eso y el chat se fue a la
 *  columna. Arrastrar, minimizar hacia la esfera y cerrar no cambian. */
export function FloatingWindow({ placement, label, title, front, orbTarget, onAbsorbed,
                                onMove, onMinimize, onClose, onFocus, actions, children }: {
  placement: WindowPlacement;
  label: string;
  title: string;
  front: boolean;
  orbTarget?: RefObject<HTMLButtonElement | null>;
  onAbsorbed?: (id: string) => void;
  onMove: (id: string, x: number, y: number) => void;
  onMinimize: (id: string) => void;
  onClose: (id: string) => void;
  onFocus: (id: string) => void;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const card = useRef<HTMLElement>(null);
  const drag = useRef<{ pointer: number; x: number; y: number; originX: number; originY: number } | null>(null);
  useEffect(() => {
    if (!placement.absorbing || !onAbsorbed) return;
    const element = card.current;
    const target = orbTarget?.current;
    if (!element || !target || window.matchMedia("(prefers-reduced-motion: reduce)").matches || !element.animate) {
      onAbsorbed(placement.id);
      return;
    }
    const start = element.getBoundingClientRect();
    const end = target.getBoundingClientRect();
    const x = end.left + end.width / 2;
    const y = end.top + end.height / 2;
    const savedStyle = element.style.cssText;
    element.style.position = "fixed";
    element.style.setProperty("transform", "none", "important");
    // El vuelo fija left/top ya medidos, así que cualquier desplazamiento previo
    // sobra. Sin esto el centrado desviaba la ventana media anchura al arrancar.
    element.style.setProperty("translate", "none", "important");
    element.style.margin = "0";
    element.style.right = "auto";
    element.style.bottom = "auto";
    element.style.left = `${start.left}px`;
    element.style.top = `${start.top}px`;
    element.style.width = `${start.width}px`;
    element.style.height = `${start.height}px`;
    const glass = element.querySelector<HTMLElement>(".window-glass")!;
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
    flight.onfinish = () => onAbsorbed(placement.id);
    return () => {
      flight.onfinish = null;
      flight.cancel(); collapse.cancel(); spark.remove();
      element.style.cssText = savedStyle;
    };
  }, [placement.absorbing, placement.id, onAbsorbed, orbTarget]);

  function move(x: number, y: number) {
    const element = card.current;
    if (!element || !element.parentElement) return;
    const area = element.parentElement.getBoundingClientRect();
    const bounds = element.getBoundingClientRect();
    const baseX = bounds.left - area.left - placement.x;
    const baseY = bounds.top - area.top - placement.y;
    onMove(placement.id,
      Math.max(-baseX, Math.min(area.width - bounds.width - baseX, x)),
      Math.max(-baseY, Math.min(area.height - bounds.height - baseY, y)));
  }
  function begin(event: PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0 || window.matchMedia("(max-width: 700px)").matches) return;
    onFocus(placement.id);
    drag.current = { pointer: event.pointerId, x: event.clientX, y: event.clientY, originX: placement.x, originY: placement.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function keyboardMove(event: KeyboardEvent<HTMLButtonElement>) {
    const directions: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    const direction = directions[event.key];
    if (!direction || window.matchMedia("(max-width: 700px)").matches) return;
    event.preventDefault();
    const step = event.shiftKey ? 40 : 12;
    move(placement.x + direction[0] * step, placement.y + direction[1] * step);
  }
  return <article ref={card} className={`message-window slot-${placement.slot}${placement.absorbing ? " absorbing" : ""}`}
    inert={placement.absorbing || undefined}
    style={{ transform: `translate(${placement.x}px, ${placement.y}px)`, zIndex: front ? 5 : 2 }}
    aria-label={title} onPointerDown={() => onFocus(placement.id)} onFocus={() => onFocus(placement.id)}>
    <div className="window-glass">
      <header className="window-heading">
        <button className="window-drag" aria-label={`Mover ${title} con las flechas`} onPointerDown={begin} onPointerMove={event => {
          const current = drag.current;
          if (current && current.pointer === event.pointerId) move(current.originX + event.clientX - current.x, current.originY + event.clientY - current.y);
        }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }} onLostPointerCapture={() => { drag.current = null; }} onKeyDown={keyboardMove}>
          <span className="window-dot" /><span>{label}</span><GripHorizontal size={16} />
        </button>
        {actions}
        <button className="icon-button" aria-label={`Minimizar ${title}`} onClick={() => onMinimize(placement.id)}><Minus size={16} /></button>
        <button className="icon-button" aria-label={`Cerrar ${title}`} onClick={() => onClose(placement.id)}><X size={16} /></button>
      </header>
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Con teclado hay que poder enfocar la región para desplazar textos largos. */}
      <div className="window-content" role="region" tabIndex={0} aria-label={title}>{children}</div>
    </div>
  </article>;
}
