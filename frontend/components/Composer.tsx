"use client";
import { useEffect, useRef } from "react";
import { ArrowUp, Square } from "lucide-react";
import VoiceRecorder from "./VoiceRecorder";

export default function Composer({
  value,
  onChange,
  onSubmit,
  onAudio,
  busy,
  onStop,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onAudio: (blob: Blob) => Promise<void> | void;
  busy: boolean;
  onStop?: () => void;
}) {
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Grow with the question, up to the max-height the CSS allows.
  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`;
  }, [value]);

  // "/" focuses the composer from anywhere, the way every search UI behaves —
  // but never while the user is already typing somewhere.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      const tag = t?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || t?.isContentEditable) return;
      e.preventDefault();
      taRef.current?.focus();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  }

  return (
    <div className="pb-safe sticky bottom-0 z-20 border-t border-line/12 bg-bg-base/85 px-3 pt-3 backdrop-blur sm:px-4">
      <div className="mx-auto flex w-full max-w-reading items-end gap-2">
        <VoiceRecorder onAudio={onAudio} disabled={busy} />

        <div className="flex min-w-0 flex-1 items-end rounded-2xl border border-line/15 bg-bg-card px-3 py-1 focus-within:border-accent/60 focus-within:shadow-glow">
          <label htmlFor="composer" className="sr-only">
            Your maintenance question
          </label>
          <textarea
            id="composer"
            ref={taRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKey}
            rows={1}
            placeholder="Ask a maintenance question…"
            className="max-h-32 min-h-[2.75rem] flex-1 resize-none bg-transparent py-2.5 text-[0.95rem] leading-snug text-ink placeholder:text-ink-faint focus:outline-none"
          />
        </div>

        {busy && onStop ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop generating"
            className="grid h-12 w-12 shrink-0 place-items-center rounded-full border border-line/20 bg-bg-card text-ink transition hover:border-accent/60 active:scale-95"
          >
            <Square size={17} strokeWidth={2.5} fill="currentColor" aria-hidden />
          </button>
        ) : (
          <button
            type="button"
            onClick={onSubmit}
            disabled={busy || !value.trim()}
            aria-label="Send question"
            className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-accent text-bg-base shadow-glow transition active:scale-95 disabled:opacity-40 disabled:shadow-none"
          >
            <ArrowUp size={22} strokeWidth={2.5} aria-hidden />
          </button>
        )}
      </div>
    </div>
  );
}
