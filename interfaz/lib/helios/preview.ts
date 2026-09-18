import { parseReply } from "./markdown";

const CSP = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'";
const HEAD = `<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="${CSP}">`;

export function extractHtmlPreview(reply: string): string | null {
  const blocks = parseReply(reply).filter(block => block.kind === "code" && ["html", "htm"].includes((block.language ?? "").toLowerCase()));
  const block = blocks[blocks.length - 1];
  return block ? block.lines.map(line => line.map(part => part.text).join("")).join("\n") : null;
}

/** Encierra la maqueta en un documento sin red, formularios ni acceso al origen padre. */
export function previewDocument(source: string): string {
  const html = source.trim();
  if (/<head(?:\s[^>]*)?>/i.test(html)) return html.replace(/<head(?:\s[^>]*)?>/i, match => `${match}${HEAD}`);
  if (/<html(?:\s[^>]*)?>/i.test(html)) return html.replace(/<html(?:\s[^>]*)?>/i, match => `${match}<head>${HEAD}</head>`);
  return `<!doctype html><html><head>${HEAD}<style>html,body{min-height:100%;margin:0}</style></head><body>${html}</body></html>`;
}
