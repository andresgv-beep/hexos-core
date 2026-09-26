"use client";
import { useEffect, useRef, useState } from "react";

// Ancho de escritorio al que se dibuja una maqueta. Helios las hace para
// pantalla completa; en el panel lateral (~550 px) solo se veía la columna
// izquierda. Por debajo de este ancho se reduce entera, como una miniatura.
export const PREVIEW_DESIGN_WIDTH = 1280;

export function previewScale(width: number, design = PREVIEW_DESIGN_WIDTH): number {
  return width > 0 && width < design ? width / design : 1;
}

export function PreviewFrame({ title, srcDoc }: { title: string; srcDoc: string }) {
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const element = box.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) =>
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const scale = previewScale(size.width);
  const fitted = scale < 1 ? { width: PREVIEW_DESIGN_WIDTH, height: size.height / scale,
    transform: `scale(${scale})`, transformOrigin: "0 0" } : { width: "100%", height: "100%" };
  return <div ref={box} className="preview-fit">
    <iframe title={title} sandbox="allow-scripts" srcDoc={srcDoc} style={fitted} />
  </div>;
}
