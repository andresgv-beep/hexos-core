/** El núcleo: lo que Helios guarda en su propio equipo.
 *
 *  Va aparte del transporte del chat a propósito. El panel se pinta leyendo
 *  directamente, sin gastar un turno del modelo, pero del MISMO recuento que
 *  responde en la conversación: si contaran por separado, un día dirían cosas
 *  distintas y no habría manera de saber cuál miente.
 */
export interface CoreSection {
  key: string; label: string; tool: string;
  /** null cuando no se pudo contar. No es cero: es no saber, y se explica en `unknown`. */
  total: number | null;
  pending?: number; unknown?: string; unreadable?: number;
}
export interface CoreFavorite { kind: string; id: string; title: string; state: string; updatedAt: string }
export interface CoreOverview { sections: CoreSection[]; favorites: CoreFavorite[]; note: string }
export interface NoteSummary {
  id: string; title: string; body: string; state: string; favorite: boolean;
  tags: string[]; updatedAt: string; revision: number; truncated: boolean;
}
export interface NoteRevision { ts: string; revision: number; actor: string; title: string; body: string }
export interface NoteDetail extends Omit<NoteSummary, "truncated"> { revisions: NoteRevision[] }

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function text(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}
function count(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function parseSection(value: unknown): CoreSection | null {
  if (!isRecord(value) || typeof value.key !== "string") return null;
  const section: CoreSection = {
    key: value.key, label: text(value.label, value.key), tool: text(value.tool),
    total: count(value.total),
  };
  if (typeof value.pending === "number") section.pending = value.pending;
  if (typeof value.unknown === "string") section.unknown = value.unknown;
  if (typeof value.unreadable === "number") section.unreadable = value.unreadable;
  return section;
}
function parseNote(value: unknown): NoteSummary | null {
  if (!isRecord(value) || typeof value.id !== "string") return null;
  return {
    id: value.id, title: text(value.title), body: text(value.body),
    state: text(value.state, "pendiente"), favorite: value.favorite === true,
    tags: Array.isArray(value.tags) ? value.tags.filter((t): t is string => typeof t === "string") : [],
    updatedAt: text(value.updated_at), revision: count(value.revision) ?? 0,
    truncated: value.truncated === true,
  };
}

export interface CoreClient {
  overview(signal?: AbortSignal): Promise<CoreOverview>;
  notes(query?: { query?: string; state?: string; favorite?: boolean }, signal?: AbortSignal): Promise<NoteSummary[]>;
  note(id: string, signal?: AbortSignal): Promise<NoteDetail>;
}

export function createCoreClient(base = "/api", fetcher: typeof fetch = fetch): CoreClient {
  const endpoint = base.replace(/\/$/, "");
  async function read(path: string, signal?: AbortSignal): Promise<unknown> {
    const response = await fetcher(`${endpoint}/${path}`, { cache: "no-store", signal });
    const data: unknown = await response.json();
    if (!response.ok) {
      throw new Error(isRecord(data) && typeof data.error === "string" ? data.error : `HexOS: HTTP ${response.status}`);
    }
    return data;
  }
  return {
    async overview(signal) {
      const data = await read("core", signal);
      if (!isRecord(data) || !Array.isArray(data.sections)) throw new Error("Núcleo de HexOS no válido");
      return {
        sections: data.sections.map(parseSection).filter((s): s is CoreSection => s !== null),
        favorites: (Array.isArray(data.favorites) ? data.favorites : []).filter(isRecord)
          .filter(f => typeof f.id === "string")
          .map(f => ({ kind: text(f.kind, "nota"), id: String(f.id), title: text(f.title),
                       state: text(f.state), updatedAt: text(f.updated_at) })),
        note: text(data.note),
      };
    },
    async notes(query, signal) {
      const params = new URLSearchParams();
      if (query?.query) params.set("query", query.query);
      if (query?.state) params.set("state", query.state);
      if (query?.favorite !== undefined) params.set("favorite", String(query.favorite));
      const suffix = params.toString();
      const data = await read(`notes${suffix ? `?${suffix}` : ""}`, signal);
      if (!Array.isArray(data)) throw new Error("Lista de notas no válida");
      return data.map(parseNote).filter((n): n is NoteSummary => n !== null);
    },
    async note(id, signal) {
      const data = await read(`notes/${encodeURIComponent(id)}`, signal);
      const nota = parseNote(data);
      if (!nota || !isRecord(data)) throw new Error("Nota no válida");
      return {
        ...nota,
        revisions: (Array.isArray(data.revisions) ? data.revisions : []).filter(isRecord)
          .map(r => ({ ts: text(r.ts), revision: count(r.revision) ?? 0, actor: text(r.actor),
                       title: text(r.title), body: text(r.body) })),
      };
    },
  };
}

/** Herramientas del turno que hablan del núcleo. La expansión se dispara con lo
 *  que REALMENTE se ejecutó, nunca adivinando por las palabras del mensaje: si no,
 *  el núcleo se abriría mientras Helios habla de otra cosa. */
export function coreSectionForTools(tools: { name: string }[]): string | null {
  for (const { name } of [...tools].reverse()) {
    if (name.startsWith("note.")) return "notas";
    if (name === "core.overview") return "";
    if (name.startsWith("report.")) return "informes";
    if (name.startsWith("work.")) return "fichas";
  }
  return null;
}

/** Una nota como documento de texto. El .md es el formato honesto: una nota ES
 *  texto, se abre en cualquier cosa y no pierde un carácter por el camino. */
export function noteAsMarkdown(note: { title: string; body: string; state: string; tags: string[]; updatedAt: string }): string {
  const encabezado = [`# ${note.title}`, "", `Estado: ${note.state}`];
  if (note.tags.length) encabezado.push(`Etiquetas: ${note.tags.join(", ")}`);
  if (note.updatedAt) encabezado.push(`Última modificación: ${note.updatedAt}`);
  return [...encabezado, "", note.body, ""].join("\n");
}

/** Nombre de archivo a partir del título, sin sorpresas para el sistema de archivos. */
export function noteFilename(title: string): string {
  const limpio = title.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase();
  return `${limpio.slice(0, 60) || "nota"}.md`;
}
