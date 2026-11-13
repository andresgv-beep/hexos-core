"use client";

import { useState, type FormEvent } from "react";
import { FolderOpen, Plus, X } from "lucide-react";
import type { Project } from "@/lib/helios/hexos";

/** Los proyectos del Agente. Cada uno tiene su carpeta y su conversación: cambiar de
 *  proyecto es dejar una y seguir en otra, sin que Helios mezcle lo de las dos. */
export function ProjectsPanel({ projects, active, busy, error, onSelect, onCreate, onClose }: {
  projects: Project[];
  active: string | null;
  busy: boolean;
  error: string;
  onSelect: (id: string | null) => void;
  onCreate: (name: string, folder: string) => Promise<boolean>;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [folder, setFolder] = useState("");
  const [conCarpeta, setConCarpeta] = useState(false);
  async function crear(event: FormEvent) {
    event.preventDefault();
    if (busy || !name.trim()) return;
    if (await onCreate(name, conCarpeta ? folder : "")) { setName(""); setFolder(""); setConCarpeta(false); }
  }
  return <div className="vision-tasks vision-projects" role="dialog" aria-labelledby="projects-title">
    <header className="vision-panel-heading">
      <FolderOpen size={17} aria-hidden="true" />
      <h2 id="projects-title">Proyectos</h2>
      <span>{projects.length ? `${projects.length} en este equipo` : "ninguno todavía"}</span>
      <button type="button" className="icon-button" aria-label="Cerrar proyectos" onClick={onClose}><X size={16} /></button>
    </header>
    <p className="vision-tasks-empty">Cada proyecto tiene su carpeta y su conversación. Al cambiar, Helios deja de tener delante la del otro; no se borra nada.</p>
    <ul className="vision-project-list">
      <li><button type="button" disabled={busy} aria-current={active === null ? "true" : undefined}
        onClick={() => onSelect(null)}>
        <strong>Sin proyecto</strong><span>La conversación general del Agente</span></button></li>
      {projects.map(project => <li key={project.id}>
        <button type="button" disabled={busy} aria-current={active === project.id ? "true" : undefined}
          onClick={() => onSelect(project.id)}>
          <strong>{project.name}</strong><span title={project.folder}>{project.folder}</span></button></li>)}
    </ul>
    <form className="vision-project-new" onSubmit={event => void crear(event)}>
      <label htmlFor="project-name">Proyecto nuevo</label>
      <div>
        <input id="project-name" value={name} maxLength={80} placeholder="Nombre" autoComplete="off"
          disabled={busy} onChange={event => setName(event.target.value)} />
        <button type="submit" className="icon-button" aria-label="Crear proyecto" disabled={busy || !name.trim()}><Plus size={16} /></button>
      </div>
      <label className="vision-project-check"><input type="checkbox" checked={conCarpeta} disabled={busy}
        onChange={event => setConCarpeta(event.target.checked)} /> Usar una carpeta que ya existe</label>
      {conCarpeta && <input aria-label="Ruta de la carpeta" value={folder} placeholder="~/Documentos/GitHub/mi-repo"
        autoComplete="off" spellCheck={false} disabled={busy} onChange={event => setFolder(event.target.value)} />}
      {!conCarpeta && <p className="vision-project-hint">Se creará una carpeta nueva con ese nombre.</p>}
      {error && <p className="attachment-error" role="alert">{error}</p>}
    </form>
  </div>;
}
