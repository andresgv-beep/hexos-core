/** Lo que Helios escribe y luego no resulta ser su respuesta.
 *
 *  En un turno puede haber varias generaciones: Helios empieza a contestar («Para que sea
 *  moderna voy a aplicar…»), HexOS ve que no ha hecho nada y le devuelve el turno, o él mismo
 *  pasa a llamar a una herramienta. En pantalla ese primer texto se escribía, se borraba de
 *  golpe y empezaba el trabajo. Ahora no se borra: se queda como un paso más, en una línea,
 *  encima de lo que hace después. */

const MAX_STEP = 160;

/** ¿Ha empezado otra generación? El texto en vivo de una misma generación solo crece. */
export function isNewGeneration(previous: string, incoming: string): boolean {
  const before = previous.trim();
  if (before.length < 12) return false;
  return !incoming.trimStart().startsWith(before.slice(0, 12));
}

/** El texto descartado, en una línea que sirva de paso; "" si no hay nada que contar. */
export function stepFromDiscarded(text: string): string {
  const plain = text
    .replace(/```[\s\S]*?(```|$)/g, " ")          // el código no cabe en una línea de paso
    .replace(/<\|[^>]*\|?>|<[a-z_]+\|>/gi, " ")   // marcas del modelo
    .replace(/[*_`#>]+/g, "")
    .replace(/\s+/g, " ").trim();
  if (plain.length < 8) return "";
  const sentence = plain.match(/^.{8,}?[.!?:](?=\s|$)/)?.[0] ?? plain;
  const line = sentence.length > MAX_STEP ? `${sentence.slice(0, MAX_STEP - 1).trimEnd()}…` : sentence;
  return line.replace(/:$/, "…");
}

/** Añade un paso si no está ya: el mismo aviso puede llegar como texto en vivo y como anuncio. */
export function addStep(steps: string[] | undefined, line: string): string[] {
  const current = steps ?? [];
  const key = (value: string) => value.toLowerCase().replace(/[^a-záéíóúñ0-9]+/g, " ").trim().slice(0, 40);
  if (!line || current.some(step => key(step) === key(line))) return current;
  return [...current, line];
}

/** Los anuncios que hay que añadir al turno en pantalla; todos quedan anotados en `seen`.
 *
 *  Sin turno en curso también se anotan, aunque no se pinten: son de un turno que esta página
 *  no envió (otro dispositivo, o ella misma antes de recargar). Si se dejaban sin anotar, el
 *  siguiente mensaje se los encontraba todavía en el estado y los enseñaba como suyos. */
export function freshAnnouncements<T extends { id: string }>(messages: T[], seen: Set<string>, inProgress: boolean): T[] {
  const fresh = messages.filter(m => !seen.has(m.id));
  fresh.forEach(m => seen.add(m.id));
  return inProgress ? fresh : [];
}
