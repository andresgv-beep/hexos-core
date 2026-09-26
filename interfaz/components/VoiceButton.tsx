"use client";
import { useEffect, useRef, useState } from "react";
import { Mic, Square } from "lucide-react";
import { audioToVoice, canRecord, VOICE_MAX_SECONDS } from "@/lib/helios/voice";

/** Graba un mensaje de voz (hasta 30 s) y lo entrega ya en WAV 16 kHz. */
export function VoiceButton({ onRecorded, onError, disabled }: {
  onRecorded: (voice: { base64: string; seconds: number }) => void;
  onError: (message: string) => void;
  disabled: boolean;
}) {
  const [elapsed, setElapsed] = useState<number | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const available = canRecord();

  useEffect(() => () => {
    if (timer.current) clearInterval(timer.current);
    if (recorder.current?.state === "recording") recorder.current.stop();
  }, []);

  async function start() {
    let stream: MediaStream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch { onError("No hay permiso para usar el micrófono."); return; }
    const chunks: Blob[] = [];
    const media = new MediaRecorder(stream);
    media.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
    media.onstop = async () => {
      stream.getTracks().forEach(track => track.stop());
      if (timer.current) clearInterval(timer.current);
      setElapsed(null);
      try { onRecorded(await audioToVoice(await new Blob(chunks).arrayBuffer())); }
      catch (error) { onError(error instanceof Error ? error.message : "No se pudo preparar el audio."); }
    };
    recorder.current = media;
    media.start();
    const started = Date.now();
    setElapsed(0);
    timer.current = setInterval(() => {
      const seconds = (Date.now() - started) / 1000;
      setElapsed(seconds);
      // El 12B oye 30 s como mucho: se corta ahí en vez de fallar al enviar.
      if (seconds >= VOICE_MAX_SECONDS && media.state === "recording") media.stop();
    }, 200);
  }

  const recording = elapsed !== null;
  return <button type="button" className={`icon-button${recording ? " voice-recording" : ""}`}
    disabled={disabled || !available}
    title={available ? undefined : "El micrófono solo funciona con https o en localhost. Puedes adjuntar un archivo de audio."}
    aria-label={recording ? `Detener grabación (${Math.floor(elapsed)} s)` : "Grabar mensaje de voz"}
    onClick={() => { if (recording) recorder.current?.stop(); else void start(); }}>
    {recording ? <><Square size={16} /><span className="voice-elapsed">{Math.floor(elapsed)}s</span></> : <Mic size={20} />}
  </button>;
}
