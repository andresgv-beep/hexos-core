"use client";

import { Brain, Database, FileSearch, History, Network, Server, Wrench } from "lucide-react";
import type { CSSProperties } from "react";
import type { ToolActivity } from "@/lib/helios/tools";

function identity(name: string) {
  if (name.startsWith("nas.")) return { label: "SSH", detail: name === "nas.read" ? "Conectado" : "Operando NAS", Icon: Server };
  if (name.startsWith("network.") || name.startsWith("device.")) return { label: "RED", detail: name === "network.local" ? "Analizando" : name.split(".")[1], Icon: Network };
  if (name.startsWith("document.")) return { label: "DOC", detail: name.split(".")[1], Icon: FileSearch };
  if (name.startsWith("history.")) return { label: "MEMORIA", detail: name.split(".")[1], Icon: History };
  if (name.startsWith("profile.")) return { label: "PERFIL", detail: name.split(".")[1], Icon: Brain };
  if (/^(work|task|procedure|report|result)\./.test(name)) return { label: "DATOS", detail: name.replace(".", " · "), Icon: Database };
  return { label: name.split(".")[0].toUpperCase(), detail: name.split(".").slice(1).join(" · ") || "Herramienta", Icon: Wrench };
}

const FAN_POSITIONS = [[61, 11], [75, 20], [86, 35], [90, 53], [84, 69], [71, 80]] as const;

function statusText(tool: ToolActivity) {
  if (tool.status === "running") return "Ejecutando…";
  if (tool.status === "failed") return "Con error";
  return tool.seconds === null ? "Completado" : `Listo · ${tool.seconds.toFixed(tool.seconds < 10 ? 1 : 0)} s`;
}

export function ToolSatellites({ tools }: { tools: ToolActivity[] }) {
  if (!tools.length) return null;
  return <section className="tool-satellites" aria-label="Herramientas activas" aria-live="polite">
    <div className="satellite-title">HERRAMIENTAS ACTIVAS</div>
    <div className="satellite-orbit">
      {tools.length > 1 && <svg className="satellite-path" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <polyline points={tools.map((_, index) => FAN_POSITIONS[index].join(",")).join(" ")} />
        {tools.slice(0, -1).map((_, index) => {
          const a = FAN_POSITIONS[index], b = FAN_POSITIONS[index + 1];
          return <circle key={index} cx={(a[0] + b[0]) / 2} cy={(a[1] + b[1]) / 2} r=".42" />;
        })}
      </svg>}
      <div className="satellite-list">
        {tools.map((tool, index) => {
          const { label, detail, Icon } = identity(tool.name);
          const [x, y] = FAN_POSITIONS[index];
          const style = {
            "--satellite-x": `${x}%`,
            "--satellite-y": `${y}%`,
          } as CSSProperties;
          return <div className={`tool-satellite ${tool.status}`} key={tool.id} title={tool.name} style={style}>
            <span className="satellite-node"><Icon size={25} strokeWidth={1.35} aria-hidden="true" /></span>
            <span className="satellite-copy"><strong>{label}</strong><small>{tool.status === "running" ? statusText(tool) : detail}</small><em>{tool.status !== "running" ? statusText(tool) : ""}</em></span>
          </div>;
        })}
      </div>
    </div>
  </section>;
}
