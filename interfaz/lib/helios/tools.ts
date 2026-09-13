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
