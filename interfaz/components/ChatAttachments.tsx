"use client";
import { useEffect, useRef } from "react";
import { FileText, Mic, Paperclip, X } from "lucide-react";
export interface Attachment {
  id: string;
  name: string;
  preview?: string;
  text?: string;
  /** base64 de la imagen, sin la cabecera `data:`. Solo una por mensaje. */
  image?: string;
  /** base64 de un WAV mono 16 kHz. Un mensaje lleva imagen o voz, no las dos. */
  audio?: string;
  seconds?: number;
  status: "reading" | "ready" | "error";
  error?: string;
}
export function ChatAttachments({ files, onRemove }: { files: Attachment[]; onRemove: (id: string) => void }) {
  return <div className="attachment-list">{files.map(file => <div className="attachment-chip" key={file.id}>
    {file.preview ? <span className="attachment-thumbnail" style={{ backgroundImage: `url("${file.preview}")` }} role="img" aria-label={file.name} /> : file.audio ? <Mic size={22} /> : <FileText size={22} />}
    <div><strong>{file.name}</strong><span>{file.status === "reading" ? "Leyendo…" : file.status === "error" ? file.error : file.image ? "Helios la verá"
      : file.audio ? `Helios lo oirá · ${(file.seconds ?? 0).toFixed(1).replace(".", ",")} s` : "Listo para enviar"}</span></div>
    <button className="icon-button" aria-label={`Quitar ${file.name}`} onClick={() => onRemove(file.id)}><X size={15} /></button>
  </div>)}</div>;
}
export function AttachmentButton({ onSelect, disabled }: { onSelect: (files: File[]) => void; disabled: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const element = input.current;
    return () => { if (element) element.value = ""; };
  }, []);
  return <><input ref={input} hidden type="file" multiple accept="image/png,image/jpeg,image/webp,audio/*,.pdf,.docx,.txt,.md,.csv,.json" onChange={event => {
    onSelect(Array.from(event.target.files || [])); event.target.value = "";
  }} /><button type="button" className="icon-button" aria-label="Adjuntar imágenes, audio o documentos" disabled={disabled} onClick={() => input.current?.click()}><Paperclip size={21} /></button></>;
}
