/** Lo que Helios escribe viene en Markdown —viñetas, negrita, `código`— y la
 *  interfaz lo soltaba en un párrafo plano: un listado de vecinos salía todo
 *  seguido y sin jerarquía. Esto lo convierte en bloques para pintarlo.
 *
 *  Deliberadamente pequeño: solo lo que este modelo usa de verdad. Nada de HTML
 *  incrustado, que además sería texto ajeno metido en la página. */
export interface Inline { text: string; bold?: boolean; code?: boolean; italic?: boolean }
export interface Block {
  kind: "p" | "ul" | "ol" | "code" | "h" | "table";
  lines: Inline[][];
  language?: string;
  /** Lista de resultados «**nombre** (valor)»: se pinta en dos columnas. */
  entries?: boolean;
  /** Título «### …»: 1 a 6. */
  level?: number;
  /** Tabla: filas y, en cada fila, sus celdas. La primera fila es la cabecera. */
  cells?: Inline[][][];
}

const VINETA = /^\s*[*-]\s+(.*)$/;
const NUMERO = /^\s*\d+[.)]\s+(.*)$/;
const CERCA = /^\s*```([^\s`]*)\s*$/;
const TITULO = /^\s*(#{1,6})\s+(.*?)\s*#*\s*$/;
const FILA = /^\s*\|.*\|\s*$/;
const SEPARADOR = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

/** Una celda corta (nombre, modelo, número de serie, estado) no se parte: la tabla se
 *  ensancha y se desliza. Solo el texto largo pasa a varias líneas. */
export const CELDA_CORTA = 32;

/** Celdas de una fila «| a | b |». */
function celdas(linea: string): string[] {
  return linea.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(celda => celda.trim());
}

/** Negrita, cursiva y código dentro de una línea. Un asterisco suelto es un asterisco,
 *  y el guion bajo nunca es cursiva: partiría nombres como immich_server. */
export function inlines(text: string): Inline[] {
  const salida: Inline[] = [];
  const patron = /\*\*(.+?)\*\*|`([^`]+)`|(?<![*\w])\*(?![\s*])([^*\n]*?[^\s*])\*(?![*\w])/g;
  let ultimo = 0;
  for (let m = patron.exec(text); m; m = patron.exec(text)) {
    if (m.index > ultimo) salida.push({ text: text.slice(ultimo, m.index) });
    if (m[1] !== undefined) salida.push({ text: m[1], bold: true });
    else if (m[2] !== undefined) salida.push({ text: m[2], code: true });
    else salida.push({ text: m[3], italic: true });
    ultimo = m.index + m[0].length;
  }
  if (ultimo < text.length) salida.push({ text: text.slice(ultimo) });
  return salida.length ? salida : [{ text }];
}

/** «**Parque Jurásico 3** (21.9 GB)» → nombre y valor. Solo cuando el nombre abre la
 *  línea en negrita y el valor es corto: una explicación no es un dato de tabla. */
export function entry(line: Inline[]): { name: Inline[]; value: string } | null {
  const inicio = line.findIndex(part => !part.bold);
  if (inicio <= 0) return null;
  const value = entryValue(line.slice(inicio).map(part => part.text).join(""));
  if (!value || value.length > 40) return null;
  return { name: line.slice(0, inicio), value };
}

/** El valor sin su envoltorio: «(39.3 GB)», «: 32 GB», «— terminada». */
export function entryValue(text: string) {
  return text.trim().replace(/^[:—–-]\s*/, "").replace(/^\((.*?)\)?$/, "$1").trim();
}

function markEntries(bloques: Block[]) {
  for (const bloque of bloques) {
    if ((bloque.kind === "ul" || bloque.kind === "ol") && bloque.lines.length >= 3
        && bloque.lines.every(linea => entry(linea) !== null)) bloque.entries = true;
  }
  return bloques;
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
  const lineas = text.split("\n");
  for (let n = 0; n < lineas.length; n++) {
    const linea = lineas[n];
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
    // Tabla: una fila «| … |» seguida de su separador «|:--|:--|». Sin separador aún
    // (llegando en directo) sigue siendo texto hasta que aparezca.
    if (FILA.test(linea) && n + 1 < lineas.length && SEPARADOR.test(lineas[n + 1])) {
      cerrarParrafo();
      const filas = [celdas(linea)];
      n += 1;
      while (n + 1 < lineas.length && FILA.test(lineas[n + 1])) filas.push(celdas(lineas[++n]));
      const cells = filas.map(fila => fila.map(celda => inlines(celda)));
      bloques.push({ kind: "table", cells, lines: cells.map(fila => fila.flat()) });
      continue;
    }
    const titulo = TITULO.exec(linea);
    if (titulo) {
      cerrarParrafo();
      bloques.push({ kind: "h", level: titulo[1].length, lines: [inlines(titulo[2])] });
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
  return markEntries(bloques);
}

/** Una palabra, sabiendo de qué bloque y línea viene. El revelado avanza sobre
 *  esta lista, así que la estructura no depende de cuánto se lleve mostrado. */
export interface Token extends Inline { block: number; line: number; kind: Block["kind"]; language?: string; entries?: boolean; level?: number; cell?: number }

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
    const base = { block: b, line: l, kind: bloque.kind, entries: bloque.entries, level: bloque.level };
    const partes = (trozos: Inline[], cell?: number) => trozos.forEach(trozo => {
      if (trozo.code) { salida.push({ ...trozo, ...base, cell }); return; }
      // Se conservan los espacios para no rehacer el texto al juntarlo.
      for (const palabra of trozo.text.split(/(\s+)/)) {
        if (palabra) salida.push({ ...trozo, text: palabra, ...base, cell });
      }
    });
    if (bloque.kind === "table" && bloque.cells) {
      // Una celda vacía no deja token: se marca para que la fila conserve sus columnas.
      bloque.cells[l].forEach((celda, c) => celda.length && celda.some(t => t.text) ? partes(celda, c)
        : salida.push({ text: "", ...base, cell: c }));
      return;
    }
    partes(linea);
  }));
  return salida;
}

/** Los tokens ya mostrados, devueltos a su forma de bloques y líneas. */
export function regroup(tokens: Token[]): { kind: Block["kind"]; index: number; language?: string; entries?: boolean; level?: number; lines: { index: number; parts: Token[] }[] }[] {
  const salida: { kind: Block["kind"]; index: number; language?: string; entries?: boolean; level?: number; lines: { index: number; parts: Token[] }[] }[] = [];
  for (const token of tokens) {
    let bloque = salida[salida.length - 1];
    if (!bloque || bloque.index !== token.block) {
      bloque = { kind: token.kind, index: token.block, language: token.language, entries: token.entries, level: token.level, lines: [] };
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
