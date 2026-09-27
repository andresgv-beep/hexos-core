"use client";

import { ListChecks, X } from "lucide-react";
import { isActive, type MediaControl, type MediaJob } from "@/lib/helios/media";
import { MediaCard } from "./MediaCard";

/** Las tareas en segundo plano, en su propio sitio del raíl. Hoy son las de la
 *  cola de vídeo; otra clase de tarea entra aquí como otra sección, con su tarjeta. */
export function TasksPanel({ media, onControl, onClose }: {
  media: MediaJob[];
  onControl: (batchId: string, operation: MediaControl) => Promise<void>;
  onClose: () => void;
}) {
  const active = media.filter(isActive);
  const recent = media.filter(job => !isActive(job));
  return <div className="vision-tasks" role="dialog" aria-labelledby="tasks-title">
    <header className="vision-panel-heading">
      <ListChecks size={17} aria-hidden="true" />
      <h2 id="tasks-title">Tareas</h2>
      <span>{active.length ? `${active.length} en curso` : "en calma"}</span>
      <button type="button" className="icon-button" aria-label="Cerrar tareas" onClick={onClose}><X size={16} /></button>
    </header>
    {!media.length && <p className="vision-tasks-empty">No hay tareas en segundo plano. Cuando pidas a Helios algo que tarde, como comprimir una película, aparecerá aquí.</p>}
    {!!active.length && <section aria-label="En curso"><h3>En curso</h3><MediaCard jobs={active} onControl={onControl} /></section>}
    {!!recent.length && <section aria-label="Recientes"><h3>Recientes</h3><MediaCard jobs={recent} onControl={onControl} /></section>}
  </div>;
}
