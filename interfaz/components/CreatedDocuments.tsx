"use client";

import { Download, Eye, FileSpreadsheet, FileText, FolderDown } from "lucide-react";
import type { CreatedDocument } from "@/lib/helios/hexos";

const megas = new Intl.NumberFormat("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const peso = (bytes: number) => bytes < 1_000_000 ? `${Math.max(1, Math.round(bytes / 1000))} kB` : `${megas.format(bytes / 1_000_000)} MB`;

/** El evento con el que la tarjeta abre la ventana de Descargas, esté donde esté pintada. */
export const ABRIR_DESCARGAS = "helios:abrir-descargas";

/** Lo que Helios ha creado en este turno: verlo antes de bajarlo, o bajarlo a este dispositivo.
 *  El fichero vive en el PC; también queda en la ventana de Descargas, que se abre desde aquí:
 *  quien no conoce el botón de la cabecera no sabría dónde buscarlo. */
export function CreatedDocuments({ documents }: { documents: CreatedDocument[] }) {
  return <div className="reply-documents">
  <p className="reply-documents-head">{documents.some(doc => doc.existing) ? "Archivos" : documents.length === 1 ? "Documento creado" : `${documents.length} documentos creados`}
    <button type="button" onClick={() => window.dispatchEvent(new Event(ABRIR_DESCARGAS))}>
      <FolderDown size={15} aria-hidden="true" /> Abrir Descargas</button></p>
  <ul className="downloads-list" aria-label="Archivos">
    {documents.map(doc => {
      const Icono = doc.kind === "Excel" ? FileSpreadsheet : FileText;
      return <li key={doc.id} className="downloads-row">
        <Icono size={20} aria-hidden="true" />
        <div className="downloads-what">
          <a href={doc.viewUrl || doc.saveUrl} target="_blank" rel="noreferrer">{doc.name}</a>
          <small>{[doc.kind, peso(doc.bytes), doc.source ?? "hecho por Helios"].join(" · ")}</small>
        </div>
        <div className="downloads-actions">
          {doc.viewUrl && <a href={doc.viewUrl} target="_blank" rel="noreferrer" aria-label={`Ver ${doc.name}`}>
            <Eye size={16} aria-hidden="true" /> Ver</a>}
          <a href={doc.saveUrl} download={doc.name} aria-label={`Descargar ${doc.name}`}>
            <Download size={16} aria-hidden="true" /> Descargar</a>
        </div>
      </li>;
    })}
  </ul>
  </div>;
}
