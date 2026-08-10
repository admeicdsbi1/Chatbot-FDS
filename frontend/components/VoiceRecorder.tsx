"use client";
import { useEffect, useRef, useState } from "react";
import { Mic, Square, Loader2 } from "lucide-react";

type RecState = "idle" | "recording" | "processing";

const MIN_MS = 600; // guard against accidental taps

export default function VoiceRecorder({
  onAudio,
  disabled,
}: {
  onAudio: (blob: Blob) => Promise<void> | void;
  disabled?: boolean;
}) {
  const [state, setState] = useState<RecState>("idle");
  const [elapsed, setElapsed] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const startedRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => stopTimer(), []);

  function stopTimer() {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  }

  async function start() {
    if (disabled) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "";
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunksRef.current = [];
      rec.ondataavailable = (e) => e.data.size > 0 && chunksRef.current.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const dur = Date.now() - startedRef.current;
        const blob = new Blob(chunksRef.current, {
          type: mime || "audio/webm",
        });
        if (dur < MIN_MS || blob.size < 1200) {
          setState("idle");
          return;
        }
        setState("processing");
        try {
          await onAudio(blob);
        } finally {
          setState("idle");
        }
      };
      recorderRef.current = rec;
      startedRef.current = Date.now();
      rec.start();
      setState("recording");
      setElapsed(0);
      timerRef.current = setInterval(
        () => setElapsed(Math.floor((Date.now() - startedRef.current) / 1000)),
        250
      );
    } catch {
      setState("idle");
      alert("Microphone access is needed for voice. Please allow it and retry.");
    }
  }

  function stop() {
    stopTimer();
    recorderRef.current?.stop();
  }

  const recording = state === "recording";
  const processing = state === "processing";

  return (
    <button
      type="button"
      disabled={disabled || processing}
      onClick={recording ? stop : start}
      aria-label={recording ? "Stop recording" : "Record voice"}
      className={`relative grid h-12 w-12 shrink-0 place-items-center rounded-full transition active:scale-95 disabled:opacity-50 ${
        recording
          ? "bg-accent-red text-bg-base ring-4 ring-accent-red/25"
          : "bg-bg-elevated text-accent ring-1 ring-accent/30 hover:ring-accent/60"
      }`}
    >
      {recording && (
        <span className="absolute inset-0 animate-ping rounded-full bg-accent-red/40" />
      )}
      {processing ? (
        <Loader2 size={20} className="animate-spin" />
      ) : recording ? (
        <span className="relative flex items-center gap-1">
          <Square size={16} fill="currentColor" />
        </span>
      ) : (
        <Mic size={20} />
      )}
      {recording && (
        <span className="absolute -bottom-5 text-[0.68rem] font-semibold text-accent-red">
          {elapsed}s
        </span>
      )}
    </button>
  );
}
