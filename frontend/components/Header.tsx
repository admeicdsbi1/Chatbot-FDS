"use client";
import { useEffect, useState } from "react";
import {
  ChevronDown,
  Menu,
  Monitor,
  Moon,
  Sun,
  Volume2,
  VolumeX,
  Wrench,
} from "lucide-react";
import { applyTheme, loadTheme } from "@/lib/storage";
import { COACH_SCOPES } from "@/lib/types";
import type { CoachScope, Theme } from "@/lib/types";

const THEME_ORDER: Theme[] = ["system", "light", "dark"];
const THEME_META: Record<Theme, { icon: typeof Sun; label: string }> = {
  system: { icon: Monitor, label: "Theme: follow device" },
  light: { icon: Sun, label: "Theme: light" },
  dark: { icon: Moon, label: "Theme: dark" },
};

function IconButton({
  onClick,
  label,
  children,
}: {
  onClick: () => void;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-line/15 text-ink-dim transition hover:border-accent/40 hover:text-accent active:scale-95"
    >
      {children}
    </button>
  );
}

export default function Header({
  voiceOn,
  onToggleVoice,
  onOpenRail,
  scope,
  onScope,
  kbLabel,
}: {
  voiceOn: boolean;
  onToggleVoice: () => void;
  onOpenRail: () => void;
  scope: CoachScope;
  onScope: (s: CoachScope) => void;
  kbLabel: string;
}) {
  const [theme, setTheme] = useState<Theme>("system");

  // Read after mount: the pre-paint script in layout.tsx has already applied
  // the saved value to <html>, so this only syncs the button's own state.
  useEffect(() => setTheme(loadTheme()), []);

  function cycleTheme() {
    const next = THEME_ORDER[(THEME_ORDER.indexOf(theme) + 1) % THEME_ORDER.length];
    setTheme(next);
    applyTheme(next);
  }

  const ThemeIcon = THEME_META[theme].icon;

  return (
    <header className="glass sticky top-0 z-30 border-x-0 border-t-0 px-3 pb-2.5 pt-[calc(env(safe-area-inset-top,0px)+0.6rem)] sm:px-4">
      <div className="mx-auto flex w-full max-w-5xl items-center gap-2">
        <button
          type="button"
          onClick={onOpenRail}
          aria-label="Open navigation"
          className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-line/15 text-ink-dim transition hover:text-accent active:scale-95 lg:hidden"
        >
          <Menu size={19} aria-hidden />
        </button>

        <div className="flex min-w-0 flex-1 items-center gap-2.5">
          <span className="hidden h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent/12 text-accent sm:grid">
            <Wrench size={19} aria-hidden />
          </span>
          <div className="min-w-0 leading-tight">
            <h1 className="truncate text-[0.95rem] font-bold tracking-tight text-ink">
              Coach Maintenance Assistant
            </h1>
            <p className="truncate text-[0.7rem] text-ink-dim">
              ICD Sabarmati · Western Railway
              <span className="hidden sm:inline"> · {kbLabel}</span>
            </p>
          </div>
        </div>

        {/* Native select: one tap, one-handed, and accessible for free. */}
        <div className="relative shrink-0">
          <select
            value={scope}
            onChange={(e) => onScope(e.target.value as CoachScope)}
            aria-label="Coach scope"
            className="h-10 appearance-none rounded-lg border border-line/15 bg-bg-card pl-2.5 pr-7 text-[0.8rem] font-medium text-ink transition hover:border-accent/40 focus:outline-none"
          >
            {COACH_SCOPES.map((c) => (
              <option key={c.value || "all"} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
          <ChevronDown
            size={14}
            aria-hidden
            className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-ink-faint"
          />
        </div>

        <IconButton onClick={cycleTheme} label={THEME_META[theme].label}>
          <ThemeIcon size={18} aria-hidden />
        </IconButton>

        <IconButton
          onClick={onToggleVoice}
          label={voiceOn ? "Mute spoken replies" : "Enable spoken replies"}
        >
          {voiceOn ? <Volume2 size={18} aria-hidden /> : <VolumeX size={18} aria-hidden />}
        </IconButton>
      </div>
    </header>
  );
}
