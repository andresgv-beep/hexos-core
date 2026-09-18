"use client";

import { useState } from "react";
import { Code2, MonitorUp, Sparkles, X } from "lucide-react";
import { ReplyCode } from "./ReplyMarkdown";
import { previewDocument, type ReplyArtifact } from "@/lib/helios/preview";

export function CodeWorkspace({ artifact, busy, onClose, onImprove, onCreatePreview }: {
  artifact: ReplyArtifact;
  busy: boolean;
  onClose: () => void;
  onImprove: (code: string, language?: string) => void;
  onCreatePreview: (code: string, language?: string) => void;
}) {
  const [mode, setMode] = useState<"code" | "preview">(artifact.previewHtml ? "preview" : "code");
  return <section className="code-workspace" aria-label="Espacio de trabajo de código">
    <header className="code-workspace-heading">
      <Code2 size={18} aria-hidden="true" />
      <div><strong>Implementación</strong><small>{artifact.language || "código"}</small></div>
      <nav aria-label="Vista del trabajo">
        <button type="button" className={mode === "code" ? "active" : ""} onClick={() => setMode("code")}>
          <Code2 size={14} /> Código
        </button>
        <button type="button" className={mode === "preview" ? "active" : ""} onClick={() => setMode("preview")}>
          <MonitorUp size={14} /> Interfaz
        </button>
      </nav>
      <button type="button" className="code-workspace-close" onClick={onClose} aria-label="Cerrar espacio de código"><X size={19} /></button>
    </header>
    <div className="code-workspace-body">
      {mode === "code" ? <ReplyCode code={artifact.code} language={artifact.language} onImprove={onImprove} />
        : artifact.previewHtml
          ? <iframe title="Vista previa de la interfaz generada" sandbox="allow-scripts" srcDoc={previewDocument(artifact.previewHtml)} />
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
