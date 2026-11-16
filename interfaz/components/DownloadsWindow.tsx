"use client";

import { useEffect, useRef, useState } from "react";
import { Download, Eye, File, FileText, Image as ImageIcon, X } from "lucide-react";
import type { DownloadedFile, Downloads, HeliosTransport } from "@/lib/helios/hexos";

const megas = new Intl.NumberFormat("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const fecha = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function peso(bytes: number): string {
  return bytes < 1_000_000 ? `${Math.max(1, Math.round(bytes / 1000))} kB` : `${megas.format(bytes / 1_000_000)} MB`;
}
function cuando(ts: string): string {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? "" : fecha.format(d);
}

function Fila({ file, transport }: { file: DownloadedFile; transport: HeliosTransport }) {
  const Icono = file.kind === "PDF" || file.readable ? FileText : file.kind.startsWith("imagen") ? ImageIcon : File;
  const ver = transport.downloadUrl!(file.id);
  const guardar = transport.downloadUrl!(file.id, true);
  // Lo que el navegador sabe enseñar se abre en otra pestaña; lo demás, al pulsarlo, se guarda.
  const principal = file.viewable ? { href: ver, target: "_blank", rel: "noreferrer" } : { href: guardar, download: file.name };
  return <li className="downloads-row" data-missing={!file.onDisk}>
    <Icono size={20} aria-hidden="true" />
    <div className="downloads-what">
      {file.onDisk ? <a {...principal}>{file.name}</a> : <span>{file.name}</span>}
      <small>{[file.kind, peso(file.bytes), cuando(file.ts), file.source].filter(Boolean).join(" · ")}</small>
      {!file.onDisk && <small>Ya no está en la carpeta: se movió o se borró.</small>}
    </div>
    {file.onDisk && <div className="downloads-actions">
      {file.viewable && <a href={ver} target="_blank" rel="noreferrer" aria-label={`Ver ${file.name}`}>
        <Eye size={16} aria-hidden="true" /> Ver</a>}
      <a href={guardar} download={file.name} aria-label={`Descargar ${file.name}`} title="Guardarlo en este dispositivo">
        <Download size={16} aria-hidden="true" /> Descargar</a>
    </div>}
  </li>;
}

/** Lo que Helios ha bajado de la web con tu aprobación, lo más nuevo primero. Se puede ver
 *  aquí mismo o llevarse al dispositivo desde el que se mira: los ficheros viven en el PC. */
export function DownloadsWindow({ transport, onClose }: { transport: HeliosTransport; onClose: () => void }) {
  const [lista, setLista] = useState<Downloads | null>(null);
  const [fallo, setFallo] = useState("");
  const panel = useRef<HTMLDivElement>(null);
  const cerrar = useRef(onClose);
  useEffect(() => { cerrar.current = onClose; }, [onClose]);
  useEffect(() => {
    panel.current?.focus();
    const tecla = (event: KeyboardEvent) => { if (event.key === "Escape") cerrar.current(); };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, []);
  useEffect(() => {
    const control = new AbortController();
    transport.downloads!(control.signal).then(setLista)
      .catch(reason => { if (!control.signal.aborted) setFallo(reason instanceof Error ? reason.message : "No se pudo leer la lista"); });
    return () => control.abort();
  }, [transport]);

  return <div className="access-backdrop">
    <div ref={panel} className="access-panel settings-panel" role="dialog" aria-modal="true" aria-labelledby="downloads-title"
      tabIndex={-1}>
      <header className="settings-head">
        <Download size={17} aria-hidden="true" />
        <h2 id="downloads-title">Descargas</h2>
        <button type="button" className="icon-button" aria-label="Cerrar descargas" onClick={onClose}><X size={16} /></button>
      </header>
      <div className="settings-content">
        {fallo && <p className="settings-status" data-kind="error" role="alert">{fallo}</p>}
        {!lista && !fallo && <p className="settings-lead">Cargando…</p>}
        {lista && !lista.files.length && <p className="settings-lead">Todavía no hay nada. Pídele a Helios en el Chat
          que te baje un PDF o un fichero de la web: lo aprobarás en una tarjeta y aparecerá aquí.</p>}
        {lista && lista.files.length > 0 && <>
          <p className="settings-lead">{lista.files.length === 1 ? "Un fichero" : `${lista.files.length} ficheros`},
            {" "}lo más nuevo primero. Están en el PC, en <strong>{lista.folder}</strong>.</p>
          <ul className="downloads-list">
            {lista.files.map(file => <Fila key={file.id} file={file} transport={transport} />)}
          </ul>
        </>}
      </div>
    </div>
  </div>;
}
