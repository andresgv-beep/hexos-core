import type { ToolActivity } from "@/lib/helios/tools";

/** Presentation only: activities still come from the existing transport. */
export function ToolActivityPanel({ tools }: { tools: ToolActivity[] }) {
  return <section className="hud-panel hud-activity" aria-label="Herramientas activas">
    <h2>ACTIVIDAD</h2>
    {!tools.length && <p>Sin herramientas activas.</p>}
    <ul aria-live="polite">{tools.map(tool => <li key={tool.id} data-status={tool.status}>
      <strong>{tool.name}</strong>
      <span>{tool.status === "running" ? "Ejecutando…" : tool.status === "failed" ? "Con error" : "Completado"}
        {tool.seconds !== null && ` · ${tool.seconds.toFixed(1)} s`}</span>
    </li>)}</ul>
  </section>;
}
