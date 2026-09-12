import { phaseFromHexos, type HeliosPhase } from "./state";

export interface ChatReply { reply: string; tools: unknown[]; document?: unknown }
export interface HistoryMessage { role: "user" | "assistant"; text: string }
function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
export interface HeliosTransport {
  status(signal?: AbortSignal): Promise<{ phase: HeliosPhase; mode: string }>;
  history(signal?: AbortSignal): Promise<HistoryMessage[]>;
  send(text: string, signal?: AbortSignal): Promise<ChatReply>;
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
      return { phase: phaseFromHexos(data.state), mode: data.mode };
    },
    async history(signal) {
      const data = await request("history", { signal });
      if (!Array.isArray(data) || !data.every(row => row && (row.role === "user" || row.role === "assistant") && typeof row.text === "string")) throw new Error("Historial de HexOS no válido");
      return data.map(({ role, text }) => ({ role, text }));
    },
    async send(text, signal) {
      if (!text.trim()) throw new Error("Escribe un mensaje");
      const data = await request("chat", { method: "POST", headers: { "Content-Type": "text/plain; charset=utf-8" }, body: text, signal });
      if (!isRecord(data) || typeof data.reply !== "string" || !data.reply.trim() || !Array.isArray(data.tools)) throw new Error("HexOS no devolvió una respuesta completa");
      return { reply: data.reply, tools: data.tools, document: data.document };
    },
  };
}
