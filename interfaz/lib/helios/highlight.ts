export type SyntaxKind = "comment" | "string" | "number" | "keyword" | "literal" | "tag" | "attribute" | "function" | "property" | "operator";
export interface SyntaxToken { text: string; kind?: SyntaxKind }

const JAVASCRIPT = new Set("as async await break case catch class const continue debugger default delete do else export extends finally for from function get if implements import in instanceof interface let new of package private protected public readonly return set static super switch throw try type typeof undefined var void while with yield".split(" "));
const CPP = new Set("alignas alignof auto bool break case catch char class const constexpr consteval constinit continue decltype default delete do double else enum explicit extern float for friend if inline int long mutable namespace new noexcept operator private protected public register reinterpret_cast return short signed sizeof static static_cast struct switch template this thread_local throw try typedef typename union unsigned using virtual void volatile while __global__ __device__ __host__ __shared__ __constant__ __forceinline__".split(" "));
const PYTHON = new Set("and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield".split(" "));
const SHELL = new Set("case do done elif else esac export fi for function if in local readonly select then time until while".split(" "));
const CSS = new Set("@charset @container @font-face @import @keyframes @layer @media @page @property @supports from to".split(" "));
const LITERALS = new Set(["true", "false", "null", "undefined", "True", "False", "None"]);
const BUILTINS = new Set("Array Boolean Date Error JSON Map Math Number Object Promise React RegExp Set String console document fetch navigator window print len range str int dict list set tuple".split(" "));
const TOKEN = /\/\*[\s\S]*?\*\/|<!--[\s\S]*?-->|\/\/[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|\b(?:0x[\da-f]+|\d+(?:\.\d+)?)\b|[A-Za-z_$][\w$-]*|\s+|./gi;

function languageFamily(language = "") {
  const value = language.toLowerCase();
  if (["c", "h", "cc", "cpp", "cxx", "hpp", "hxx", "cu", "cuh", "cuda", "c++"].includes(value)) return "cpp";
  if (["py", "python"].includes(value)) return "python";
  if (["sh", "shell", "bash", "zsh"].includes(value)) return "shell";
  if (["css", "scss", "sass", "less"].includes(value)) return "css";
  if (["html", "xml", "svg", "vue", "svelte"].includes(value)) return "markup";
  return "javascript";
}

/** Resaltado pequeño y determinista: devuelve texto para React, nunca HTML. */
export function highlightCode(source: string, language?: string): SyntaxToken[] {
  const family = languageFamily(language);
  const raw = source.match(TOKEN) ?? [];
  const result: SyntaxToken[] = [];
  let inTag = false;
  let expectTag = false;

  const following: (string | undefined)[] = new Array(raw.length);
  let next: string | undefined;
  for (let i = raw.length - 1; i >= 0; i -= 1) {
    following[i] = next;
    if (!/^\s+$/.test(raw[i])) next = raw[i];
  }
  const nextVisible = (index: number) => following[index];
  for (let index = 0; index < raw.length; index += 1) {
    const text = raw[index];
    let kind: SyntaxKind | undefined;

    if ((family !== "css" && family !== "markup" && text.startsWith("//")) || text.startsWith("/*") || text.startsWith("<!--") || ((family === "python" || family === "shell") && text.startsWith("#"))) {
      kind = "comment";
    } else if (/^["'`]/.test(text)) {
      kind = "string";
    } else if (/^(?:0x[\da-f]+|\d)/i.test(text)) {
      kind = "number";
    } else if (text === "<") {
      inTag = family === "markup" || ["jsx", "tsx"].includes((language ?? "").toLowerCase());
      expectTag = inTag;
      kind = inTag ? "tag" : "operator";
    } else if (inTag && text === ">") {
      inTag = false;
      kind = "tag";
    } else if (/^[A-Za-z_$]/.test(text)) {
      const keywords = family === "cpp" ? CPP : family === "python" ? PYTHON : family === "shell" ? SHELL : family === "css" ? CSS : JAVASCRIPT;
      if (inTag && expectTag) { kind = "tag"; expectTag = false; }
      else if (inTag && nextVisible(index) === "=") kind = "attribute";
      else if (keywords.has(text)) kind = "keyword";
      else if (LITERALS.has(text)) kind = "literal";
      else if (BUILTINS.has(text)) kind = "literal";
      else if (nextVisible(index) === "(") kind = "function";
      else if (raw[index - 1] === ".") kind = "property";
    } else if (/^[{}()[\].,:;=/+\-*%!&|?]$/.test(text)) {
      kind = inTag ? "tag" : "operator";
    }
    result.push(kind ? { text, kind } : { text });
  }
  return result;
}

/** Only known source extensions get syntax colors; prose remains plain text. */
export function codeLanguageForFilename(name: string): string | undefined {
  const extension = name.split('.').pop()?.toLowerCase();
  const supported = new Set(['c','h','cc','cpp','cxx','hpp','hxx','cu','cuh','js','jsx','ts','tsx','json','py','sh','bash','css','scss','html','xml','svg']);
  return extension && supported.has(extension) ? extension : undefined;
}
