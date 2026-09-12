export type HeliosPhase = "idle" | "listening" | "thinking" | "tool" | "responding" | "error";

export type OrbSignal = { phase: HeliosPhase; energy: number };

export const phases: Record<HeliosPhase, { label: string; title: string; detail: string; color: string; warmth: number; energy: number; speed: number }> = {
  idle: { label: "En calma", title: "Todo empieza contigo.", detail: "Un pensamiento, una pregunta, una nueva idea.", color: "#66c7ff", warmth: 0, energy: .16, speed: .14 },
  listening: { label: "Escuchando", title: "Soy todo oídos.", detail: "La luz se abre para recibirte.", color: "#70eed9", warmth: .08, energy: .4, speed: .23 },
  thinking: { label: "Pensando", title: "Conectando ideas.", detail: "Cada conexión abre una posibilidad.", color: "#c3a0ff", warmth: .38, energy: .63, speed: .36 },
  tool: { label: "Consultando", title: "Buscando el camino.", detail: "La actividad recorre las conexiones.", color: "#edb67e", warmth: .72, energy: .58, speed: .28 },
  responding: { label: "Respondiendo", title: "Una idea toma forma.", detail: "La esfera se expande al ritmo de cada frase.", color: "#ffb47a", warmth: 1, energy: .8, speed: .22 },
  error: { label: "En pausa", title: "Un momento de pausa.", detail: "Podemos volver a intentarlo cuando quieras.", color: "#e3a1ad", warmth: .55, energy: .12, speed: .06 },
};

// Transport state is deliberately independent from presentation and GPU state.
export function phaseFromHexos(state: unknown): HeliosPhase {
  if (state === "idle" || state === "thinking" || state === "tool") return state;
  throw new Error(`Estado de HexOS no reconocido: ${String(state)}`);
}

export function clampEnergy(value: number): number {
  return Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
}
