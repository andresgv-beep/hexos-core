"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Globe, Palette, Settings as SettingsIcon, X } from "lucide-react";
import type { HeliosTransport, ServiceProvider, Settings } from "@/lib/helios/hexos";
import { CLAVE_TEMA, MANDOS, TEMA_ATAJOS, TEMA_BASE, TEMA_MANDOS, aplicarTema, guardarTema, leerTema, mismoTema,
         type Tema } from "@/lib/helios/tema";

/** Las secciones de la ventana. Una nueva (chat…) es otra entrada aquí y su panel abajo. */
const SECCIONES = [{ id: "web", nombre: "Web", Icono: Globe },
                   { id: "apariencia", nombre: "Apariencia", Icono: Palette }] as const;
type Seccion = typeof SECCIONES[number]["id"];

const error = (reason: unknown) => reason instanceof Error ? reason.message : "No se pudo completar";

/** Un servicio con clave. La clave solo viaja de aquí a HexOS: nunca vuelve, así que el
 *  campo empieza siempre vacío y lo guardado se reconoce por sus cuatro últimos caracteres. */
function ProviderCard({ provider, transport, onChange }: {
  provider: ServiceProvider; transport: HeliosTransport; onChange: (settings: Settings) => void;
}) {
  const [clave, setClave] = useState("");
  const [busy, setBusy] = useState<"guardar" | "probar" | "quitar" | null>(null);
  const [aviso, setAviso] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  async function probar(prefijo = "") {
    setBusy("probar");
    try {
      const n = await transport.testService!(provider.id);
      setAviso({ kind: "ok", text: `${prefijo}Funciona: la búsqueda de prueba trajo ${n} ${n === 1 ? "resultado" : "resultados"}.` });
    } catch (reason) {
      setAviso({ kind: "error", text: `${prefijo}La prueba falló: ${error(reason)}` });
    } finally { setBusy(null); }
  }
  async function guardar(event: FormEvent) {
    event.preventDefault();
    if (!clave.trim() || busy) return;
    setBusy("guardar"); setAviso(null);
    try {
      onChange(await transport.saveServiceKey!(provider.id, clave.trim()));
      setClave("");
    } catch (reason) { setAviso({ kind: "error", text: error(reason) }); setBusy(null); return; }
    await probar("Clave guardada. ");
  }
  async function quitar() {
    setBusy("quitar"); setAviso(null);
    try {
      onChange(await transport.saveServiceKey!(provider.id, null));
      setAviso({ kind: "ok", text: "Clave quitada." });
    } catch (reason) { setAviso({ kind: "error", text: error(reason) }); }
    finally { setBusy(null); }
  }

  return <section className="settings-provider" aria-label={provider.name}>
    <header>
      <strong>{provider.name}</strong>
      <span className="settings-pill" data-on={provider.configured}>
        {provider.configured ? `Con clave ${provider.hint ?? ""}` : "Sin clave"}</span>
    </header>
    <p className="settings-lead">{provider.note}{" "}
      {provider.site && <a href={provider.site} target="_blank" rel="noreferrer">Conseguir una clave</a>}</p>
    <form className="settings-row" onSubmit={guardar}>
      <label className="access-field">{provider.configured ? "Cambiar la clave" : "Clave de la API"}
        {/* De texto y enmascarado por CSS, no `password`: a un campo de contraseña el navegador
            le ofrece o le mete las contraseñas guardadas del sitio, que no son la clave. */}
        <input className="settings-secret" type="text" name={`clave-${provider.id}`} autoComplete="off"
          autoCapitalize="none" autoCorrect="off" spellCheck={false} data-1p-ignore data-lpignore="true"
          value={clave} placeholder={provider.placeholder}
          disabled={busy !== null} onChange={event => setClave(event.target.value)} />
      </label>
      <div className="access-actions">
        {provider.configured && <button type="button" disabled={busy !== null} onClick={() => void quitar()}>
          {busy === "quitar" ? "Quitando…" : "Quitar"}</button>}
        {provider.configured && <button type="button" disabled={busy !== null} onClick={() => void probar()}>
          {busy === "probar" ? "Probando…" : "Probar"}</button>}
        <button type="submit" className="access-save" disabled={busy !== null || !clave.trim()}>
          {busy === "guardar" ? "Guardando…" : "Guardar"}</button>
      </div>
    </form>
    {aviso && <p className="settings-status" data-kind={aviso.kind} role={aviso.kind === "error" ? "alert" : "status"}>{aviso.text}</p>}
  </section>;
}

const almacen = (): Storage | null => { try { return window.localStorage; } catch { return null; } };

/** El aspecto de la interfaz. No pasa por HexOS: se aplica al documento y se guarda en este
 *  navegador, así que cada dispositivo lleva el suyo y cambia sin esperar a nadie. */
function Apariencia() {
  // Solo se monta al abrir Ajustes, ya en el navegador: se puede leer lo guardado al empezar.
  const [tema, setTema] = useState<Tema>(() => leerTema(almacen()?.getItem(CLAVE_TEMA)));
  // El último tema puesto, no el del último repintado: dos pulsaciones seguidas se suman
  // en vez de partir las dos del mismo estado y que la segunda deshaga la primera.
  const puesto = useRef(tema);
  function poner(cambio: Partial<Tema>) {
    const nuevo = puesto.current = { ...puesto.current, ...cambio };
    setTema(nuevo);
    aplicarTema(document.documentElement, nuevo);
    guardarTema(nuevo, almacen());
  }
  return <>
    <h3>Apariencia</h3>
    <p className="settings-lead">Cambia al momento y se guarda en este dispositivo: el móvil y el PC pueden ir distintos.</p>
    <div className="theme-group" role="group" aria-label="Atajos">
      <span>Atajos</span>
      <div>{TEMA_ATAJOS.map(atajo => <button key={atajo.nombre} type="button" aria-pressed={mismoTema(tema, atajo.tema)}
        onClick={() => poner(atajo.tema)}>{atajo.nombre}</button>)}</div>
    </div>
    {MANDOS.map(mando => <div key={mando} className="theme-group" role="group" aria-label={TEMA_MANDOS[mando].nombre}>
      <span>{TEMA_MANDOS[mando].nombre}</span>
      <div>{TEMA_MANDOS[mando].opciones.map(opcion => <button key={opcion.id} type="button"
        aria-pressed={tema[mando] === opcion.id} onClick={() => poner({ [mando]: opcion.id })}>
        {"muestra" in opcion && <i style={{ background: opcion.muestra }} aria-hidden="true" />}{opcion.nombre}
      </button>)}</div>
    </div>)}
    {!mismoTema(tema, TEMA_BASE) && <p className="access-note">«Clásico» devuelve el aspecto de siempre.</p>}
  </>;
}

/** Ajustes de Helios: «Web», los servicios externos y sus claves, y «Apariencia», el tema. */
export function SettingsWindow({ transport, onClose }: { transport: HeliosTransport; onClose: () => void }) {
  const [seccion, setSeccion] = useState<Seccion>("web");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [fallo, setFallo] = useState("");
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const control = new AbortController();
    transport.settings!(control.signal).then(setSettings)
      .catch(reason => { if (!control.signal.aborted) setFallo(error(reason)); });
    return () => control.abort();
  }, [transport]);
  // El padre se repinta con cada sondeo de estado: el foco se pone una sola vez, o se
  // lo quitaría al campo de la clave mientras se escribe.
  const cerrar = useRef(onClose);
  useEffect(() => { cerrar.current = onClose; }, [onClose]);
  useEffect(() => {
    panel.current?.focus();
    const tecla = (event: KeyboardEvent) => { if (event.key === "Escape") cerrar.current(); };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, []);

  const buscadores = settings?.web.providers.filter(p => p.kind === "busqueda") ?? [];
  return <div className="access-backdrop">
    <div ref={panel} className="access-panel settings-panel" role="dialog" aria-modal="true" aria-labelledby="settings-title"
      tabIndex={-1}>
      <header className="settings-head">
        <SettingsIcon size={17} aria-hidden="true" />
        <h2 id="settings-title">Ajustes</h2>
        <button type="button" className="icon-button" aria-label="Cerrar ajustes" onClick={onClose}><X size={16} /></button>
      </header>
      <div className="settings-body">
        <nav className="settings-nav" aria-label="Secciones de ajustes">
          {SECCIONES.map(({ id, nombre, Icono }) => <button key={id} type="button"
            aria-current={seccion === id ? "page" : undefined} onClick={() => setSeccion(id)}>
            <Icono size={16} aria-hidden="true" /> {nombre}</button>)}
        </nav>
        <div className="settings-content">
          {seccion === "apariencia" && <Apariencia />}
          {seccion === "web" && fallo && <p className="settings-status" data-kind="error" role="alert">{fallo}</p>}
          {seccion === "web" && !settings && !fallo && <p className="settings-lead">Cargando…</p>}
          {settings && seccion === "web" && <>
            <h3>Búsqueda en la web</h3>
            <p className="settings-lead">Helios busca ahora con <strong>{settings.web.search}</strong>.{" "}
              {buscadores.some(p => p.configured)
                ? "Las consultas salen hacia ese servicio con tu clave."
                : "Sin clave lee la página de resultados de DuckDuckGo, que a veces bloquea las búsquedas automáticas. Con la clave de un servicio de búsqueda eso no pasa."}</p>
            {buscadores.map(provider => <ProviderCard key={provider.id} provider={provider}
              transport={transport} onChange={setSettings} />)}
            <p className="access-note">Las claves se guardan en este PC, en un fichero aparte de la conversación.
              Helios no las ve y esta pantalla no vuelve a enseñarlas.</p>
          </>}
        </div>
      </div>
    </div>
  </div>;
}
