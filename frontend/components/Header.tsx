"use client";
import { Volume2, VolumeX } from "lucide-react";

const badges = [
  { label: "FSDS · FDSS", dot: "bg-accent-amber" },
  { label: "WSP", dot: "bg-accent" },
  { label: "Hindi + English", dot: "bg-accent-green" },
];

export default function Header({
  voiceOn,
  onToggleVoice,
}: {
  voiceOn: boolean;
  onToggleVoice: () => void;
}) {
  return (
    <header className="sticky top-0 z-20 glass border-b border-white/10 px-4 pt-[calc(env(safe-area-inset-top,0px)+0.75rem)] pb-3">
      <div className="mx-auto flex max-w-2xl items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-accent/30 to-accent-violet/30 shadow-glow">
            <span className="text-lg">⚙️</span>
          </div>
          <div className="leading-tight">
            <h1 className="bg-gradient-to-r from-accent to-accent-glow bg-clip-text text-[0.95rem] font-bold tracking-tight text-transparent">
              MAINTENANCE ASSISTANT
            </h1>
            <p className="text-[0.62rem] uppercase tracking-[0.18em] text-ink-dim">
              ICD-SBI · Coach Maintenance
            </p>
          </div>
        </div>
        <button
          onClick={onToggleVoice}
          aria-label={voiceOn ? "Mute voice replies" : "Enable voice replies"}
          className="grid h-9 w-9 place-items-center rounded-lg border border-white/10 bg-bg-elevated text-ink-dim transition hover:text-accent active:scale-95"
        >
          {voiceOn ? <Volume2 size={18} /> : <VolumeX size={18} />}
        </button>
      </div>

      <div className="mx-auto mt-2.5 flex max-w-2xl flex-wrap gap-1.5">
        {badges.map((b) => (
          <span
            key={b.label}
            className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-2.5 py-0.5 text-[0.6rem] font-semibold uppercase tracking-wider text-ink-dim"
          >
            <span className={`h-1.5 w-1.5 rounded-full ${b.dot} animate-pulseDot`} />
            {b.label}
          </span>
        ))}
      </div>
    </header>
  );
}
