"use client";

import { useState } from "react";
import type { ToolActivity } from "@/lib/helios/tools";

const segundos = (value: number) => `${value.toLocaleString("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s`;
const estado = { running: "en curso", done: "ok", failed: "error" } as const;

/** Las llamadas del turno como una terminal: abierta mientras Helios trabaja y
 *  plegada en una línea cuando termina, para que el chat no se llene de registros. */
export function ToolTerminal({ tools, live }: { tools: ToolActivity[]; live: boolean }) {
  // null = lo decide el turno; así se abre sola al trabajar y se pliega al acabar,
  // salvo que el usuario la haya abierto o cerrado a mano.
  const [elegido, setElegido] = useState<boolean | null>(null);
  if (!tools.length) return null;
  const abierta = elegido ?? live;
  const enCurso = tools.filter(tool => tool.status === "running").length;
  const fallidas = tools.filter(tool => tool.status === "failed").length;
  const total = tools.reduce((sum, tool) => sum + (tool.seconds ?? 0), 0);
  const resumen = [`${tools.length} ${tools.length === 1 ? "llamada" : "llamadas"}`,
    enCurso ? `${enCurso} en curso` : total > 0 ? segundos(total) : "",
    fallidas ? `${fallidas} con error` : ""].filter(Boolean).join(" · ");
  return <div className="tool-terminal" role="log" aria-label="Llamadas a herramientas" data-live={live || undefined}>
    <div className="tool-terminal-head">
      <span>herramientas · {resumen}</span>
      <button type="button" aria-expanded={abierta} onClick={() => setElegido(!abierta)}>{abierta ? "Ocultar" : "Ver"}</button>
    </div>
    {abierta && <ul>
      {tools.map(tool => {
        const punto = tool.name.indexOf(".");
        return <li key={tool.id} data-status={tool.status}>
          <span className="tool-terminal-prompt" aria-hidden="true">›</span>
          <span className="tool-terminal-name">{punto > 0 && <span>{tool.name.slice(0, punto + 1)}</span>}{tool.name.slice(punto + 1)}</span>
          <span className="tool-terminal-state">{estado[tool.status]}{tool.status === "running" && <i aria-hidden="true" />}</span>
          <span className="tool-terminal-time">{tool.seconds !== null ? segundos(tool.seconds) : ""}</span>
        </li>;
      })}
    </ul>}
  </div>;
}
