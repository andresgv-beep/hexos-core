"use client";
import { useEffect, useState } from "react";
import { previewDocument } from "@/lib/helios/preview";
import { compileTailwind, inlineTailwind, usesTailwindCdn } from "@/lib/helios/tailwindPreview";

/**
 * Documento de la vista previa. Si la página pide Tailwind por CDN, se pinta
 * primero tal cual y en cuanto el CSS está compilado se sustituye por la
 * versión con estilos (unos milisegundos; el compilador se reutiliza).
 */
export function usePreviewDocument(html: string | null | undefined): string {
  const [styled, setStyled] = useState<{ html: string; document: string } | null>(null);
  useEffect(() => {
    if (!html || !usesTailwindCdn(html)) return;
    let alive = true;
    // La hoja de Tailwind (~30 KB) se carga solo cuando hace falta.
    import("tailwindcss/index.css?raw")
      .then(({ default: stylesheet }) => compileTailwind(html, stylesheet))
      .then(css => { if (alive) setStyled({ html, document: previewDocument(inlineTailwind(html, css)) }); })
      .catch(() => { /* sin CSS la página se sigue viendo, como antes */ });
    return () => { alive = false; };
  }, [html]);
  if (!html) return "";
  return styled?.html === html ? styled.document : previewDocument(html);
}
