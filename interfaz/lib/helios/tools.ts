export type ToolActivityStatus = "running" | "done" | "failed";

export interface ToolActivity {
  id: string;
  name: string;
  status: ToolActivityStatus;
  seconds: number | null;
  detail?: string;
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** Las notas que el turno ha leído o escrito, en orden. El resultado de las
 *  herramientas se queda fuera de `ToolActivity` a propósito, pero el id sí hace
 *  falta: sin él la interfaz sabe que hubo un `note.get` y no cuál, así que no
 *  puede abrir la nota que le acaban de pedir mostrar. */
export function notesTouched(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const ids: string[] = [];
  for (const entry of value) {
    if (!record(entry) || !["note.show", "note.get", "note.save"].includes(String(entry.tool))) continue;
    if (entry.failed === true) continue;
    const result = entry.result;
    if (record(result) && typeof result.id === "string" && result.id && !ids.includes(result.id)) ids.push(result.id);
  }
  return ids;
}

/** Keep tool results and arguments outside presentation state; satellites only need identity and lifecycle. */
export function parseToolActivities(value: unknown, defaultStatus: ToolActivityStatus): ToolActivity[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((entry, index) => {
    if (!record(entry) || typeof entry.tool !== "string" || !entry.tool.trim()) return [];
    const explicit = entry.status;
    const status: ToolActivityStatus = explicit === "running" || explicit === "done" || explicit === "failed"
      ? explicit : entry.failed === true ? "failed" : defaultStatus;
    let detail = "";
    const args = record(entry.arguments) ? entry.arguments : {};
    if (entry.tool === "web.search" && typeof args.query === "string") detail = args.query.slice(0, 180);
    if (entry.tool === "web.read" && typeof args.url === "string") {
      try { detail = new URL(args.url).hostname; } catch { /* La URL fallida puede ser inválida. */ }
      const error = record(entry.result) && typeof entry.result.error === "string" ? entry.result.error : "";
      const http = error.match(/\bHTTP \d{3}\b/i);
      if (http) detail = [detail, http[0]].filter(Boolean).join(" · ");
    }
    return [{
      id: `${index}-${entry.tool}`,
      name: entry.tool,
      ...(detail ? { detail } : {}),
      status,
      seconds: typeof entry.seconds === "number" && Number.isFinite(entry.seconds) && entry.seconds >= 0 ? entry.seconds : null,
    }];
  }).slice(-MAX_TURN_TOOLS);
}

const MAX_TURN_TOOLS = 60;

/** Las llamadas de un turno, una por una. Se casan por posición y nombre, no solo por nombre:
 *  ocho `project.read` seguidos son ocho llamadas, y casadas por nombre el chat enseñaba una. */
export function turnToolActivities(current: ToolActivity[], incoming: ToolActivity[]): ToolActivity[] {
  const merged = [...current];
  for (const tool of incoming) {
    const existing = merged.findIndex(item => item.id === tool.id);
    if (existing >= 0) merged[existing] = tool;
    else merged.push(tool);
  }
  return merged.slice(-MAX_TURN_TOOLS);
}

/** Preserve the recent tool constellation while updating repeated tools in place. */
export function mergeToolActivities(current: ToolActivity[], incoming: ToolActivity[]): ToolActivity[] {
  const merged = [...current];
  for (const tool of incoming) {
    const existing = merged.findIndex(item => item.name === tool.name);
    if (existing >= 0) merged[existing] = { ...tool, id: merged[existing].id };
    else merged.push(tool);
  }
  return merged.slice(-6);
}

/** Las notas que el turno ha mandado cerrar. `"todas"` cierra las abiertas: hay
 *  que poder decir «cierra las notas» sin enumerarlas una a una. */
export function notesDismissed(value: unknown): string[] | "todas" | null {
  if (!Array.isArray(value)) return null;
  const ids: string[] = [];
  let todas = false;
  for (const entry of value) {
    if (!record(entry) || entry.tool !== "note.hide" || entry.failed === true) continue;
    const result = entry.result;
    if (!record(result)) continue;
    if (result.hidden === "todas") todas = true;
    else if (typeof result.hidden === "string" && result.hidden && !ids.includes(result.hidden)) ids.push(result.hidden);
  }
  if (todas) return "todas";
  return ids.length ? ids : null;
}
