import { phaseFromHexos, type HeliosPhase } from "./state";
import { parseToolActivities, type ToolActivity } from "./tools";

export interface ChatReply { reply: string; tools: ToolActivity[]; document?: unknown }
export interface HistoryMessage { role: "user" | "assistant"; text: string }
function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
export interface HeliosTransport {
  /** `thinking` es null cuando el motor no tiene canal de pensamiento. */
  status(signal?: AbortSignal): Promise<{ phase: HeliosPhase; mode: string; thinking: boolean | null; tools: ToolActivity[] }>;
  /** Enciende o apaga el canal de pensamiento de Gemma. HexOS lo recuerda. */
  setThinking(enabled: boolean, signal?: AbortSignal): Promise<boolean>;
  history(signal?: AbortSignal): Promise<HistoryMessage[]>;
  /** `image` es base64 de PNG/JPEG/WebP, sin la cabecera `data:`. Una por turno. */
  send(text: string, signal?: AbortSignal, image?: string): Promise<ChatReply>;
}

/** Existing HexOS HTTP contract, inspected 2026-09-12. No connection at import time.
 * Use a same-origin proxy in the host application; never connect the browser to
 * Héctor's shared memory / native protocol. Cancellation stops waiting locally;
 * the current HexOS endpoint cannot cancel generation on the server.
 */
export function createHexosTransport(base = "/api", fetcher: typeof fetch = fetch): HeliosTransport {
  const endpoint = base.replace(/\/$/, "");
  async function request(path: string, init: RequestInit) {
    const response = await fetcher(`${endpoint}/${path}`, { ...init, cache: "no-store" });
    const data: unknown = await response.json();
    if (!response.ok) throw new Error(isRecord(data) && typeof data.error === "string" ? data.error : `HexOS: HTTP ${response.status}`);
    if (!data || typeof data !== "object") throw new Error("Respuesta de HexOS no válida");
    return data;
  }
  return {
    async status(signal) {
      const data = await request("status", { signal });
      if (!isRecord(data) || typeof data.mode !== "string") throw new Error("Modo de HexOS no válido");
      const thinking = typeof data.thinking === "boolean" ? data.thinking : null;
      return { phase: phaseFromHexos(data.state), mode: data.mode, thinking, tools: parseToolActivities(data.active_tools, "running") };
    },
    async setThinking(enabled, signal) {
      const data = await request("thinking", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }), signal });
      if (!isRecord(data) || typeof data.thinking !== "boolean") throw new Error("HexOS no confirmó el cambio");
      return data.thinking;
    },
    async history(signal) {
      const data = await request("history", { signal });
      if (!Array.isArray(data) || !data.every(row => row && (row.role === "user" || row.role === "assistant") && typeof row.text === "string")) throw new Error("Historial de HexOS no válido");
      return data.map(({ role, text }) => ({ role, text }));
    },
    async send(text, signal, image) {
      if (!text.trim()) throw new Error("Escribe un mensaje");
      // Con imagen el contrato es JSON; sin ella se mantiene el text/plain de siempre.
      const init: RequestInit = image
        ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, image }), signal }
        : { method: "POST", headers: { "Content-Type": "text/plain; charset=utf-8" }, body: text, signal };
      const data = await request("chat", init);
      if (!isRecord(data) || typeof data.reply !== "string" || !data.reply.trim() || !Array.isArray(data.tools)) throw new Error("HexOS no devolvió una respuesta completa");
      return { reply: data.reply, tools: parseToolActivities(data.tools, "done"), document: data.document };
    },
  };
}
