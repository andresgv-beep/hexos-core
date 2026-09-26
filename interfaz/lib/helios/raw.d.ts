// Vite: `import text from "archivo?raw"` entrega el contenido como cadena.
declare module "*?raw" {
  const content: string;
  export default content;
}
