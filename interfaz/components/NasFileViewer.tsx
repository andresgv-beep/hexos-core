"use client";
import { useEffect, useRef, useState } from "react";
import { Download, X } from "lucide-react";

import { listFileCopies, readFilePage, type NasFileCopy } from "@/lib/helios/files";
export function NasFileViewer({ initialId, onClose }: { initialId?: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [copies, setCopies] = useState<NasFileCopy[]>([]);
  const [selected, setSelected] = useState(initialId ?? "");
  const [text, setText] = useState("");
  const [next, setNext] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = copies.find(item => item.file_id === selected);
  useEffect(() => { const element = dialog.current; element?.showModal(); return () => element?.close(); }, []);
  useEffect(() => {
    const controller = new AbortController();
    listFileCopies(controller.signal).then(setCopies)
      .catch(error => { if (!controller.signal.aborted) setError(String(error.message)); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    setText(""); setNext(null); setError("");
    if (!active?.text_available) return;
    const controller = new AbortController();
    setBusy(true);
    readFilePage(selected, 0, controller.signal).then(data => {
      setText(data.text); setNext(data.next_offset);
    }).catch(error => { if (!controller.signal.aborted) setError(String(error.message)); })
      .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [selected, active?.text_available]);
  async function more() {
    if (next === null || busy) return;
    setBusy(true); setError("");
    try {
      const data = await readFilePage(selected, next);
      setText(previous => previous + data.text); setNext(data.next_offset);
    } catch (error) { setError(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  }
  return <dialog ref={dialog} className="chat-history nas-file-viewer" aria-labelledby="file-title"
    onCancel={event => { event.preventDefault(); onClose(); }}>
    <header className="history-heading"><h2 id="file-title">Archivos del NAS</h2>
      <button className="icon-button" onClick={onClose} aria-label="Cerrar visor de archivos"><X /></button></header>
    <div className="history-messages">
      <label>Copias recientes <select value={selected} disabled={busy} onChange={event => setSelected(event.target.value)}>
        <option value="">Selecciona un archivo</option>
        {copies.map(item => <option key={item.file_id} value={item.file_id}>{item.name} · {item.device}</option>)}
      </select></label>
      {!copies.length && <p>Pide a Helios que abra un archivo encontrado. Aquí podrás verlo y descargarlo.</p>}
      {active && <>
        <p>{active.path}<br />{active.size_bytes.toLocaleString()} bytes · Copia del {active.observed_at}</p>
        <a className="history-code-open" href={`/api/helios/files/${active.file_id}/download`} download>
          <Download size={16} /> Descargar {active.name}</a>
        {active.text_available ? <pre className="nas-file-text">{text}</pre>
          : <p>Este formato está disponible para descarga. Todavía no tiene vista de texto.</p>}
        {next !== null && <button className="history-code-open" disabled={busy} onClick={() => void more()}>Cargar siguiente fragmento</button>}
      </>}
      {busy && <p role="status">Leyendo…</p>}
      {error && <p role="alert">{error}</p>}
    </div>
    <footer className="history-footer">Se muestra una copia guardada; el archivo del NAS puede cambiar después.</footer>
  </dialog>;
}
