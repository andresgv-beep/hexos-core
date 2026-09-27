"use client";

import { type ReactNode, useState } from "react";
import { Check, Copy } from "lucide-react";
import { entry, parseReply, type Inline } from "@/lib/helios/markdown";
import { CodeText } from "./CodeText";

export interface CodeActions {
  onPreviewCode?: (code: string, language?: string) => void;
}

export function ReplyMarkdown({ text, onPreviewCode }: { text: string } & CodeActions) {
  const bloques = parseReply(text);
  return <div className="helios-answer">{bloques.map((bloque, indice) => {
    if (bloque.kind === "code") {
      const codigo = bloque.lines.map(linea => linea.map(parte => parte.text).join("")).join("\n");
      return <ReplyCode key={indice} code={codigo} language={bloque.language} onPreview={onPreviewCode} />;
    }
    if (bloque.kind === "p") return <p key={indice}>{bloque.lines[0].map((parte, i) => <InlinePart key={i} part={parte} />)}</p>;
    const Lista = bloque.kind === "ol" ? "ol" : "ul";
    if (bloque.entries) return <Lista key={indice} className="reply-entries">{bloque.lines.map((linea, i) => {
      const fila = entry(linea)!;
      return <li key={i}><span className="reply-entry-name">{fila.name.map((parte, j) => <InlinePart key={j} part={parte} />)}</span>
        <span className="reply-entry-value">{fila.value}</span></li>;
    })}</Lista>;
    return <Lista key={indice}>{bloque.lines.map((linea, i) =>
      <li key={i}>{linea.map((parte, j) => <InlinePart key={j} part={parte} />)}</li>)}</Lista>;
  })}</div>;
}

function InlinePart({ part }: { part: Inline }) {
  if (part.code) return <code>{part.text}</code>;
  if (part.bold) return <strong>{part.text}</strong>;
  return part.text;
}

export function ReplyCode({ code, language, children, copy = true, download = false, onPreview }: {
  code: string;
  language?: string;
  children?: ReactNode;
  copy?: boolean;
  download?: boolean;
  onPreview?: (code: string, language?: string) => void;
}) {
  const [copiado, setCopiado] = useState(false);
  async function copiar() {
    await navigator.clipboard.writeText(code);
    setCopiado(true);
    window.setTimeout(() => setCopiado(false), 1600);
  }
  const contenido = children === undefined || children === null || children === false
    ? <CodeText source={code} language={language} />
    : children;
  return <section className="reply-code" aria-label={`Bloque de código${language ? ` ${language}` : ""}`}>
    <header>
      <span>{language || "código"}</span>
      <span className="reply-code-actions">
        {onPreview && <button type="button" onClick={() => onPreview(code, language)}>
          {["html", "htm"].includes((language ?? "").toLowerCase()) ? "Ver" : "Crear vista"}
        </button>}
        {download && <a download={`helios.${({ html: "html", javascript: "js", typescript: "ts", python: "py", css: "css", json: "json", cpp: "cpp", cuda: "cu", markdown: "md" } as Record<string,string>)[language ?? ""] ?? "txt"}`}
          href={`data:text/plain;charset=utf-8,${encodeURIComponent(code)}`}>Descargar</a>}
        {copy && <button type="button" onClick={copiar} aria-label="Copiar código">
          {copiado ? <Check size={14} /> : <Copy size={14} />}
          {copiado ? "Copiado" : "Copiar"}
        </button>}
      </span>
    </header>
    <pre><code>{contenido}</code></pre>
  </section>;
}
