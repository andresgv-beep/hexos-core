"use client";

import { type ReactNode, useState } from "react";
import { Check, Copy } from "lucide-react";
import { parseReply, type Inline } from "@/lib/helios/markdown";

export function ReplyMarkdown({ text }: { text: string }) {
  const bloques = parseReply(text);
  return <div className="helios-answer">{bloques.map((bloque, indice) => {
    if (bloque.kind === "code") {
      const codigo = bloque.lines.map(linea => linea.map(parte => parte.text).join("")).join("\n");
      return <ReplyCode key={indice} code={codigo} language={bloque.language} />;
    }
    if (bloque.kind === "p") return <p key={indice}>{bloque.lines[0].map((parte, i) => <InlinePart key={i} part={parte} />)}</p>;
    const Lista = bloque.kind === "ol" ? "ol" : "ul";
    return <Lista key={indice}>{bloque.lines.map((linea, i) =>
      <li key={i}>{linea.map((parte, j) => <InlinePart key={j} part={parte} />)}</li>)}</Lista>;
  })}</div>;
}

function InlinePart({ part }: { part: Inline }) {
  if (part.code) return <code>{part.text}</code>;
  if (part.bold) return <strong>{part.text}</strong>;
  return part.text;
}

export function ReplyCode({ code, language, children, copy = true }: {
  code: string;
  language?: string;
  children?: ReactNode;
  copy?: boolean;
}) {
  const [copiado, setCopiado] = useState(false);
  async function copiar() {
    await navigator.clipboard.writeText(code);
    setCopiado(true);
    window.setTimeout(() => setCopiado(false), 1600);
  }
  return <section className="reply-code" aria-label={`Bloque de código${language ? ` ${language}` : ""}`}>
    <header>
      <span>{language || "código"}</span>
      {copy && <button type="button" onClick={copiar} aria-label="Copiar código">
        {copiado ? <Check size={14} /> : <Copy size={14} />}
        {copiado ? "Copiado" : "Copiar"}
      </button>}
    </header>
    <pre><code>{children ?? code}</code></pre>
  </section>;
}
