"use client";

import { useCallback, useEffect, useState } from "react";
import { Star } from "lucide-react";
import { createCoreClient, type CoreClient, type NoteDetail } from "@/lib/helios/core";

const defaultClient = createCoreClient("/api/helios");

/** La tira de favoritos bajo la esfera: lo que Helios tiene anclado y a mano.
 *  El archivo completo ya no vive aquí — se abre desde el panel lateral. */
export function CoreShelf({ client = defaultClient, reload, onOpenNote, onTotal }:
  { client?: CoreClient; reload: number; onOpenNote: (note: NoteDetail) => void;
    onTotal?: (total: number | null) => void }) {
  const [favoritos, setFavoritos] = useState<{ id: string; title: string }[]>([]);
  const [error, setError] = useState("");

  const refresh = useCallback((signal?: AbortSignal) => {
    client.overview(signal).then(data => {
      setFavoritos(data.favorites.map(f => ({ id: f.id, title: f.title })));
      setError("");
      // Un total que no se pudo contar se dice, no se pinta como cero.
      const known = data.sections.every(s => s.total !== null);
      onTotal?.(known ? data.sections.reduce((total, s) => total + (s.total ?? 0), 0) : null);
    }).catch(e => {
      if (signal?.aborted) return;
      setError(e instanceof Error ? e.message : "No se pudo leer el núcleo.");
      onTotal?.(null);
    });
  }, [client, onTotal]);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh, reload]);

  async function abrirNota(id: string) {
    // Sin esto un fallo se ve como «pulso y no pasa nada», que es peor que el error.
    try { onOpenNote(await client.note(id)); setError(""); }
    catch (e) { setError(e instanceof Error ? e.message : "No se pudo abrir la nota."); }
  }

  return <div className="core-shelf" aria-label="Favoritos del núcleo">
    {favoritos.map(item => <button key={item.id} type="button" className="core-favorite"
      onClick={() => void abrirNota(item.id)}>
      <Star size={14} aria-hidden="true" />
      <span className="core-favorite-title">{item.title}</span>
    </button>)}
    {!favoritos.length && !error && <span className="core-empty">
      Sin favoritos. Pídele a Helios que ancle una nota.
    </span>}
    {error && <span className="core-empty" role="alert">{error}</span>}
  </div>;
}
