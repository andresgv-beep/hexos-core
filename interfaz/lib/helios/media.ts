/** La cola de vídeo para las tarjetas vivas. Se lee sin pasar por el modelo,
 *  de la misma cola que usa el trabajador, así que la tarjeta y lo que cuenta
 *  Helios no pueden decir cosas distintas. */
export interface MediaJob {
  id: string; batchId: string; title: string; state: string; label: string; paused: boolean;
  updatedAt: number;
  percent?: number; etaSeconds?: number;
  sizeBeforeGb?: number; sizeAfterGb?: number; estimatedGb?: number;
  error?: string;
}
export type MediaControl = "pause" | "resume" | "cancel";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);
export const isActive = (job: MediaJob) => !TERMINAL.has(job.state);

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
const number = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : undefined;

export function parseMediaJobs(value: unknown): MediaJob[] {
  if (!isRecord(value) || !Array.isArray(value.jobs)) return [];
  return value.jobs.flatMap(item => {
    if (!isRecord(item) || typeof item.id !== "string" || typeof item.batch_id !== "string" || typeof item.state !== "string") return [];
    return [{
      id: item.id, batchId: item.batch_id, state: item.state,
      title: typeof item.title === "string" ? item.title : "Película",
      label: typeof item.label === "string" ? item.label : item.state,
      paused: item.paused === true, updatedAt: number(item.updated_at) ?? 0,
      percent: number(item.percent), etaSeconds: number(item.eta_seconds),
      sizeBeforeGb: number(item.size_before_gb), sizeAfterGb: number(item.size_after_gb),
      estimatedGb: number(item.estimated_gb),
      error: typeof item.error === "string" ? item.error : undefined,
    }];
  });
}

export interface MediaClient {
  jobs(signal?: AbortSignal): Promise<MediaJob[]>;
  control(batchId: string, operation: MediaControl): Promise<MediaJob[]>;
}

export function createMediaClient(base = "/api", fetcher: typeof fetch = fetch): MediaClient {
  async function read(response: Response) {
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) throw new Error(isRecord(body) && typeof body.error === "string" ? body.error : "No se pudo leer la cola de vídeo.");
    return parseMediaJobs(body);
  }
  return {
    jobs: async signal => read(await fetcher(`${base}/media`, { signal })),
    control: async (batchId, operation) => read(await fetcher(`${base}/media/control`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ batch_id: batchId, operation }),
    })),
  };
}

/** «12 min», «1 h 05 min»: lo que queda, sin segundos que bailan. */
export function remaining(seconds: number) {
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}

export const gigabytes = (value: number) => `${value.toLocaleString("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} GB`;
