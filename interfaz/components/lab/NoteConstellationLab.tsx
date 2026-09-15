"use client";

import { useEffect, useRef } from "react";
import { HeliosOrb } from "@/components/orb/HeliosOrb";
import { NoteConstellation, type ConstellationTuning, type LabNote } from "./NoteConstellation";

const NOTES: LabNote[] = [
  { id: "a", title: "Actualización de estado de srv1" },
  { id: "b", title: "Cableado del disco sda" },
  { id: "c", title: "Contenedores que nunca arrancaron" },
  { id: "d", title: "Plan de copias semanales" },
];

const DEFAULTS: ConstellationTuning = {
  orbitRadius: 2.2, orbitSpeed: .01, sizePx: 26,
  hue: 207, graceMs: 30, bubblePx: 108, life: .46, tilt: 1,
};

const CONTROLS: { key: keyof ConstellationTuning; label: string; min: number; max: number; step: number }[] = [
  { key: "orbitRadius", label: "Radio de órbita", min: 1.9, max: 3.6, step: .01 },
  { key: "orbitSpeed", label: "Velocidad de órbita", min: 0, max: 1, step: .01 },
  { key: "sizePx", label: "Tamaño del punto (px)", min: 10, max: 60, step: 1 },
  { key: "hue", label: "Tono (0 rojo · 45 oro · 200 azul)", min: 0, max: 260, step: 1 },
  { key: "graceMs", label: "Respiro al salir (ms)", min: 0, max: 1200, step: 10 },
  { key: "bubblePx", label: "Tamaño de la burbuja (px)", min: 30, max: 110, step: 1 },
  { key: "life", label: "Vida (balanceo y palpitar)", min: 0, max: 2, step: .01 },
  { key: "tilt", label: "Achatado (1 círculo · 0.3 anillo)", min: .2, max: 1, step: .01 },
];

export function NoteConstellationLab() {
  const stage = useRef<HTMLDivElement>(null);
  const pointer = useRef({ distance: 99, x: -1e4, y: -1e4 });
  const tuning = useRef<ConstellationTuning>({ ...DEFAULTS });
  const markers = useRef<(HTMLDivElement | null)[]>([]);

  // Distance is measured from the orb's centre in units of its on-screen radius,
  // so "inside the constellation" means the whole ring, not the sphere's edge.
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
    const leave = () => { pointer.current = { ...pointer.current, distance: 99 }; };
    window.addEventListener("pointermove", move, { passive: true });
    el.addEventListener("pointerleave", leave);
    return () => { window.removeEventListener("pointermove", move); el.removeEventListener("pointerleave", leave); };
  }, []);

  return <main className="lab">
    <header className="lab-bar">
      <strong>Laboratorio · notas como estrellas</strong>
      <span>Pasa el ratón sobre el núcleo. Al acercarte la órbita frena; al salir del todo vuelven a ser estrellas.</span>
    </header>

    <div ref={stage} className="lab-stage">
      <HeliosOrb signal={{ phase: "idle", energy: .16 }} motion >
        <NoteConstellation notes={NOTES} pointer={pointer} tuning={tuning} markers={markers} />
      </HeliosOrb>
      {NOTES.map((note, i) => <div key={note.id} className="lab-marker" ref={el => { markers.current[i] = el; }}>
        <div className="lab-bubble" aria-hidden="true" />
        <div className="lab-title">{note.title}</div>
      </div>)}
      <div className="lab-fresh" title="La nota recién pedida, todavía en la mano" />
    </div>

    <aside className="lab-controls">
      {CONTROLS.map(control => <label key={control.key}>
        <span>{control.label}<output id={`out-${control.key}`}>{DEFAULTS[control.key]}</output></span>
        <input type="range" min={control.min} max={control.max} step={control.step}
          defaultValue={DEFAULTS[control.key]}
          onChange={event => {
            const value = Number(event.target.value);
            tuning.current = { ...tuning.current, [control.key]: value };
            const out = document.getElementById(`out-${control.key}`);
            if (out) out.textContent = String(value);
          }} />
      </label>)}
      <button type="button" onClick={() => {
        tuning.current = { ...DEFAULTS };
        for (const control of CONTROLS) {
          const input = document.querySelector<HTMLInputElement>(`input[name="${control.key}"]`);
          if (input) input.value = String(DEFAULTS[control.key]);
          const out = document.getElementById(`out-${control.key}`);
          if (out) out.textContent = String(DEFAULTS[control.key]);
        }
      }}>Valores por defecto</button>
    </aside>
  </main>;
}
