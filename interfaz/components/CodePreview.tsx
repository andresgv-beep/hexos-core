"use client";

import { useEffect, useRef } from "react";
import { MonitorUp, X } from "lucide-react";
import { previewDocument } from "@/lib/helios/preview";

export function CodePreview({ html, onClose }: { html: string; onClose: () => void }) {
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    close.current?.focus();
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [onClose]);
  return <div className="code-preview-backdrop">
    <section className="code-preview-panel" role="dialog" aria-modal="true" aria-labelledby="code-preview-title">
      <header>
        <MonitorUp size={18} aria-hidden="true" />
        <h2 id="code-preview-title">Vista previa</h2>
        <span>Aislada · sin red</span>
        <button ref={close} type="button" onClick={onClose} aria-label="Cerrar vista previa"><X size={19} /></button>
      </header>
      <iframe title="Vista previa de la interfaz generada" sandbox="allow-scripts" srcDoc={previewDocument(html)} />
    </section>
  </div>;
}
