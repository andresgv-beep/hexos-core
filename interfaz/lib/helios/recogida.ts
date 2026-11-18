import type { HeliosTransport, HistoryMessage } from "./hexos";

/** El navegador perdió la petición mientras Helios contestaba: el móvil se bloqueó, cambió de red
 *  o Tailscale cortó. El turno sigue en el PC y su respuesta se guarda igual. El 18/11 un Excel bien
 *  hecho se quedó en el chat como «Load failed» (el texto de Safari para esto). */
export function esCorteDeRed(error: unknown): boolean {
  return error instanceof TypeError
    && /load failed|failed to fetch|networkerror|network connection was lost|conexi[oó]n/i.test(error.message);
}

const pausa = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));

/** Espera a que Helios acabe en el PC y trae su respuesta del historial, si es la de esta pregunta.
 *  null si no se pudo: sin red todo el rato, o la última respuesta guardada es de otra cosa. */
export async function recogerRespuesta(transport: HeliosTransport, pregunta: string,
  { esperar = pausa, intentos = 300, cada = 2000 }: { esperar?: (ms: number) => Promise<void>; intentos?: number; cada?: number } = {},
): Promise<HistoryMessage | null> {
  for (let i = 0; i < intentos; i++) {
    try {
      const estado = await transport.status();
      if (estado.phase === "idle" || estado.phase === "error") break;
    } catch { /* todavía sin red: se vuelve a probar */ }
    await esperar(cada);
  }
  if (!transport.historyPage) return null;
  try {
    const { messages } = await transport.historyPage();
    const respuesta = messages.at(-1), suya = messages.at(-2);
    const inicio = pregunta.trim().slice(0, 60);
    if (respuesta?.role === "assistant" && suya?.role === "user" && inicio && suya.text.trim().startsWith(inicio)) return respuesta;
  } catch { /* sin historial no se inventa nada */ }
  return null;
}
