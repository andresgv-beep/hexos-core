import type { compile } from "tailwindcss";

// Helios suele maquetar con el CDN de Tailwind, pero la vista previa no carga
// nada de fuera (CSP con default-src 'none'): el script se bloqueaba y la
// página salía sin estilos. Aquí se compila el CSS con el Tailwind que ya trae
// la interfaz y se mete en el propio documento. Sin red y sin tocar la CSP.

const CDN_SCRIPT = /<script\b[^>]*\bsrc\s*=\s*["']?https?:\/\/(?:cdn\.tailwindcss\.com|cdn\.jsdelivr\.net\/npm\/@tailwindcss\/browser)[^>]*>\s*<\/script>/gi;
// Configuración del CDN (tailwind.config = {...}): sin el script no hace nada.
const CDN_CONFIG = /<script\b[^>]*>\s*tailwind\.config\s*=[\s\S]*?<\/script>/gi;

/** La página pide Tailwind por CDN y, por tanto, depende de él para verse. */
export function usesTailwindCdn(html: string): boolean {
  CDN_SCRIPT.lastIndex = 0;
  return CDN_SCRIPT.test(html);
}

/**
 * Candidatos a clase: cualquier palabra del documento. Tailwind hace lo mismo
 * al escanear código; lo que no es una utilidad se descarta al compilar, y así
 * también valen las clases que el script de la página pone con classList.
 */
export function tailwindCandidates(html: string): string[] {
  const words = html.match(/[^\s"'`<>=;{}()]+/g) ?? [];
  return [...new Set(words.filter(word => word.length <= 120))];
}

type Compiler = Awaited<ReturnType<typeof compile>>;
const compilers = new Map<string, Promise<Compiler>>();

/** `stylesheet` es tailwindcss/index.css; se inyecta para no depender del bundler. */
export async function compileTailwind(html: string, stylesheet: string): Promise<string> {
  let compiler = compilers.get(stylesheet);
  if (!compiler) {
    // Bajo demanda: el compilador solo se descarga si alguna vista previa lo pide.
    compiler = import("tailwindcss").then(tailwind => tailwind.compile('@import "tailwindcss";', {
      base: "/",
      loadStylesheet: async () => ({ path: "tailwindcss/index.css", base: "/", content: stylesheet }),
    }));
    compilers.set(stylesheet, compiler);
  }
  return (await compiler).build(tailwindCandidates(html));
}

/** Quita el CDN (bloqueado de todos modos) y deja el CSS compilado en su sitio. */
export function inlineTailwind(html: string, css: string): string {
  const style = `<style data-helios-tailwind>${css.replace(/<\/style/gi, "<\\/style")}</style>`;
  let placed = false;
  const result = html.replace(CDN_CONFIG, "").replace(CDN_SCRIPT, () => {
    if (placed) return "";
    placed = true;
    return style;
  });
  return placed ? result : style + result;
}
