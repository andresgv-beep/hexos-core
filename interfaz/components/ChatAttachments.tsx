"use client";
import { useEffect, useRef } from "react";
import { FileText, Paperclip, X } from "lucide-react";
export interface Attachment {
  id: string;
  name: string;
  preview?: string;
  text?: string;
  status: "reading" | "ready" | "vision" | "error";
  error?: string;
}
export function ChatAttachments({ files, onRemove }: { files: Attachment[]; onRemove: (id: string) => void }) {
  return <div className="attachment-list">{files.map(file => <div className="attachment-chip" key={file.id}>
    {file.preview ? <span className="attachment-thumbnail" style={{ backgroundImage: `url("${file.preview}")` }} role="img" aria-label={file.name} /> : <FileText size={22} />}
    <div><strong>{file.name}</strong><span>{file.status === "reading" ? "Leyendo…" : file.status === "vision" ? "Visión todavía no conectada" : file.status === "error" ? file.error : "Listo para enviar"}</span></div>
    <button className="icon-button" aria-label={`Quitar ${file.name}`} onClick={() => onRemove(file.id)}><X size={15} /></button>
  </div>)}</div>;
}
export function AttachmentButton({ onSelect, disabled }: { onSelect: (files: File[]) => void; disabled: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const element = input.current;
    return () => { if (element) element.value = ""; };
  }, []);
  return <><input ref={input} hidden type="file" multiple accept="image/png,image/jpeg,image/webp,.pdf,.docx,.txt,.md,.csv,.json" onChange={event => {
    onSelect(Array.from(event.target.files || [])); event.target.value = "";
  }} /><button type="button" className="icon-button" aria-label="Adjuntar imágenes o documentos" disabled={disabled} onClick={() => input.current?.click()}><Paperclip size={21} /></button></>;
}
