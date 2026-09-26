"use client";

import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { Code2, GripHorizontal, MonitorUp, RotateCcw, Sparkles, X, Maximize2, Minimize2 } from "lucide-react";
import { ReplyCode } from "./ReplyMarkdown";
import { type ReplyArtifact } from "@/lib/helios/preview";
import { usePreviewDocument } from "./usePreviewDocument";
import { PreviewFrame } from "./PreviewFrame";

export function CodeWorkspace({ artifact, busy, canUndo, onUndo, onClose, onImprove, onCreatePreview, fixedMode }: {
  fixedMode?: "code" | "preview";
  artifact: ReplyArtifact;
  busy: boolean;
  canUndo: boolean;
  onUndo: () => void;
  onClose: () => void;
  onImprove: (code: string, language?: string) => void;
  onCreatePreview: (code: string, language?: string) => void;
}) {
  const artifactKey = `${artifact.code}\u0000${artifact.previewHtml ?? ""}`;
  const previewSource = usePreviewDocument(artifact.previewHtml);
  const defaultMode = artifact.previewHtml ? "preview" : "code";
  const [view, setView] = useState<{ artifactKey: string; mode: "code" | "preview" }>(
    { artifactKey, mode: defaultMode });
  const mode = fixedMode ?? (view.artifactKey === artifactKey ? view.mode : defaultMode);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [maximized, setMaximized] = useState(false);
  const panel = useRef<HTMLElement>(null);
  const drag = useRef<{ pointer: number; x: number; y: number; originX: number; originY: number } | null>(null);
  function move(x: number, y: number) {
    const bounds = panel.current?.getBoundingClientRect();
    if (!bounds) return;
    const baseLeft = bounds.left - offset.x;
    const baseTop = bounds.top - offset.y;
    const margin = 12;
    setOffset({
      x: Math.max(margin - baseLeft, Math.min(window.innerWidth - margin - bounds.width - baseLeft, x)),
      y: Math.max(margin - baseTop, Math.min(window.innerHeight - margin - bounds.height - baseTop, y)),
    });
  }
  function beginMove(event: PointerEvent<HTMLButtonElement>) {
    if (maximized || event.button !== 0 || window.matchMedia("(max-width: 700px)").matches) return;
    drag.current = { pointer: event.pointerId, x: event.clientX, y: event.clientY,
      originX: offset.x, originY: offset.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function keyboardMove(event: KeyboardEvent<HTMLButtonElement>) {
    const direction: Record<string, [number, number]> = {
      ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1],
    };
    const delta = direction[event.key];
    if (maximized || !delta || window.matchMedia("(max-width: 700px)").matches) return;
    event.preventDefault();
    const step = event.shiftKey ? 40 : 12;
    move(offset.x + delta[0] * step, offset.y + delta[1] * step);
  }
  return <section ref={panel} className={`code-workspace${maximized ? " maximized" : ""}`} aria-label="Espacio de trabajo de código"
    style={{ transform: maximized ? undefined : `translate3d(${offset.x}px, ${offset.y}px, 0)` }}>
    <header className="code-workspace-heading">
      <button type="button" className="code-workspace-drag" aria-label="Mover espacio de código con las flechas"
        title="Arrastra para mover" onPointerDown={beginMove} onPointerMove={event => {
          const current = drag.current;
          if (current?.pointer === event.pointerId) move(current.originX + event.clientX - current.x,
            current.originY + event.clientY - current.y);
        }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}
        onLostPointerCapture={() => { drag.current = null; }} onKeyDown={keyboardMove}>
        <Code2 size={18} aria-hidden="true" />
        <span><strong>Implementación</strong><small>{artifact.language || "código"} · pide cambios en el chat</small></span>
        <GripHorizontal size={15} aria-hidden="true" />
      </button>
      {!fixedMode && <nav aria-label="Vista del trabajo">
        {canUndo && <button type="button" onClick={onUndo} title="Recuperar la versión anterior">
          <RotateCcw size={14} /> Deshacer
        </button>}
        <button type="button" className={mode === "code" ? "active" : ""} onClick={() => setView({ artifactKey, mode: "code" })}>
          <Code2 size={14} /> Código
        </button>
        <button type="button" className={mode === "preview" ? "active" : ""} onClick={() => setView({ artifactKey, mode: "preview" })}>
          <MonitorUp size={14} /> Interfaz
        </button>
      </nav>}
      {!fixedMode && <button type="button" className="code-workspace-close"
        aria-label={maximized ? "Restaurar tamaño" : "Maximizar implementación"}
        onClick={() => setMaximized(value => !value)}>
        {maximized ? <Minimize2 size={19} /> : <Maximize2 size={19} />}
      </button>}
      <button type="button" className="code-workspace-close" onClick={onClose} aria-label="Cerrar espacio de código"><X size={19} /></button>
    </header>
    <div className="code-workspace-body">
      {mode === "code" ? <ReplyCode code={artifact.code} language={artifact.language} onImprove={onImprove} />
        : artifact.previewHtml
          ? <PreviewFrame title="Vista previa de la interfaz generada" srcDoc={previewSource} />
          : <div className="code-preview-empty">
              <MonitorUp size={38} aria-hidden="true" />
              <h3>Prepara una vista de esta interfaz</h3>
              <p>Helios convertirá el componente en una maqueta autónoma y la abrirá aquí.</p>
              <button type="button" disabled={busy} onClick={() => onCreatePreview(artifact.code, artifact.language)}>
                <Sparkles size={15} /> {busy ? "Preparando…" : "Crear interfaz"}
              </button>
            </div>}
    </div>
  </section>;
}
