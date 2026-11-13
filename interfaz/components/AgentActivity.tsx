"use client";

import { useEffect, useState } from "react";
import type { Activity, ActivityDetail } from "@/lib/helios/hexos";

const hora = (ts: string) => {
  const fecha = new Date(ts);
  return Number.isNaN(fecha.getTime()) ? "" : fecha.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
};
const segundos = (value: number) => `${value.toLocaleString("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s`;

/** El tiempo que lleva la etapa actual. Se monta de nuevo en cada etapa (`key`), así que
 *  empieza de cero sin tener que ponerlo a mano. */
function Lleva() {
  const [desde] = useState(() => Date.now());
  const [ahora, setAhora] = useState(desde);
  useEffect(() => {
    const reloj = setInterval(() => setAhora(Date.now()), 1000);
    return () => clearInterval(reloj);
  }, []);
  const lleva = Math.max(0, Math.round((ahora - desde) / 1000));
  return lleva >= 1 ? <time>{lleva} s</time> : null;
}

/** Qué está haciendo Helios en este momento y cuánto lleva. El contador vuelve a cero cada
 *  vez que cambia lo que hace: así una espera larga se ve avanzar en vez de parecer colgada. */
export function AgentNow({ label, stage, busy }: { label: string; stage: string; busy: boolean }) {
  return <section className="vision-agent-now" aria-label="Ahora mismo" data-busy={busy || undefined}>
    <span aria-hidden="true" />
    <p role="status">{label}</p>
    {busy && <Lleva key={stage} />}
  </section>;
}

/** Lo hecho en la conversación puesta: las órdenes lanzadas y lo que cambió. Una llamada
 *  se abre para ver sus argumentos y su salida; la salida no viaja hasta que se pide. */
export function AgentActivity({ activity, loadDetail }: {
  activity: Activity | null;
  loadDetail?: (seq: number) => Promise<ActivityDetail>;
}) {
  const [abierta, setAbierta] = useState<number | null>(null);
  const [detalle, setDetalle] = useState<ActivityDetail | null>(null);
  const [error, setError] = useState("");
  async function abrir(seq: number) {
    if (abierta === seq) { setAbierta(null); return; }
    setAbierta(seq); setDetalle(null); setError("");
    if (!loadDetail) return;
    try { setDetalle(await loadDetail(seq)); }
    catch (fallo) { setError(fallo instanceof Error ? fallo.message : "No se pudo leer la llamada."); }
  }
  if (!activity) return null;
  return <>
    <section className="vision-agent-log" aria-label="Herramientas ejecutadas">
      <h3>Herramientas <span>{activity.tools.length || ""}</span></h3>
      {!activity.tools.length && <p className="vision-agent-empty">Aún no se ha ejecutado ninguna aquí.</p>}
      <ul>{activity.tools.map(call => {
        const punto = call.tool.indexOf(".");
        return <li key={call.seq} data-failed={call.failed || undefined}>
          <button type="button" aria-expanded={abierta === call.seq} onClick={() => void abrir(call.seq)}>
            <span className="vision-agent-tool">{punto > 0 && <i>{call.tool.slice(0, punto + 1)}</i>}{call.tool.slice(punto + 1)}</span>
            <span className="vision-agent-when">{call.failed ? "error" : call.seconds !== null ? segundos(call.seconds) : ""}</span>
            {call.summary && <code>{call.summary}</code>}
          </button>
          {abierta === call.seq && <div className="vision-agent-detail">
            {error && <p role="alert">{error}</p>}
            {!error && !detalle && <p>Leyendo…</p>}
            {detalle && <>
              <pre>{detalle.output || "(sin salida)"}</pre>
              {detalle.truncated && <p>La salida sigue; aquí va el principio.</p>}
            </>}
          </div>}
        </li>;
      })}</ul>
    </section>
    {!!activity.changes.length && <section className="vision-agent-log" aria-label="Cambios">
      <h3>Cambios <span>{activity.changes.length}</span></h3>
      <ul>{activity.changes.map((change, index) => <li key={`${change.ts}-${index}`} className="vision-agent-change" data-kind={change.kind}>
        <time>{hora(change.ts)}</time><p>{change.text}</p>
      </li>)}</ul>
    </section>}
  </>;
}
