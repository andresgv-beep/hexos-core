import { phaseFromHexos, type HeliosPhase } from "./state";
import { notesDismissed, notesTouched, parseToolActivities, type ToolActivity } from "./tools";

/** Llega el turno en que HexOS corta el contexto por lleno: lo anterior deja de
 *  estar en la ventana del modelo, aunque siga entero en el archivo. */
export interface ContextCut { at: string; messages: number; characters: number }
/** Cómo se cierra el turno según lo COMPROBADO, no según lo que diga la respuesta. */
export interface Closure { reason: string; note: string; unverified: { tool: string; verification?: string; evidence?: string }[] }
export interface ChatReply { reply: string; tools: ToolActivity[]; notes: string[]; closeNotes: string[] | "todas" | null; document?: unknown; contextCut?: ContextCut; closure?: Closure; cancelled?: boolean }
export interface Generation { requestId: string; phase: string; text: string; processed: number; total: number; cancellable: boolean; cancelling: boolean }
export interface HistoryMessage { role: "user" | "assistant"; text: string }
export interface HistoryPage { messages: HistoryMessage[]; nextBefore: number | null }
/** Lo que Helios dice que va a hacer, antes de hacerlo. Lo escribe el modelo, no
 *  HexOS, y llega a mitad de turno: por eso viaja aparte de la respuesta. */
export interface Progress { turnId: string | null; messages: { id: string; text: string }[] }
/** Helios ha pedido el acceso a un equipo. La contraseña se escribe en la ventana
 *  y va directa a HexOS: no pasa por la conversación ni la ve el modelo. */
export interface CredentialRequest {
  device: string; host?: string; mac?: string; pinned?: boolean;
  /** 'rejected' cuando ya había un acceso guardado y el equipo lo rechazó. */
  reason?: string; port?: number; user?: string;
  /** Marca de la petición. Cambia cada vez que se pide de nuevo, y es lo que
   *  distingue «la misma que ya descarté» de «me lo está pidiendo otra vez». */
  requestedAt?: string;
}
export interface AccessSaved {
  device: string; user: string; host: string; pinned: boolean;
  /** Lo que se estaba pidiendo cuando faltó el acceso. La interfaz lo reenvía
   *  sola: quien acaba de rellenar la ventana no debería repetir la petición. */
  resume?: string;
  resumedRequest?: string;
  resumed?: ChatReply;
  resumeError?: string;
}
function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function parseProgress(value: unknown): Progress {
  if (!isRecord(value)) return { turnId: null, messages: [] };
  const filas = Array.isArray(value.messages) ? value.messages : [];
  return {
    turnId: typeof value.turn_id === "string" ? value.turn_id : null,
    // Solo las que traen id y texto: el id es lo que evita repetirlas en cada consulta.
    messages: filas.filter(isRecord)
      .filter(m => typeof m.id === "string" && typeof m.text === "string" && m.text.trim())
      .map(m => ({ id: String(m.id), text: String(m.text) })),
  };
}
function parseChatReply(data: unknown): ChatReply {
  if (!isRecord(data) || typeof data.reply !== "string" || !data.reply.trim() || !Array.isArray(data.tools)) {
    throw new Error("HexOS no devolvió una respuesta completa");
  }
  const c = data.context_cut;
  const contextCut = isRecord(c) && typeof c.at === "string" && typeof c.messages === "number"
    && typeof c.characters === "number"
    ? { at: c.at, messages: c.messages, characters: c.characters } : undefined;
  const c2 = data.closure;
  const closure = isRecord(c2) && typeof c2.reason === "string" && typeof c2.note === "string"
    ? { reason: c2.reason, note: c2.note,
        unverified: (Array.isArray(c2.unverified) ? c2.unverified : []).filter(isRecord)
          .filter(u => typeof u.tool === "string")
          .map(u => ({ tool: String(u.tool),
                       verification: typeof u.verification === "string" ? u.verification : undefined,
                       evidence: typeof u.evidence === "string" ? u.evidence : undefined })) }
    : undefined;
  return { reply: data.reply, tools: parseToolActivities(data.tools, "done"),
           notes: notesTouched(data.tools), closeNotes: notesDismissed(data.tools),
           document: data.document, contextCut, closure, cancelled: data.cancelled === true };
}
export interface HeliosTransport {
  /** `thinking` es null cuando el motor no tiene canal de pensamiento. */
  status(signal?: AbortSignal): Promise<{ phase: HeliosPhase; mode: string; thinking: boolean | null;
    tools: ToolActivity[]; credentialRequest: CredentialRequest | null; progress: Progress; generation?: Generation }>;
  /** Guarda el acceso de un equipo. `host` fija su dirección: sin ella se busca
   *  entre los vecinos de la red, que solo sirve estando en la misma. */
  saveAccess(input: { device: string; user: string; password: string; host?: string; port?: number },
             signal?: AbortSignal): Promise<AccessSaved>;
  /** Retira la petición de acceso sin guardar nada, para que no vuelva a abrirse. */
  dismissAccess(device: string, signal?: AbortSignal): Promise<void>;
  /** Enciende o apaga el canal de pensamiento de Gemma. HexOS lo recuerda. */
  setThinking(enabled: boolean, signal?: AbortSignal): Promise<boolean>;
  /** Avisa a HexOS al empezar a escribir. Inicia la carga, pero no bloquea la UI. */
  warmup(signal?: AbortSignal): Promise<"unloaded" | "loading" | "ready" | "unloading" | "error" | "closed">;
  history(signal?: AbortSignal): Promise<HistoryMessage[]>;
  historyPage?(before?: number, signal?: AbortSignal): Promise<HistoryPage>;
  /** `image` es base64 de PNG/JPEG/WebP, sin la cabecera `data:`. Una por turno. */
  /** `thinking` abre el canal solo durante este turno; no cambia la preferencia AUTO. */
  send(text: string, signal?: AbortSignal, image?: string, thinking?: boolean, displayText?: string, requestId?: string): Promise<ChatReply>;
  cancel?(requestId: string): Promise<boolean>;
}

/** Existing HexOS HTTP contract, inspected 2026-09-12. No connection at import time.
 * Use a same-origin proxy in the host application; never connect the browser to
 * Héctor's shared memory / native protocol. Live snapshots are delivered by
 * status; cancellation targets the exact request and waits for its terminal reply.
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
      const r = data.credential_request;
      const g = data.generation;
      const generation = isRecord(g) && typeof g.request_id === "string" && typeof g.text === "string"
        ? { requestId: g.request_id, text: g.text, phase: String(g.phase ?? "preparing"),
            processed: typeof g.processed === "number" ? g.processed : 0,
            total: typeof g.total === "number" ? g.total : 0,
            cancellable: g.cancellable === true, cancelling: g.cancelling === true } : undefined;
      const credentialRequest = isRecord(r) && typeof r.device === "string"
        ? { device: r.device, host: typeof r.host === "string" ? r.host : undefined,
            mac: typeof r.mac === "string" ? r.mac : undefined, pinned: r.pinned === true,
            reason: typeof r.reason === "string" ? r.reason : undefined,
            port: typeof r.port === "number" ? r.port : undefined,
            user: typeof r.user === "string" ? r.user : undefined,
            requestedAt: typeof r.requested_at === "string" ? r.requested_at : undefined }
        : null;
      return { phase: phaseFromHexos(data.state), mode: data.mode, thinking,
               tools: parseToolActivities(data.active_tools, "running"), credentialRequest,
               progress: parseProgress(data.progress), generation };
    },
    async saveAccess({ device, user, password, host, port }, signal) {
      if (!device.trim() || !user.trim()) throw new Error("Faltan el equipo y el usuario");
      if (!password) throw new Error("Falta la contraseña");
      const body: Record<string, unknown> = { device, user, password };
      if (host && host.trim()) body.host = host.trim();
      if (typeof port === "number") body.port = port;
      const data = await request("credentials", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
      if (!isRecord(data) || data.saved !== true || typeof data.host !== "string") {
        throw new Error("HexOS no confirmó el acceso");
      }
      return { device: String(data.device), user: String(data.user),
               host: data.host, pinned: data.pinned === true,
               resume: typeof data.resume === "string" && data.resume.trim() ? data.resume : undefined,
               resumedRequest: typeof data.resumed_request === "string" ? data.resumed_request : undefined,
               resumed: data.resumed === undefined ? undefined : parseChatReply(data.resumed),
               resumeError: typeof data.resume_error === "string" ? data.resume_error : undefined };
    },
    async dismissAccess(device, signal) {
      await request("credentials", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device, dismiss: true }), signal });
    },
    async setThinking(enabled, signal) {
      const data = await request("thinking", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }), signal });
      if (!isRecord(data) || typeof data.thinking !== "boolean") throw new Error("HexOS no confirmó el cambio");
      return data.thinking;
    },
    async warmup(signal) {
      const data = await request("model/warmup", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: "{}", signal });
      if (!isRecord(data) || typeof data.state !== "string") throw new Error("HexOS no confirmó la carga del modelo");
      const states = ["unloaded", "loading", "ready", "unloading", "error", "closed"] as const;
      if (!states.includes(data.state as typeof states[number])) throw new Error("Estado del modelo no válido");
      return data.state as typeof states[number];
    },
    async history(signal) {
      const data = await request("history", { signal });
      if (!Array.isArray(data) || !data.every(row => row && (row.role === "user" || row.role === "assistant") && typeof row.text === "string")) throw new Error("Historial de HexOS no válido");
      return data.map(({ role, text }) => ({ role, text }));
    },
    async historyPage(before, signal) {
      const data = await request(`history?limit=100${before === undefined ? "" : `&before=${before}`}`, { signal });
      if (!isRecord(data) || !Array.isArray(data.messages) ||
          !data.messages.every(row => isRecord(row) && (row.role === "user" || row.role === "assistant") && typeof row.text === "string") ||
          !(data.next_before === null || (Number.isSafeInteger(data.next_before) && Number(data.next_before) > 0)))
        throw new Error("Página de historial de HexOS no válida");
      return { messages: data.messages.map(({ role, text }) => ({ role, text })), nextBefore: data.next_before as number | null };
    },
    async cancel(requestId) {
      const data = await request("cancel", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: requestId }) });
      return isRecord(data) && data.ok === true;
    },
    async send(text, signal, image, thinking, displayText, requestId) {
      if (!text.trim()) throw new Error("Escribe un mensaje");
      // Con imagen o razonamiento puntual el contrato es JSON; el chat ordinario
      // conserva text/plain para seguir siendo compatible con clientes anteriores.
      const init: RequestInit = image || thinking !== undefined || displayText !== undefined || requestId !== undefined
        ? { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, ...(image ? { image } : {}), ...(thinking !== undefined ? { thinking } : {}),
              ...(displayText !== undefined ? { display_text: displayText } : {}),
              ...(requestId ? { request_id: requestId } : {}) }), signal }
        : { method: "POST", headers: { "Content-Type": "text/plain; charset=utf-8" }, body: text, signal };
      const stop = () => {
        if (requestId) void fetcher(`${endpoint}/cancel`, { method: "POST", keepalive: true,
          headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request_id: requestId }) }).catch(() => {});
      };
      signal?.addEventListener("abort", stop, { once: true });
      try { return parseChatReply(await request("chat", init)); }
      finally { signal?.removeEventListener("abort", stop); }
    },
  };
}
