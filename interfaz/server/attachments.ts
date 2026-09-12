import type { Plugin } from "vite";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, extname } from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { heliosProxyOrigin } from "../lib/helios/proxy";
const run = promisify(execFile);
const maxBytes = 10 * 1024 * 1024;

/** Local document extraction; files are deleted immediately after processing. */
export function attachmentPlugin(): Plugin {
  return { name: "helios-local-attachments", configureServer(server) {
    server.middlewares.use("/api/attachments", async (request, response) => {
      const json = (status: number, data: unknown) => {
        response.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
        response.end(JSON.stringify(data));
      };
      if (request.method !== "POST") { json(405, { error: "Método no permitido" }); return; }
      const origin = request.headers.origin;
      if (!origin || heliosProxyOrigin(origin) !== "http://127.0.0.1:8080") { json(403, { error: "Origen no permitido" }); return; }
      let directory: string | undefined;
      try {
        const name = new URL(request.url || "/", "http://localhost").searchParams.get("name") || "documento";
        const extension = extname(name).toLowerCase();
        if (![".txt", ".md", ".csv", ".json", ".pdf", ".docx"].includes(extension)) throw new Error("Formato no disponible. Usa PDF con texto, DOCX, TXT, MD, CSV o JSON.");
        const chunks: Buffer[] = [];
        let size = 0;
        for await (const chunk of request) {
          size += chunk.length;
          if (size > maxBytes) { json(413, { error: "El máximo es 10 MB por archivo." }); return; }
          chunks.push(Buffer.from(chunk));
        }
        const bytes = Buffer.concat(chunks);
        if (!bytes.length) throw new Error("El archivo está vacío.");
        let text: string;
        if (extension === ".pdf" || extension === ".docx") {
          directory = await mkdtemp(join(tmpdir(), "helios-document-"));
          const path = join(directory, `document${extension}`);
          await writeFile(path, bytes, { mode: 0o600 });
          const options = { timeout: 20000, maxBuffer: 2 * 1024 * 1024 };
          try {
            const result = extension === ".pdf"
              ? await run("pdftotext", ["-layout", "-enc", "UTF-8", path, "-"], options)
              : await run("python3", [join(process.cwd(), "scripts/read-document.py"), path], options);
            text = result.stdout;
          } catch { throw new Error("No se pudo leer el documento. Comprueba que sea válido, no esté protegido y no supere el límite de texto."); }
        } else {
          try { text = new TextDecoder("utf-8", { fatal: true }).decode(bytes); }
          catch { throw new Error("Guarda el documento de texto con codificación UTF-8."); }
        }
        if (!text.trim()) throw new Error("Este archivo no contiene texto extraíble. Los PDF escaneados necesitan la conexión de visión.");
        if (Buffer.byteLength(text) > 2 * 1024 * 1024) throw new Error("El texto extraído supera 2 MB. Divide el documento en partes.");
        json(200, { name, text });
      } catch (error) { json(422, { error: error instanceof Error ? error.message : "No se pudo leer el archivo." }); }
      finally { if (directory) await rm(directory, { recursive: true, force: true }); }
    });
  } };
}
