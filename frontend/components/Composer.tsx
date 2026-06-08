"use client";
import { useRef } from "react";
import { ArrowUp } from "lucide-react";
import VoiceRecorder from "./VoiceRecorder";

export default function Composer({
  value,
  onChange,
  onSubmit,
  onAudio,
  busy,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onAudio: (blob: Blob) => Promise<void> | void;
  busy: boolean;
}) {
  const taRef = useRef<HTMLTextAreaElement>(null);

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  }

  return (
    <div className="pb-safe sticky bottom-0 z-20 border-t border-white/8 bg-bg-base/80 px-3 pt-3 backdrop-blur">
      <div className="mx-auto flex max-w-2xl items-end gap-2">
        <VoiceRecorder onAudio={onAudio} disabled={busy} />

        <div className="flex flex-1 items-end gap-2 rounded-2xl border border-white/10 bg-bg-card px-3 py-1.5 focus-within:border-accent/60 focus-within:shadow-glow">
          <textarea
            ref={taRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKey}
            rows={1}
            placeholder="Ask, or tap the mic…"
            className="max-h-28 flex-1 resize-none bg-transparent py-2 text-[0.95rem] text-ink placeholder:text-ink-faint focus:outline-none"
          />
        </div>

        <button
          onClick={onSubmit}
          disabled={busy || !value.trim()}
          aria-label="Send"
          className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-gradient-to-br from-accent to-accent-glow text-bg-base shadow-glow transition active:scale-95 disabled:opacity-40 disabled:shadow-none"
        >
          <ArrowUp size={22} strokeWidth={2.5} />
        </button>
      </div>
    </div>
  );
}
