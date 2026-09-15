export type ToolActivityStatus = "running" | "done" | "failed";

export interface ToolActivity {
  id: string;
  name: string;
  status: ToolActivityStatus;
  seconds: number | null;
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
    return [{
      id: `${index}-${entry.tool}`,
      name: entry.tool,
      status,
      seconds: typeof entry.seconds === "number" && Number.isFinite(entry.seconds) && entry.seconds >= 0 ? entry.seconds : null,
    }];
  }).slice(-6);
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
