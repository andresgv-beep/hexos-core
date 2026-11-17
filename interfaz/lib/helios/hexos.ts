import { parseInferenceMetrics, type InferenceMetrics } from "./metrics";
import { phaseFromHexos, type HeliosPhase } from "./state";
import { notesDismissed, notesTouched, parseToolActivities, type ToolActivity } from "./tools";
import { displayUserText } from "./voice";

/** Llega el turno en que HexOS corta el contexto por lleno: lo anterior deja de
 *  estar en la ventana del modelo, aunque siga entero en el archivo. */
export interface ContextCut { at: string; messages: number; characters: number }
/** Cómo se cierra el turno según lo COMPROBADO, no según lo que diga la respuesta. */
export interface Closure { reason: string; note: string; unverified: { tool: string; verification?: string; evidence?: string }[] }
export interface ChatReply { reply: string; tools: ToolActivity[]; notes: string[]; closeNotes: string[] | "todas" | null; fileIds?: string[]; document?: unknown; contextCut?: ContextCut; closure?: Closure; cancelled?: boolean; incomplete?: boolean; /** Lo que Helios entendió de un mensaje de voz. */ transcript?: string }
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
  /** 'rejected' cuando ya había un acceso guardado y el equipo lo rechazó.
   *  'address_changed' cuando se guardó para una dirección que ya no es la registrada. */
  reason?: string; port?: number; user?: string;
  /** Con 'address_changed': la dirección para la que estaba guardado el acceso. */
  previousHost?: string;
  /** Marca de la petición. Cambia cada vez que se pide de nuevo, y es lo que
   *  distingue «la misma que ya descarté» de «me lo está pidiendo otra vez». */
  requestedAt?: string;
}
/** Plan de instalar o quitar un programa que Helios ha preparado y espera tu aprobación.
 *  Helios no puede ejecutarlo: solo lo hace HexOS cuando lo apruebas aquí. */
export interface SystemRequest {
  planId: string; summary: string; manager: string; action: "install" | "remove"; package: string;
  /** Paquetes que entran o salen según la simulación (los primeros 60). */
  affects: string[]; affectsCount: number;
}
/** Un fichero de la web tal como HexOS lo ha visto en el servidor, antes de bajarlo. */
export interface DownloadItem {
  name: string; host: string; url: string; kind: string;
  /** Lo que el servidor dice que pesa; null si no lo declara. */
  bytes: number | null;
}
/** Los ficheros que Helios propone bajar a este PC y esperan tu aprobación, todos en una tarjeta.
 *  Helios no puede descargarlos: solo los baja HexOS cuando lo apruebas aquí. Cada fichero que
 *  se suma estrena `planId`, así que se aprueba la lista que se ha visto. */
export interface DownloadRequest { planId: string; summary: string; folder: string; items: DownloadItem[] }
/** El `download_request` de /api/status, o null si no hay ninguno válido. Un fichero a medias
 *  invalida la tarjeta entera: no se enseña una lista distinta de la que se aprobaría. */
export function parseDownloadRequest(dr: unknown): DownloadRequest | null {
  if (!isRecord(dr) || typeof dr.plan_id !== "string" || typeof dr.summary !== "string"
      || !Array.isArray(dr.items) || !dr.items.length) return null;
  const items: DownloadItem[] = [];
  for (const f of dr.items) {
    if (!isRecord(f) || typeof f.name !== "string" || typeof f.url !== "string") return null;
    items.push({ name: f.name, host: String(f.host ?? ""), url: f.url, kind: String(f.kind ?? ""),
                 bytes: typeof f.bytes === "number" ? f.bytes : null });
  }
  return { planId: dr.plan_id, summary: dr.summary, folder: String(dr.folder ?? ""), items };
}
/** Un fichero ya descargado. `viewable`: el navegador puede enseñarlo; `readable`: Helios puede leerlo. */
export interface DownloadedFile { id: string; name: string; kind: string; bytes: number; ts: string; source: string;
  onDisk: boolean; viewable: boolean; readable: boolean }
export interface Downloads { folder: string; files: DownloadedFile[] }
export function parseDownloads(data: unknown): Downloads {
  if (!isRecord(data) || !Array.isArray(data.downloads)) throw new Error("Lista de descargas no válida");
  return { folder: String(data.folder ?? ""), files: data.downloads.filter(isRecord)
    .filter(f => typeof f.id === "string" && typeof f.name === "string")
    .map(f => ({ id: String(f.id), name: String(f.name), kind: String(f.kind ?? ""),
      bytes: typeof f.bytes === "number" ? f.bytes : 0, ts: String(f.ts ?? ""), source: String(f.source ?? ""),
      onDisk: f.on_disk === true, viewable: f.viewable === true, readable: f.readable === true })) };
}
/** Un fichero dentro de la tarjeta de cambios: qué se crea o cambia y sus líneas. */
export interface FileChange {
  path: string; kind: "create" | "replace" | "edit"; added: number; removed: number;
  /** Líneas del diff unificado (las primeras 400) y cuántas tiene entero. */
  diff: string[]; diffLines: number;
}
/** Los cambios en ficheros del proyecto que Helios ha preparado y esperan tu aprobación, todos
 *  juntos. Helios no puede escribirlos: los escribe HexOS cuando los apruebas aquí. */
export interface ProjectChange {
  planId: string; summary: string; projectName: string; added: number; removed: number;
  changes: FileChange[];
}
/** El `project_request` de /api/status, o null si no hay ninguno válido. */
export function parseProjectChange(pr: unknown): ProjectChange | null {
  if (!pr || typeof pr !== "object") return null;
  const r = pr as Record<string, unknown>;
  if (typeof r.plan_id !== "string" || typeof r.summary !== "string" || !Array.isArray(r.changes)) return null;
  const numero = (valor: unknown) => typeof valor === "number" ? valor : 0;
  const changes = r.changes.flatMap((entrada): FileChange[] => {
    if (!entrada || typeof entrada !== "object") return [];
    const c = entrada as Record<string, unknown>;
    if (typeof c.path !== "string" || (c.kind !== "create" && c.kind !== "replace" && c.kind !== "edit")) return [];
    const diff = Array.isArray(c.diff) ? c.diff.filter((x): x is string => typeof x === "string") : [];
    return [{ path: c.path, kind: c.kind, added: numero(c.added), removed: numero(c.removed), diff,
              diffLines: typeof c.diff_lines === "number" ? c.diff_lines : diff.length }];
  });
  if (!changes.length) return null;
  return { planId: r.plan_id, summary: r.summary, projectName: String(r.project_name ?? ""),
           added: numero(r.added), removed: numero(r.removed), changes };
}
/** Con este texto queda en el archivo la comprobación que la interfaz pide sola tras aprobar
 *  un cambio. No lo escribió la persona, así que la conversación no lo enseña como suyo. */
export const AUTO_CHECK_LABEL = "Comprobación tras aprobar";
/** Cómo acabó un plan aprobado o rechazado. */
export interface SystemDecision {
  summary: string; executed: boolean; verified?: boolean; cancelled?: boolean;
  refused?: string; check?: string;
  /** Lo que la interfaz le pide a Helios nada más aprobar: comprobar lo que se acaba de escribir. */
  resume?: string;
}
/** Cómo acabó cada fichero de una tarjeta de descargas aprobada. */
export interface DownloadOutcome { name: string; executed: boolean; verified: boolean; refused?: string; check?: string }
export interface DownloadDecision extends SystemDecision { files: DownloadOutcome[] }
/** Lo que se le dice a la persona cuando HexOS termina con una tarjeta de descargas. Con varios
 *  ficheros va uno por línea: el que falló se nombra, no se pierde entre los que salieron bien. */
export function downloadReply(r: DownloadDecision): string {
  if (r.cancelled) return `Cancelado: ${r.summary}. No se ha descargado nada.`;
  if (r.files.length < 2) {
    const f = r.files[0] ?? r;
    return f.executed && f.verified ? `Descargado y comprobado: ${f.check}. Lo tienes en Descargas.`
      : f.executed ? `Se descargó, pero lo guardado no coincide con lo recibido: ${f.check}. No te fíes de ese fichero.`
      : `No se descargó: ${f.refused ?? "hubo un error"}.`;
  }
  const buenos = r.files.filter(f => f.executed && f.verified).length;
  const cabecera = buenos === r.files.length ? `Descargados y comprobados los ${buenos} ficheros. Los tienes en Descargas.`
    : buenos ? `Descargados y comprobados ${buenos} de ${r.files.length} ficheros. Los que han salido bien están en Descargas.`
    : `No se descargó ninguno de los ${r.files.length} ficheros.`;
  const lineas = r.files.map(f => `- \`${f.name}\`: ` + (f.executed && f.verified ? "descargado y comprobado"
    : f.executed ? "se descargó, pero lo guardado no coincide con lo recibido; no te fíes de ese fichero"
    : `no se descargó: ${f.refused ?? "hubo un error"}`));
  return `${cabecera}\n\n${lineas.join("\n")}`;
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
           ...(typeof data.transcript === "string" && data.transcript.trim() ? { transcript: data.transcript } : {}),
           fileIds: data.tools.filter(isRecord).filter(item => item.tool === 'nas.file_open' && !item.failed)
             .map(item => isRecord(item.result) ? item.result.file_id : null)
             .filter((id): id is string => typeof id === 'string' && /^[a-f0-9]{32}$/.test(id)),
           notes: notesTouched(data.tools), closeNotes: notesDismissed(data.tools),
           document: data.document, contextCut, closure, cancelled: data.cancelled === true,
           incomplete: data.incomplete === true };
}
/** Los dos espacios de trabajo del agente. */
export type HeliosWindow = "chat" | "agente";
/** Un proyecto del Agente: su carpeta y su conversación propia. */
export interface Project { id: string; name: string; folder: string; used: string }
export interface ProjectList { active: string | null; projects: Project[];
  /** Dónde se crean las carpetas de los proyectos nuevos, para enseñar el destino antes de crear. */
  root?: string }

/** Una llamada a herramienta ya hecha, con una línea que dice qué se pidió. */
export interface ActivityCall { seq: number; ts: string; tool: string; summary: string; failed: boolean; seconds: number | null }
/** Algo que cambió: una herramienta con efecto o una decisión tomada en una tarjeta. */
export interface ActivityChange { ts: string; kind: "tool" | "decision"; text: string }
export interface Activity { tools: ActivityCall[]; changes: ActivityChange[] }
export interface ActivityDetail { seq: number; tool: string; arguments: Record<string, unknown>; output: string; truncated: boolean; failed: boolean }

function parseProject(value: unknown): Project | null {
  return isRecord(value) && typeof value.id === "string" && typeof value.name === "string" &&
    typeof value.folder === "string"
    ? { id: value.id, name: value.name, folder: value.folder, used: typeof value.used === "string" ? value.used : "" }
    : null;
}

/** Un servicio externo que se enchufa con clave. La clave nunca viene: solo si está y cómo acaba. */
export interface ServiceProvider { id: string; name: string; kind: string; site: string; note: string;
  placeholder: string; configured: boolean; hint: string | null }
/** `search` es el buscador que usa Helios ahora mismo. */
export interface Settings { web: { search: string; providers: ServiceProvider[] } }

export function parseSettings(data: unknown): Settings {
  const web = isRecord(data) && isRecord(data.web) ? data.web : null;
  if (!web || typeof web.search !== "string" || !Array.isArray(web.providers)) throw new Error("Ajustes de HexOS no válidos");
  return { web: { search: web.search, providers: web.providers.filter(isRecord).map(item => ({
    id: String(item.id), name: String(item.name), kind: String(item.kind), site: String(item.site ?? ""),
    note: String(item.note ?? ""), placeholder: String(item.placeholder ?? ""),
    configured: item.configured === true, hint: typeof item.hint === "string" ? item.hint : null })) } };
}

/** Un modelo de la lista de HexOS. `available` es false si su fichero no está (disco sin montar). */
export type ModelChoice = { id: string; name: string; ctx: number; active: boolean; available: boolean };

function parseModels(data: unknown): ModelChoice[] {
  if (!isRecord(data) || !Array.isArray(data.models)) throw new Error("Lista de modelos de HexOS no válida");
  return data.models.map(item => {
    if (!isRecord(item) || typeof item.id !== "string" || typeof item.name !== "string" || typeof item.ctx !== "number"
        || typeof item.active !== "boolean" || typeof item.available !== "boolean") {
      throw new Error("Lista de modelos de HexOS no válida");
    }
    return { id: item.id, name: item.name, ctx: item.ctx, active: item.active, available: item.available };
  });
}

export interface HeliosTransport {
  /** `thinking` es null cuando el motor no tiene canal de pensamiento.
   *  `window` es null si el agente no reparte las herramientas por ventana. */
  status(signal?: AbortSignal): Promise<{ phase: HeliosPhase; mode: string; thinking: boolean | null;
    window: HeliosWindow | null;
    /** El proyecto puesto en el Agente; null si trabaja sin proyecto, y `undefined`
     *  si este HexOS es anterior a los proyectos y no hay nada que enseñar. */
    project?: string | null;
    tools: ToolActivity[]; credentialRequest: CredentialRequest | null; systemRequest: SystemRequest | null;
    projectChange: ProjectChange | null;
    /** `undefined` si este HexOS es anterior a las descargas. */
    downloadRequest?: DownloadRequest | null;
    progress: Progress; generation?: Generation; metrics?: InferenceMetrics }>;
  /** Aprueba o rechaza el plan pendiente. Aprobarlo lo ejecuta HexOS y lo comprueba. */
  decideSystem(planId: string, approve: boolean, signal?: AbortSignal): Promise<SystemDecision>;
  /** Aprueba o rechaza la descarga pendiente. Aprobarla la baja HexOS y comprueba lo guardado. */
  decideDownload?(planId: string, approve: boolean, signal?: AbortSignal): Promise<DownloadDecision>;
  /** Lo descargado hasta ahora, lo más nuevo primero. */
  downloads?(signal?: AbortSignal): Promise<Downloads>;
  /** La dirección de un fichero descargado: para verlo en el navegador o, con `save`, para guardarlo. */
  downloadUrl?(id: string, save?: boolean): string;
  /** Aprueba o rechaza el cambio de fichero pendiente. Aprobarlo lo escribe HexOS y lo relee. */
  decideProjectChange(planId: string, approve: boolean, signal?: AbortSignal): Promise<SystemDecision>;
  /** Guarda el acceso de un equipo. `host` fija su dirección: sin ella se busca
   *  entre los vecinos de la red, que solo sirve estando en la misma. */
  saveAccess(input: { device: string; user: string; password: string; host?: string; port?: number },
             signal?: AbortSignal): Promise<AccessSaved>;
  /** Retira la petición de acceso sin guardar nada, para que no vuelva a abrirse. */
  dismissAccess(device: string, signal?: AbortSignal): Promise<void>;
  /** Enciende o apaga el canal de pensamiento de Gemma. HexOS lo recuerda. */
  setThinking(enabled: boolean, signal?: AbortSignal): Promise<boolean>;
  /** Cambia el espacio de trabajo. Decide qué herramientas se le declaran al modelo:
   *  en «chat» no ve el NAS ni la terminal. HexOS lo recuerda entre reinicios. */
  setWindow(window: HeliosWindow, signal?: AbortSignal): Promise<HeliosWindow>;
  /** Empieza de cero el contexto de la ventana actual. El archivo no se borra: lo
   *  anterior sigue en el historial y Helios puede consultarlo, pero ya no lo tiene delante. */
  clearContext?(signal?: AbortSignal): Promise<void>;
  /** Lo hecho en la conversación puesta: llamadas y cambios, lo más nuevo primero. */
  activity?(signal?: AbortSignal): Promise<Activity>;
  /** Argumentos y salida de una llamada, con tope. */
  activityDetail?(seq: number, signal?: AbortSignal): Promise<ActivityDetail>;
  /** Los proyectos del Agente y cuál está puesto. */
  projects?(signal?: AbortSignal): Promise<ProjectList>;
  /** Crea un proyecto con su carpeta y pasa a trabajar en él. Sin `folder` se crea una nueva. */
  createProject?(name: string, folder?: string, signal?: AbortSignal): Promise<string>;
  /** Cambia de proyecto; null vuelve al Agente sin proyecto. Devuelve el que queda puesto. */
  setProject?(id: string | null, signal?: AbortSignal): Promise<string | null>;
  /** Cambia el nombre que se ve; la carpeta y la conversación siguen siendo las mismas. */
  renameProject?(id: string, name: string, signal?: AbortSignal): Promise<void>;
  /** Lo saca de la lista sin borrar su carpeta ni su conversación. Devuelve el que queda puesto. */
  removeProject?(id: string, signal?: AbortSignal): Promise<string | null>;
  /** Servicios externos y cuáles tienen clave. */
  settings?(signal?: AbortSignal): Promise<Settings>;
  /** Guarda la clave de un servicio; con null la quita. Devuelve los ajustes como quedan. */
  saveServiceKey?(provider: string, key: string | null, signal?: AbortSignal): Promise<Settings>;
  /** Hace una llamada real al servicio con la clave guardada. Devuelve cuántos resultados trajo. */
  testService?(provider: string, signal?: AbortSignal): Promise<number>;
  /** Los modelos entre los que se puede elegir. Vacío si el servicio arrancó con uno solo. */
  models?(signal?: AbortSignal): Promise<ModelChoice[]>;
  /** Cambia de modelo: el que había se descarga y el nuevo empieza a cargarse. Devuelve la
   *  lista como queda. Falla, sin cambiar nada, si hay un turno en marcha. */
  selectModel?(id: string, signal?: AbortSignal): Promise<ModelChoice[]>;
  /** Avisa a HexOS al empezar a escribir. Inicia la carga, pero no bloquea la UI. */
  warmup(signal?: AbortSignal): Promise<"unloaded" | "loading" | "ready" | "unloading" | "error" | "closed">;
  history(signal?: AbortSignal): Promise<HistoryMessage[]>;
  historyPage?(before?: number, signal?: AbortSignal): Promise<HistoryPage>;
  /** `image` es base64 de PNG/JPEG/WebP, sin la cabecera `data:`. Una por turno. */
  /** `thinking` abre el canal solo durante este turno; no cambia la preferencia AUTO. */
  /** `audio` es base64 de un WAV mono 16 kHz de hasta 30 s. Imagen o audio, no ambos. */
  send(text: string, signal?: AbortSignal, image?: string, thinking?: boolean, displayText?: string, requestId?: string, audio?: string): Promise<ChatReply>;
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
      // `ventana`, no `window`: dentro de esta función taparía el objeto del navegador.
      const ventana = data.window === "chat" || data.window === "agente" ? data.window : null;
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
            previousHost: typeof r.access_stale === "string" ? r.access_stale : undefined,
            port: typeof r.port === "number" ? r.port : undefined,
            user: typeof r.user === "string" ? r.user : undefined,
            requestedAt: typeof r.requested_at === "string" ? r.requested_at : undefined }
        : null;
      const sr = data.system_request;
      const systemRequest: SystemRequest | null = isRecord(sr) && typeof sr.plan_id === "string" &&
          typeof sr.summary === "string" && (sr.action === "install" || sr.action === "remove")
        ? { planId: sr.plan_id, summary: sr.summary, manager: String(sr.manager ?? ""), action: sr.action,
            package: String(sr.package ?? ""),
            affects: Array.isArray(sr.affects) ? sr.affects.filter((x): x is string => typeof x === "string") : [],
            affectsCount: typeof sr.affects_count === "number" ? sr.affects_count : 0 }
        : null;
      const project = typeof data.project === "string" ? data.project : data.project === null ? null : undefined;
      return { phase: phaseFromHexos(data.state), mode: data.mode, thinking, window: ventana, project,
               tools: parseToolActivities(data.active_tools, "running"), credentialRequest, systemRequest,
               projectChange: parseProjectChange(data.project_request),
               downloadRequest: "download_request" in data ? parseDownloadRequest(data.download_request) : undefined,
               progress: parseProgress(data.progress), generation, metrics: parseInferenceMetrics(data.metrics) };
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
    async decideSystem(planId, approve, signal) {
      const data = await request("system", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan_id: planId, approve }), signal });
      if (!isRecord(data) || typeof data.summary !== "string") throw new Error("HexOS no confirmó la decisión");
      return { summary: data.summary, executed: data.executed === true,
               verified: typeof data.verified === "boolean" ? data.verified : undefined,
               cancelled: data.cancelled === true,
               refused: typeof data.refused === "string" ? data.refused : undefined,
               check: typeof data.check === "string" ? data.check : undefined };
    },
    async decideDownload(planId, approve, signal) {
      const data = await request("download", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan_id: planId, approve }), signal });
      if (!isRecord(data) || typeof data.summary !== "string") throw new Error("HexOS no confirmó la decisión");
      const files = (Array.isArray(data.files) ? data.files : []).filter(isRecord).map(f => ({
        name: String(f.name ?? ""), executed: f.executed === true, verified: f.verified === true,
        refused: typeof f.refused === "string" ? f.refused : undefined,
        check: typeof f.check === "string" ? f.check : undefined }));
      return { summary: data.summary, executed: data.executed === true,
               verified: typeof data.verified === "boolean" ? data.verified : undefined,
               cancelled: data.cancelled === true,
               refused: typeof data.refused === "string" ? data.refused : undefined,
               check: typeof data.check === "string" ? data.check : undefined, files };
    },
    async downloads(signal) {
      return parseDownloads(await request("downloads", { signal }));
    },
    downloadUrl(id, save) {
      return `${endpoint}/downloads/${encodeURIComponent(id)}${save ? "/download" : ""}`;
    },
    async decideProjectChange(planId, approve, signal) {
      const data = await request("project/change", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan_id: planId, approve }), signal });
      if (!isRecord(data) || typeof data.summary !== "string") throw new Error("HexOS no confirmó la decisión");
      return { summary: data.summary, executed: data.executed === true,
               verified: typeof data.verified === "boolean" ? data.verified : undefined,
               cancelled: data.cancelled === true,
               refused: typeof data.refused === "string" ? data.refused : undefined,
               check: typeof data.check === "string" ? data.check : undefined,
               resume: typeof data.resume === "string" && data.resume.trim() ? data.resume : undefined };
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
    async setWindow(ventana, signal) {
      const data = await request("window", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ window: ventana }), signal });
      if (!isRecord(data) || (data.window !== "chat" && data.window !== "agente")) {
        throw new Error("HexOS no confirmó el espacio de trabajo");
      }
      return data.window;
    },
    async settings(signal) {
      return parseSettings(await request("settings", { signal }));
    },
    async saveServiceKey(provider, key, signal) {
      return parseSettings(await request("settings/web", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, key }), signal }));
    },
    async testService(provider, signal) {
      const data = await request("settings/web/test", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider }), signal });
      if (!isRecord(data) || data.ok !== true || typeof data.results !== "number") throw new Error("HexOS no confirmó la prueba");
      return data.results;
    },
    async activity(signal) {
      const data = await request("activity", { signal });
      if (!isRecord(data) || !Array.isArray(data.tools) || !Array.isArray(data.changes)) throw new Error("Actividad de HexOS no válida");
      return {
        tools: data.tools.flatMap(t => isRecord(t) && typeof t.seq === "number" && typeof t.tool === "string"
          ? [{ seq: t.seq, ts: String(t.ts ?? ""), tool: t.tool, summary: typeof t.summary === "string" ? t.summary : "",
               failed: t.failed === true, seconds: typeof t.seconds === "number" ? t.seconds : null }] : []),
        changes: data.changes.flatMap(c => isRecord(c) && typeof c.text === "string"
          ? [{ ts: String(c.ts ?? ""), kind: c.kind === "decision" ? "decision" as const : "tool" as const, text: c.text }] : []),
      };
    },
    async activityDetail(seq, signal) {
      const data = await request(`activity/${seq}`, { signal });
      if (!isRecord(data) || typeof data.tool !== "string" || typeof data.output !== "string") throw new Error("Detalle de la llamada no válido");
      return { seq, tool: data.tool, arguments: isRecord(data.arguments) ? data.arguments : {}, output: data.output,
               truncated: data.truncated === true, failed: data.failed === true };
    },
    async projects(signal) {
      const data = await request("projects", { signal });
      if (!isRecord(data) || !Array.isArray(data.projects)) throw new Error("Lista de proyectos de HexOS no válida");
      return { active: typeof data.active === "string" ? data.active : null,
               projects: data.projects.map(parseProject).filter((p): p is Project => p !== null),
               ...(typeof data.root === "string" ? { root: data.root } : {}) };
    },
    async createProject(name, folder, signal) {
      if (!name.trim()) throw new Error("Ponle un nombre al proyecto");
      const data = await request("projects", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(folder?.trim() ? { name, folder: folder.trim() } : { name }), signal });
      if (!isRecord(data) || typeof data.active !== "string") throw new Error("HexOS no confirmó el proyecto");
      return data.active;
    },
    async setProject(id, signal) {
      const data = await request("project", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }), signal });
      if (!isRecord(data) || !(data.active === null || typeof data.active === "string")) {
        throw new Error("HexOS no confirmó el cambio de proyecto");
      }
      return data.active;
    },
    async renameProject(id, name, signal) {
      if (!name.trim()) throw new Error("Ponle un nombre al proyecto");
      const data = await request("project/rename", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, name }), signal });
      if (!isRecord(data) || !isRecord(data.project)) throw new Error("HexOS no confirmó el nombre nuevo");
    },
    async removeProject(id, signal) {
      const data = await request("project/remove", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }), signal });
      if (!isRecord(data) || data.removed !== id) throw new Error("HexOS no confirmó que lo quitara");
      return typeof data.active === "string" ? data.active : null;
    },
    async clearContext(signal) {
      const data = await request("context/reset", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: "{}", signal });
      if (!isRecord(data) || data.ok !== true) throw new Error("HexOS no confirmó la limpieza");
    },
    async models(signal) {
      return parseModels(await request("models", { signal }));
    },
    async selectModel(id, signal) {
      return parseModels(await request("model/select", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }), signal }));
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
      return data.map(({ role, text }) => ({ role, text: role === "user" ? displayUserText(text) : text }));
    },
    async historyPage(before, signal) {
      const data = await request(`history?limit=100${before === undefined ? "" : `&before=${before}`}`, { signal });
      if (!isRecord(data) || !Array.isArray(data.messages) ||
          !data.messages.every(row => isRecord(row) && (row.role === "user" || row.role === "assistant") && typeof row.text === "string") ||
          !(data.next_before === null || (Number.isSafeInteger(data.next_before) && Number(data.next_before) > 0)))
        throw new Error("Página de historial de HexOS no válida");
      return { messages: data.messages.map(({ role, text }) => ({ role, text: role === "user" ? displayUserText(String(text)) : text })), nextBefore: data.next_before as number | null };
    },
    async cancel(requestId) {
      const data = await request("cancel", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: requestId }) });
      return isRecord(data) && data.ok === true;
    },
    async send(text, signal, image, thinking, displayText, requestId, audio) {
      if (!text.trim()) throw new Error("Escribe un mensaje");
      // Con imagen o razonamiento puntual el contrato es JSON; el chat ordinario
      // conserva text/plain para seguir siendo compatible con clientes anteriores.
      const init: RequestInit = image || audio || thinking !== undefined || displayText !== undefined || requestId !== undefined
        ? { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, ...(image ? { image } : {}), ...(audio ? { audio } : {}), ...(thinking !== undefined ? { thinking } : {}),
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
