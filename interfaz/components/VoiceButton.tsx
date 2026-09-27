"use client";
import { useSyncExternalStore } from "react";
import { Mic } from "lucide-react";
import { canRecord } from "@/lib/helios/voice";

const noSubscription = () => () => {};

/** Abre el modo voz. La grabación vive allí, con el emblema grande escuchando. */
export function VoiceButton({ onOpen, disabled }: { onOpen: () => void; disabled: boolean }) {
  // Se mira ya en el navegador: en el render del servidor no hay window, salía
  // «sin micrófono» y la hidratación dejaba el botón deshabilitado para siempre.
  // Servidor e hidratación ven false; justo después, el valor real.
  const available = useSyncExternalStore(noSubscription, canRecord, () => false);
  return <button type="button" className="icon-button"
    disabled={disabled || !available}
    title={available ? undefined : "El micrófono solo funciona con https o en localhost. Puedes adjuntar un archivo de audio."}
    aria-label="Hablar con Helios" onClick={onOpen}>
    <Mic size={20} />
  </button>;
}
