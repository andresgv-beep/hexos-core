"use client";
import { useEffect, useRef, useState } from "react";
import { audioToVoice, VOICE_MAX_SECONDS } from "@/lib/helios/voice";

type Voice = { base64: string; seconds: number };

const reloj = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

/** El modo voz: el emblema grande escucha mientras hablas. Graba al abrirse y
 *  entrega el audio ya en WAV 16 kHz al pulsar Enviar; Cancelar lo descarta. */
export function VoiceMode({ onSend, onCancel, onError }: {
  onSend: (voice: Voice) => void;
  onCancel: () => void;
  onError: (message: string) => void;
}) {
  const [elapsed, setElapsed] = useState(0);
  const [preparing, setPreparing] = useState(false);
  const overlay = useRef<HTMLDivElement>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const keep = useRef(false);
  const sendButton = useRef<HTMLButtonElement>(null);
  // Las funciones de fuera cambian en cada render; la grabación solo se monta una vez.
  const handlers = useRef({ onSend, onCancel, onError });
  useEffect(() => { handlers.current = { onSend, onCancel, onError }; });

  useEffect(() => {
    let disposed = false;
    let stream: MediaStream | null = null;
    let context: AudioContext | null = null;
    let frame = 0;
    let timer: ReturnType<typeof setInterval> | undefined;
    (async () => {
      try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
      catch { handlers.current.onError("No hay permiso para usar el micrófono."); handlers.current.onCancel(); return; }
      if (disposed) { stream.getTracks().forEach(track => track.stop()); return; }
      const chunks: Blob[] = [];
      const media = new MediaRecorder(stream);
      media.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      media.onstop = async () => {
        stream?.getTracks().forEach(track => track.stop());
        if (!keep.current) return;
        try { handlers.current.onSend(await audioToVoice(await new Blob(chunks).arrayBuffer())); }
        catch (error) { handlers.current.onError(error instanceof Error ? error.message : "No se pudo preparar el audio."); handlers.current.onCancel(); }
      };
      recorder.current = media;
      media.start();
      const started = Date.now();
      timer = setInterval(() => {
        const seconds = (Date.now() - started) / 1000;
        setElapsed(seconds);
        // El 12B oye 30 s como mucho: al llegar, se envía lo grabado.
        if (seconds >= VOICE_MAX_SECONDS && media.state === "recording") { keep.current = true; setPreparing(true); media.stop(); }
      }, 200);
      // Las ondas siguen el volumen de la voz: una variable CSS, sin rerenderizar.
      context = new AudioContext();
      const analyser = context.createAnalyser();
      analyser.fftSize = 512;
      context.createMediaStreamSource(stream).connect(analyser);
      const samples = new Uint8Array(analyser.fftSize);
      const pulse = () => {
        analyser.getByteTimeDomainData(samples);
        let sum = 0;
        for (const value of samples) sum += ((value - 128) / 128) ** 2;
        const level = Math.min(1, Math.sqrt(sum / samples.length) * 4);
        overlay.current?.style.setProperty("--voice-level", level.toFixed(3));
        frame = requestAnimationFrame(pulse);
      };
      pulse();
    })();
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      if (timer) clearInterval(timer);
      void context?.close();
      if (recorder.current?.state === "recording") recorder.current.stop();
      else stream?.getTracks().forEach(track => track.stop());
    };
  }, []);

  useEffect(() => {
    sendButton.current?.focus();
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") handlers.current.onCancel(); };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, []);

  function enviar() {
    if (recorder.current?.state !== "recording") return;
    keep.current = true;
    setPreparing(true);
    recorder.current.stop();
  }

  return <div ref={overlay} className="voice-mode" role="dialog" aria-modal="true" aria-labelledby="voice-title">
    <div className="voice-mode-orb" aria-hidden="true">
      <i /><i /><i />
      <span className="voice-mode-emblem"><span /></span>
    </div>
    <h2 id="voice-title">{preparing ? "Un momento…" : "Te escucho…"}</h2>
    <p className="voice-mode-hint">Habla con normalidad; cuando termines, pulsa Enviar.</p>
    <div className="voice-mode-actions">
      <span className="voice-mode-time" aria-label={`${Math.floor(elapsed)} de ${VOICE_MAX_SECONDS} segundos`}>{reloj(elapsed)} / {reloj(VOICE_MAX_SECONDS)}</span>
      <button ref={sendButton} type="button" className="voice-mode-send" disabled={preparing} onClick={enviar}>Enviar</button>
      <button type="button" className="voice-mode-cancel" disabled={preparing} onClick={onCancel}>Cancelar</button>
    </div>
  </div>;
}
