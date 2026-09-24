"use client";
import { useState } from "react";
import { Maximize2, RotateCcw } from "lucide-react";
import { ReplyCode } from "./ReplyMarkdown";
import { NasFileViewer } from "./NasFileViewer";
import { previewDocument, type ReplyArtifact } from "@/lib/helios/preview";

type Tab = "code" | "preview" | "nas";
export function ContentDock({ artifact, fileRequest, busy, canUndo, onUndo, onExpandCode, onExpandFile, onImprove, onPreview }: {
  artifact: ReplyArtifact | null; fileRequest: { id?: string } | null; busy: boolean;
  canUndo: boolean; onUndo: () => void; onExpandCode: () => void; onExpandFile: (id?: string) => void;
  onImprove: (code: string, language?: string) => void; onPreview: (code: string, language?: string) => void;
}) {
  const initialTab: Tab = fileRequest ? "nas" : artifact?.previewHtml ? "preview" : "code";
  const [selection, setSelection] = useState({ tab: initialTab, nasVisited: initialTab === "nas", artifact, fileRequest });
  if (selection.artifact !== artifact || selection.fileRequest !== fileRequest) {
    const nextTab: Tab = fileRequest && selection.fileRequest !== fileRequest ? "nas"
      : artifact && selection.artifact !== artifact ? (artifact.previewHtml ? "preview" : "code") : selection.tab;
    setSelection({ tab: nextTab, nasVisited: selection.nasVisited || nextTab === "nas", artifact, fileRequest });
  }
  const { tab, nasVisited } = selection;
  function setTab(next: Tab) { setSelection(current => ({ ...current, tab: next, nasVisited: current.nasVisited || next === "nas" })); }
  const tabs: { id: Tab; label: string }[] = [{ id: "code", label: "Código" }, { id: "preview", label: "Interfaz" }, { id: "nas", label: "NAS" }];
  return <section className="hud-content-dock" aria-label="Visor de contenido">
    <nav className="hud-content-tabs" aria-label="Tipo de contenido">{tabs.map(item =>
      <button key={item.id} type="button" aria-pressed={tab === item.id} onClick={() => setTab(item.id)}>{item.label}</button>)}
      {tab !== "nas" && artifact && <button type="button" className="hud-expand" title="Abrir en ventana" aria-label="Abrir implementación en ventana" onClick={onExpandCode}><Maximize2 size={16} /></button>}
    </nav>
    <div className="hud-content-body">
      {(nasVisited || tab === "nas") && <div className="hud-nas-pane" hidden={tab !== "nas"}><NasFileViewer key={fileRequest?.id ?? "library"} embedded initialId={fileRequest?.id}
        onClose={() => {}} onExpand={onExpandFile} /></div>}
      {tab === "nas" ? null : !artifact ? <div className="hud-content-empty"><p>{tab === "code" ? "El código que abra Helios aparecerá aquí." : "La vista previa de la implementación aparecerá aquí."}</p></div>
        : tab === "code" ? <ReplyCode download code={artifact.code} language={artifact.language} onImprove={onImprove} />
        : artifact.previewHtml ? <iframe title="Vista previa lateral" sandbox="allow-scripts" srcDoc={previewDocument(artifact.previewHtml)} />
        : <div className="hud-content-empty"><p>Esta implementación todavía no tiene vista previa.</p>
          <button type="button" disabled={busy} onClick={() => onPreview(artifact.code, artifact.language)}>Crear interfaz</button></div>}
    </div>
    {artifact && tab !== "nas" && canUndo && <footer><button type="button" onClick={onUndo}><RotateCcw size={14} /> Recuperar versión anterior</button></footer>}
  </section>;
}
