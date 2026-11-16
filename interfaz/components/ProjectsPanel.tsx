"use client";

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Check, FolderOpen, Pencil, Plus, Trash2, X } from "lucide-react";
import type { Project } from "@/lib/helios/hexos";
import type { InferenceMetrics } from "@/lib/helios/metrics";

/** La misma regla que HexOS para sacar del nombre el identificador y la carpeta: sin acentos,
 *  en minúsculas y con guiones. Solo sirve para enseñar la propuesta; quien decide es HexOS. */
function etiqueta(nombre: string): string {
  return nombre.normalize("NFKD").replace(/[^ -~]/g, "").toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48).replace(/-+$/, "");
}

/** La carpeta que HexOS le daría a un proyecto con ese nombre, o "" si el nombre no da para una. */
export function carpetaPropuesta(root: string, nombre: string): string {
  return nombre.trim() && etiqueta(nombre) ? `${root}/${etiqueta(nombre)}` : "";
}

/** La ventana de «Proyecto nuevo»: nombre y carpeta. Estaba fija en el lateral y se comía la
 *  altura de la lista de proyectos y de las herramientas; ahora solo existe mientras se crea uno. */
export function NewProjectForm({ root, busy, error, onCreate, onClose }: {
  root: string; busy: boolean; error: string;
  onCreate: (name: string, folder: string) => Promise<boolean>; onClose: () => void;
}) {
  const [name, setName] = useState("");
  // La carpeta se enseña ya escrita, calculada con el nombre, hasta que la persona la toca:
  // así se ve dónde va a ir y se puede cambiar el destino o apuntar a una que ya existe.
  const [folder, setFolder] = useState("");
  const [carpetaTocada, setCarpetaTocada] = useState(false);
  // El error del panel es de todo lo que se hace con proyectos: aquí solo cuenta el de este intento.
  const [intentado, setIntentado] = useState(false);
  const carpeta = carpetaTocada ? folder : carpetaPropuesta(root, name);
  const campo = useRef<HTMLInputElement>(null);
  const cerrar = useRef(onClose);
  useEffect(() => { cerrar.current = onClose; }, [onClose]);
  useEffect(() => {
    campo.current?.focus();
    const tecla = (event: KeyboardEvent) => { if (event.key === "Escape") cerrar.current(); };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, []);
  async function crear(event: FormEvent) {
    event.preventDefault();
    if (busy || !name.trim()) return;
    setIntentado(true);
    // Sin tocar, decide HexOS con su misma regla; tocada, se le manda la que se ha escrito.
    if (await onCreate(name, carpetaTocada ? folder.trim() : "")) onClose();
  }
  return <div className="access-backdrop">
    <form className="access-panel project-new-panel" role="dialog" aria-modal="true" aria-labelledby="project-new-title"
      onSubmit={event => void crear(event)}>
      <h2 id="project-new-title" className="panel-title">Proyecto nuevo</h2>
      <label className="access-field">Nombre
        <input ref={campo} value={name} maxLength={80} placeholder="Cómo se va a llamar" autoComplete="off"
          disabled={busy} onChange={event => setName(event.target.value)} />
      </label>
      <label className="access-field">Carpeta
        <input className="project-new-folder" value={carpeta} placeholder={`${root}/…`} autoComplete="off" spellCheck={false}
          disabled={busy} title={carpeta}
          onChange={event => { setCarpetaTocada(true); setFolder(event.target.value); }} />
      </label>
      <p className="access-note">{carpetaTocada
        ? <>Se usará esa ruta: si ya existe, tal cual; si no, se crea. <button type="button" disabled={busy}
            onClick={() => { setCarpetaTocada(false); setFolder(""); }}>Volver a la propuesta</button></>
        : "Se crea ahí si no existe. Cámbiala para elegir otro destino o usar una carpeta que ya tienes."}</p>
      {intentado && error && <p className="attachment-error" role="alert">{error}</p>}
      <div className="access-actions">
        <button type="button" disabled={busy} onClick={onClose}>Cancelar</button>
        <button type="submit" className="access-save" disabled={busy || !name.trim()}>{busy ? "Creando…" : "Crear proyecto"}</button>
      </div>
    </form>
  </div>;
}

const integer = new Intl.NumberFormat("es-ES");
const decimal = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 });

/** Contexto y velocidad, al fondo del lateral: en el Agente salen de debajo del chat para
 *  dejar limpia la zona de escribir. */
function AgentMeter({ metrics, action }: { metrics?: InferenceMetrics; action?: ReactNode }) {
  const used = metrics?.contextUsed;
  const capacity = metrics?.contextCapacity;
  const percent = used != null && capacity != null ? used / capacity * 100 : null;
  const speed = metrics?.tokensPerSecond;
  return <section className="vision-agent-meter" aria-label="Contexto y velocidad" data-full={percent != null && percent >= 90}>
    <div><span>Contexto</span><strong>{percent == null ? "—" : `${Math.round(percent)} %`}</strong></div>
    <span className="inference-track" role="meter" aria-label="Ocupación del contexto"
      aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent == null ? undefined : Math.min(100, percent)}
      aria-valuetext={percent == null ? "Sin medición" : `${integer.format(used!)} de ${integer.format(capacity!)} tokens`}
      title="Tokens en la caché del modelo; el historial visible puede ser más largo.">
      <span style={{ width: `${Math.min(100, percent ?? 0)}%` }} />
    </span>
    <p>{percent == null ? "Sin medición todavía" : `${integer.format(used!)} de ${integer.format(capacity!)} tokens`}</p>
    <div title="Media del turno: tokens / tiempo de decodificación. Se actualiza tras cada generación; excluye prefill y herramientas.">
      <span>Generación</span><strong>{speed == null ? "—" : `${decimal.format(speed)} tok/s`}</strong></div>
    {action}
  </section>;
}

/** Los proyectos del Agente. Cada uno tiene su carpeta y su conversación: cambiar de
 *  proyecto es dejar una y seguir en otra, sin que Helios mezcle lo de las dos. */
export function ProjectsPanel({ projects, root = "~/Helios/proyectos", active, busy, error, fixed, metrics, controls, meterAction, now, activity, onSelect, onCreate, onRename, onRemove, onClose }: {
  projects: Project[];
  /** Dónde se crean las carpetas nuevas si no se indica otra. */
  root?: string;
  active: string | null;
  busy: boolean;
  error: string;
  /** En el escritorio es el lateral fijo del Agente; en el móvil, un panel que se abre y se cierra. */
  fixed?: boolean;
  /** Solo en el lateral fijo: la tarjeta de contexto y velocidad del fondo. */
  metrics?: InferenceMetrics;
  /** Solo en el lateral fijo: los botones de arriba (razonamiento, historial). */
  controls?: ReactNode;
  /** Solo en el lateral fijo: lo que se puede hacer con el contexto, dentro de su tarjeta. */
  meterAction?: ReactNode;
  /** Solo en el lateral fijo: lo que Helios está haciendo ahora, arriba del todo. */
  now?: ReactNode;
  /** Solo en el lateral fijo: herramientas ejecutadas y cambios, en el centro. */
  activity?: ReactNode;
  onSelect: (id: string | null) => void;
  onCreate: (name: string, folder: string) => Promise<boolean>;
  onRename?: (id: string, name: string) => Promise<boolean>;
  onRemove?: (id: string) => Promise<boolean>;
  onClose?: () => void;
}) {
  const [creando, setCreando] = useState(false);
  // Un proyecto a la vez en edición o pendiente de confirmar que se quita.
  const [editando, setEditando] = useState<{ id: string; name: string } | null>(null);
  const [quitando, setQuitando] = useState<string | null>(null);
  async function guardarNombre(event: FormEvent) {
    event.preventDefault();
    if (!editando || busy || !editando.name.trim() || !onRename) return;
    if (await onRename(editando.id, editando.name)) setEditando(null);
  }
  const Caja = fixed ? "aside" : "div";
  return <Caja className={fixed ? "vision-agent-side vision-projects" : "vision-tasks vision-projects"}
    role={fixed ? undefined : "dialog"} aria-labelledby="projects-title">
    {fixed && controls && <div className="vision-side-controls">{controls}</div>}
    {fixed && now}
    <header className="vision-panel-heading">
      <FolderOpen size={17} aria-hidden="true" />
      <h2 id="projects-title">Proyectos</h2>
      <span>{projects.length === 1 ? "1 proyecto" : projects.length ? `${projects.length} proyectos` : "ninguno todavía"}</span>
      <button type="button" className="vision-project-add" aria-label="Proyecto nuevo" title="Proyecto nuevo"
        aria-haspopup="dialog" disabled={busy} onClick={() => setCreando(true)}><Plus size={16} aria-hidden="true" /></button>
      {!fixed && <button type="button" className="icon-button" aria-label="Cerrar proyectos" onClick={onClose}><X size={16} /></button>}
    </header>
    {/* Fuera del panel: en el móvil el panel es de cristal, y un fondo desenfocado encierra dentro
        de sí a lo que se coloca fijo sobre la pantalla. */}
    {creando && createPortal(<NewProjectForm root={root} busy={busy} error={error} onCreate={onCreate}
      onClose={() => setCreando(false)} />, document.body)}
    {error && !creando && <p className="attachment-error" role="alert">{error}</p>}
    <ul className="vision-project-list">
      <li><button type="button" disabled={busy} aria-current={active === null ? "true" : undefined}
        onClick={() => onSelect(null)}>
        <strong>Sin proyecto</strong><span>La conversación general del Agente</span></button></li>
      {projects.map(project => <li key={project.id}>
        {editando?.id === project.id
          ? <form className="vision-project-edit" onSubmit={event => void guardarNombre(event)}>
              <input aria-label="Nombre del proyecto" value={editando.name} maxLength={80} disabled={busy}
                ref={campo => { if (campo && document.activeElement !== campo) campo.focus(); }}
                onChange={event => setEditando({ id: project.id, name: event.target.value })}
                onKeyDown={event => { if (event.key === "Escape") setEditando(null); }} />
              <button type="submit" className="icon-button" aria-label="Guardar nombre" disabled={busy || !editando.name.trim()}><Check size={15} /></button>
              <button type="button" className="icon-button" aria-label="Cancelar" onClick={() => setEditando(null)}><X size={15} /></button>
            </form>
          : quitando === project.id
          ? <div className="vision-project-confirm" role="alertdialog" aria-label={`Quitar ${project.name}`}>
              <p>¿Quitar «{project.name}» de la lista? Su carpeta y lo hablado no se borran.</p>
              <div>
                <button type="button" disabled={busy} onClick={() => setQuitando(null)}>No</button>
                <button type="button" disabled={busy} className="vision-project-danger"
                  onClick={() => { void onRemove?.(project.id).then(hecho => { if (hecho) setQuitando(null); }); }}>Quitar</button>
              </div>
            </div>
          : <div className="vision-project-row">
              <button type="button" disabled={busy} aria-current={active === project.id ? "true" : undefined}
                onClick={() => onSelect(project.id)}>
                <strong>{project.name}</strong><span title={project.folder}>{project.folder}</span></button>
              {onRename && <button type="button" className="icon-button" aria-label={`Renombrar ${project.name}`} title="Renombrar"
                disabled={busy} onClick={() => { setQuitando(null); setEditando({ id: project.id, name: project.name }); }}><Pencil size={14} /></button>}
              {onRemove && <button type="button" className="icon-button" aria-label={`Quitar ${project.name}`} title="Quitar de la lista"
                disabled={busy} onClick={() => { setEditando(null); setQuitando(project.id); }}><Trash2 size={14} /></button>}
            </div>}
      </li>)}
    </ul>
    {!fixed && <p className="vision-tasks-empty">Cada proyecto tiene su carpeta y su conversación. Al cambiar, Helios deja de tener delante la del otro; no se borra nada.</p>}
    {fixed && <div className="vision-agent-scroll">{activity}</div>}
    {fixed && <AgentMeter metrics={metrics} action={meterAction} />}
  </Caja>;
}
