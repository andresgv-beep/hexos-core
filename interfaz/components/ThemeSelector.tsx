"use client";
import { useEffect, useState, type CSSProperties } from "react";

const themes = [
  { id: "hud", label: "HUD azul y rosa", accent: "#4a9cf0", secondary: "#e85ccb" },
  { id: "slate", label: "Pizarra", accent: "#555b63", secondary: "#d2d7de" },
  { id: "amber", label: "Ámbar", accent: "#e5a46a", secondary: "#4fd1e6" },
  { id: "purple", label: "Púrpura", accent: "#a87cff", secondary: "#3fe0e6" },
];
const key = "helios.hud.theme";
function valid(value: string | null) { if (value === "phosphor") return "slate"; return themes.some(theme => theme.id === value) ? value! : "hud"; }
export function ThemeSelector() {
  const [selected, setSelected] = useState("hud");
  useEffect(() => {
    const apply = (value: string | null) => {
      const id = valid(value);
      document.documentElement.setAttribute("data-theme", id);
      setSelected(id);
    };
    try { const saved = localStorage.getItem(key); apply(saved); if (saved === "phosphor") localStorage.setItem(key, "slate"); } catch { apply("hud"); }
    const sync = (event: StorageEvent) => { if (event.key === key || event.key === null) apply(event.newValue); };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);
  function choose(id: string) {
    setSelected(id);
    document.documentElement.setAttribute("data-theme", id);
    try { localStorage.setItem(key, id); } catch { /* Preferencia opcional; el tema sigue funcionando. */ }
  }
  return <div className="hud-theme-picker" role="group" aria-label="Tema de la interfaz">
    <span>TEMA</span>{themes.map(theme => <button key={theme.id} type="button"
      title={theme.label} aria-label={theme.label} aria-pressed={selected === theme.id}
      style={{ "--swatch-a": theme.accent, "--swatch-b": theme.secondary } as CSSProperties}
      onClick={() => choose(theme.id)} />)}
  </div>;
}
