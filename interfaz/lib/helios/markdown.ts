/** Lo que Helios escribe viene en Markdown —viñetas, negrita, `código`— y la
 *  interfaz lo soltaba en un párrafo plano: un listado de vecinos salía todo
 *  seguido y sin jerarquía. Esto lo convierte en bloques para pintarlo.
 *
 *  Deliberadamente pequeño: solo lo que este modelo usa de verdad. Nada de HTML
 *  incrustado, que además sería texto ajeno metido en la página. */
export interface Inline { text: string; bold?: boolean; code?: boolean }
export interface Block {
  kind: "p" | "ul" | "ol" | "code";
  lines: Inline[][];
  language?: string;
}

const VINETA = /^\s*[*-]\s+(.*)$/;
const NUMERO = /^\s*\d+[.)]\s+(.*)$/;
const CERCA = /^\s*```([^\s`]*)\s*$/;

/** Negrita y código dentro de una línea. Un asterisco suelto es un asterisco. */
export function inlines(text: string): Inline[] {
  const salida: Inline[] = [];
  const patron = /\*\*(.+?)\*\*|`([^`]+)`/g;
  let ultimo = 0;
  for (let m = patron.exec(text); m; m = patron.exec(text)) {
    if (m.index > ultimo) salida.push({ text: text.slice(ultimo, m.index) });
    if (m[1] !== undefined) salida.push({ text: m[1], bold: true });
    else salida.push({ text: m[2], code: true });
    ultimo = m.index + m[0].length;
  }
  if (ultimo < text.length) salida.push({ text: text.slice(ultimo) });
  return salida.length ? salida : [{ text }];
}

export function parseReply(text: string): Block[] {
  const bloques: Block[] = [];
  let parrafo: string[] = [];
  let codigo: string[] | null = null;
  let lenguaje = "";
  const cerrarParrafo = () => {
    if (!parrafo.length) return;
    bloques.push({ kind: "p", lines: [inlines(parrafo.join(" "))] });
    parrafo = [];
  };
  for (const linea of text.split("\n")) {
    const cerca = CERCA.exec(linea);
    if (codigo !== null) {
      if (cerca) {
        bloques.push({ kind: "code", language: lenguaje, lines: codigo.map(texto => [{ text: texto }]) });
        codigo = null;
        lenguaje = "";
      } else codigo.push(linea);
      continue;
    }
    if (cerca) {
      cerrarParrafo();
      codigo = [];
      lenguaje = cerca[1];
      continue;
    }
    const vineta = VINETA.exec(linea);
    const numero = vineta ? null : NUMERO.exec(linea);
    if (vineta || numero) {
      cerrarParrafo();
      const kind = vineta ? "ul" : "ol";
      const ultimo = bloques[bloques.length - 1];
      const contenido = inlines((vineta ? vineta[1] : numero![1]).trim());
      if (ultimo && ultimo.kind === kind) ultimo.lines.push(contenido);
      else bloques.push({ kind, lines: [contenido] });
      continue;
    }
    if (!linea.trim()) { cerrarParrafo(); continue; }
    parrafo.push(linea.trim());
  }
  // Una cerca sin cerrar sigue siendo código: los modelos locales pueden cortar
  // justo antes de los tres acentos al alcanzar su límite de salida.
  if (codigo !== null) bloques.push({ kind: "code", language: lenguaje, lines: codigo.map(texto => [{ text: texto }]) });
  cerrarParrafo();
  return bloques;
}

/** Una palabra, sabiendo de qué bloque y línea viene. El revelado avanza sobre
 *  esta lista, así que la estructura no depende de cuánto se lleve mostrado. */
export interface Token extends Inline { block: number; line: number; kind: Block["kind"]; language?: string }

export function tokenize(blocks: Block[]): Token[] {
  const salida: Token[] = [];
  blocks.forEach((bloque, b) => bloque.lines.forEach((linea, l) => {
    if (bloque.kind === "code") {
      // Fragmentos fijos: una línea parcial puede crecer entre consultas al
      // servidor. Revelar la línea como un token hacía aparecer todo ese tramo
      // de golpe, incluso aunque su token ya estuviese visible.
      const chars = Array.from(linea.map(trozo => trozo.text).join(""));
      for (let i = 0; i < Math.max(1, chars.length); i += 4) {
        salida.push({ text: chars.slice(i, i + 4).join(""), block: b, line: l,
          kind: "code", language: bloque.language });
      }
      return;
    }
    linea.forEach(trozo => {
      if (trozo.code) { salida.push({ ...trozo, block: b, line: l, kind: bloque.kind }); return; }
      // Se conservan los espacios para no rehacer el texto al juntarlo.
      for (const palabra of trozo.text.split(/(\s+)/)) {
        if (palabra) salida.push({ ...trozo, text: palabra, block: b, line: l, kind: bloque.kind });
      }
    });
  }));
  return salida;
}

/** Los tokens ya mostrados, devueltos a su forma de bloques y líneas. */
export function regroup(tokens: Token[]): { kind: Block["kind"]; index: number; language?: string; lines: { index: number; parts: Token[] }[] }[] {
  const salida: { kind: Block["kind"]; index: number; language?: string; lines: { index: number; parts: Token[] }[] }[] = [];
  for (const token of tokens) {
    let bloque = salida[salida.length - 1];
    if (!bloque || bloque.index !== token.block) {
      bloque = { kind: token.kind, index: token.block, language: token.language, lines: [] };
      salida.push(bloque);
    }
    let linea = bloque.lines[bloque.lines.length - 1];
    if (!linea || linea.index !== token.line) {
      linea = { index: token.line, parts: [] };
      bloque.lines.push(linea);
    }
    linea.parts.push(token);
  }
  return salida;
}
