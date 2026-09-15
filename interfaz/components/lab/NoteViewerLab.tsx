"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { HeliosOrb } from "@/components/orb/HeliosOrb";
import { SystemMonitor } from "@/components/SystemMonitor";
import { NoteViewer, type ViewerNote } from "./NoteViewer";
import { NoteConstellation, type ConstellationTuning } from "./NoteConstellation";

const TITULOS = [
  "Actualización de estado de srv1", "Cableado del disco sda", "Contenedores que nunca arrancaron",
  "Plan de copias semanales", "Temperaturas del NAS en agosto", "Rotación de claves SSH",
  "Inventario de discos", "Migración de Portainer", "Notas de la caída del martes",
  "Consumo eléctrico del rack", "Ajustes de HandBrake", "Pendientes de red",
  "Certificados que caducan", "Repaso de backups Synology", "Errores CRC del ata1",
  "Me pica el ano", "Tareas del fin de semana", "Reinicio programado",
  "Logs del kernel filtrados", "Pools md2 md3 md6", "Cambios en el router",
  "Lista de la compra", "Ideas para Helios", "Presupuesto de discos",
];
const CUANDO = ["Hoy, 21:18", "Hoy, 15:25", "Ayer, 20:40", "Anteayer", "Hace 3 días", "La semana pasada", "El mes pasado"];

const AJUSTE: ConstellationTuning = {
  orbitRadius: 2.2, orbitSpeed: .01, sizePx: 26,
  hue: 207, graceMs: 30, bubblePx: 108, life: .46, tilt: 1,
};

export function NoteViewerLab() {
  const [open, setOpen] = useState(true);
  const [marked, setMarked] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [width, setWidth] = useState(490);
  const [turn, setTurn] = useState(1);
  const [reading, setReading] = useState<ViewerNote | null>(null);
  const [notes, setNotes] = useState<ViewerNote[]>(() => TITULOS.map((title, i) => ({
    id: `n${i}`, title, updatedAt: CUANDO[i % CUANDO.length], favorite: i < 4,
  })));
  // Mentioned in this turn: an untouched viewer closes when the turn advances.
  const mentioned = useRef(true);
  const orbHovered = useRef(false);
  /** The note Helios just handed you: it waits below the orb until you open it. */
  const [inHand, setInHand] = useState<ViewerNote | null>(null);
  const stage = useRef<HTMLDivElement>(null);
  const pointer = useRef({ distance: 99, x: -1e4, y: -1e4 });
  const tuning = useRef<ConstellationTuning>(AJUSTE);
  const markers = useRef<(HTMLDivElement | null)[]>([]);

  // Favourites are the ring. Starring one in the viewer sends it up to the orb.
  const favoritas = useMemo(() => notes.filter(n => n.favorite).slice(0, 12), [notes]);

  useEffect(() => {
    const el = stage.current;
    if (!el) return;
    const move = (event: PointerEvent) => {
      const box = el.getBoundingClientRect();
      const cx = box.left + box.width / 2, cy = box.top + box.height / 2;
      const radius = Math.min(box.width, box.height) * .32;
      pointer.current = {
        distance: Math.hypot(event.clientX - cx, event.clientY - cy) / radius,
        x: event.clientX - box.left, y: event.clientY - box.top,
      };
    };
    window.addEventListener("pointermove", move, { passive: true });
    return () => window.removeEventListener("pointermove", move);
  }, []);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? notes.filter(n => n.title.toLowerCase().includes(q)) : notes;
  }, [notes, query]);

  function buscar(andShow: boolean) {
    const found = notes.find(n => n.title.toLowerCase().includes("pica")) ?? notes[15];
    setOpen(true); setQuery(""); mentioned.current = true;
    setMarked(null);
    setTimeout(() => setMarked(found.id), 40);
    setInHand(found);
    if (andShow) setReading(found);
  }

  function siguienteTurno() {
    setTurn(t => t + 1);
    if (!mentioned.current) { setOpen(false); setMarked(null); }
    mentioned.current = false;
  }

  return <main className="helios-app phase-idle lab-visor">
    <section className="presence" aria-label="Presencia de Helios">
      <div ref={stage} className="orb-stage">
        <HeliosOrb signal={{ phase: "idle", energy: .16 }} motion hovered={orbHovered}>
          <NoteConstellation notes={favoritas} pointer={pointer} tuning={tuning} markers={markers} />
        </HeliosOrb>
        {favoritas.map((note, i) => <div key={note.id} className="lab-marker" ref={el => { markers.current[i] = el; }}>
          <div className="lab-bubble" aria-hidden="true" />
          <div className="lab-title">{note.title}</div>
        </div>)}
        {inHand && <button type="button" className="hand-note"
          onClick={() => { mentioned.current = true; setReading(inHand); }}
          title={`Abrir: ${inHand.title}`} aria-label={`Abrir la nota que Helios te ha dado: ${inHand.title}`}>
          <span className="hand-bubble" aria-hidden="true" />
          <span className="hand-label">{inHand.title}</span>
        </button>}
      </div>
    </section>

    <SystemMonitor autoEnabled autoBusy={false} onToggleAuto={() => {}} />

    {open && <NoteViewer notes={shown} marked={marked} query={query} width={width}
      onQuery={value => { setQuery(value); mentioned.current = true; }}
      onToggleFavorite={id => { mentioned.current = true; setNotes(list => list.map(n => n.id === id ? { ...n, favorite: !n.favorite } : n)); }}
      onClose={() => { setOpen(false); setMarked(null); }}
      onOpen={id => { mentioned.current = true; setReading(notes.find(n => n.id === id) ?? null); }} />}

    {reading && <div className="lab-reading">
      <div className="window-glass">
        <header className="window-heading">
          <span className="window-dot" /><span>{reading.title}</span>
          <button className="icon-button" onClick={() => setReading(null)} aria-label="Cerrar la nota">✕</button>
        </header>
        <div className="window-content"><p>Contenido de la nota, que en la app real llega del núcleo.</p></div>
      </div>
    </div>}

    <div className="lab-console">
      <strong>Turno {turn}</strong>
      <button type="button" onClick={() => buscar(false)}>«búscame la nota…»</button>
      <button type="button" onClick={() => buscar(true)}>«búscala y muéstrala»</button>
      <button type="button" onClick={siguienteTurno}>Siguiente turno</button>
      <button type="button" onClick={() => { setOpen(true); mentioned.current = true; }}>Abrir visor</button>
      <button type="button" onClick={() => setInHand(null)}>Soltar la de la mano</button>
      <label>Ancho <output>{width}</output>
        <input type="range" min={300} max={620} step={5} value={width}
          onChange={e => setWidth(Number(e.target.value))} aria-label="Ancho del visor" /></label>
    </div>
  </main>;
}
