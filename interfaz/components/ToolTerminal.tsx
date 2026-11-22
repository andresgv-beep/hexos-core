"use client";

import type { ToolActivity } from "@/lib/helios/tools";

const segundos = (value: number) => `${value.toLocaleString("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s`;
const estado = { running: "En curso", done: "Completada", failed: "Error" } as const;

export function ToolTerminal({ tools, live, progress }: { tools: ToolActivity[]; live: boolean; progress?: string[] }) {
  if (!tools.length) return null;
  const activa = live ? tools.findLast(tool => tool.status === "running") : undefined;
  const fallidas = tools.filter(tool => tool.status === "failed").length;
  const total = tools.reduce((sum, tool) => sum + (tool.seconds ?? 0), 0);
  const web = tools.every(tool => tool.name === "web.search" || tool.name === "web.read");
  let titulo = web ? "Consulta web" : "Herramientas";
  if (activa?.name === "web.search") titulo = "Buscando en la web…";
  else if (activa?.name === "web.read") titulo = "Leyendo una fuente…";
  else if (activa) titulo = "Usando herramientas…";
  else if (web && !fallidas && tools.some(tool => tool.name === "web.read" && tool.status === "done")) titulo = "Fuentes consultadas";
  const resumen = [`${tools.length} ${tools.length === 1 ? "llamada" : "llamadas"}`,
    !activa && total > 0 ? segundos(total) : "", fallidas ? `${fallidas} con error` : ""].filter(Boolean).join(" · ");
  return <details className="tool-terminal">
    <summary><span className="activity-emblem" data-busy={Boolean(activa) || undefined} aria-hidden="true" />
      <span>{titulo}</span><small>{resumen}</small></summary>
    <div className="tool-terminal-detail">
      <ul>{tools.map(tool => <li key={tool.id} data-status={tool.status}>
        <span>{tool.name === "web.search" ? "Búsqueda web" : tool.name === "web.read" ? "Lectura de fuente" : tool.name}</span>
        <small>{estado[tool.status]}{tool.seconds !== null ? ` · ${segundos(tool.seconds)}` : ""}</small>
        {tool.detail && <small className="tool-detail-text">{tool.detail}</small>}
      </li>)}</ul>
      {progress?.map((line, i) => <p key={i}>{line}</p>)}
    </div>
  </details>;
}
