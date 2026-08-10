"use client";
import {
  Clock,
  Library,
  Plus,
  Star,
  Trash2,
  Train,
} from "lucide-react";
import { COACH_SCOPES } from "@/lib/types";
import type { CoachScope, SavedAnswer, Thread } from "@/lib/types";

function timeAgo(ts: number): string {
  const s = Math.max(1, Math.floor((Date.now() - ts) / 1000));
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return d < 7 ? `${d}d ago` : new Date(ts).toLocaleDateString();
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="px-2 pb-1 pt-3 text-[0.68rem] font-bold uppercase tracking-[0.12em] text-ink-faint">
      {children}
    </h2>
  );
}

/**
 * The left rail: scope, the reference shelf, recent questions and saved
 * answers. On desktop it is always visible; on mobile AppShell renders it in a
 * drawer. It is deliberately the only navigation in the app — everything else
 * stays one conversation.
 */
export default function Rail({
  threads,
  activeThreadId,
  saved,
  scope,
  onScope,
  onNewThread,
  onOpenThread,
  onDeleteThread,
  onOpenLibrary,
  onOpenSaved,
}: {
  threads: Thread[];
  activeThreadId: string | null;
  saved: SavedAnswer[];
  scope: CoachScope;
  onScope: (s: CoachScope) => void;
  onNewThread: () => void;
  onOpenThread: (id: string) => void;
  onDeleteThread: (id: string) => void;
  onOpenLibrary: () => void;
  onOpenSaved: () => void;
}) {
  return (
    <nav
      aria-label="Main"
      className="flex h-full min-h-0 flex-col gap-1 overflow-y-auto scroll-area px-2 pb-4"
    >
      <button
        type="button"
        onClick={onNewThread}
        className="mt-2 flex min-h-[44px] w-full items-center gap-2 rounded-xl border border-accent/35 bg-accent/10 px-3 text-[0.88rem] font-semibold text-accent transition hover:bg-accent/16 active:scale-[0.99]"
      >
        <Plus size={17} aria-hidden /> New question
      </button>

      <SectionLabel>Coach</SectionLabel>
      <div
        role="radiogroup"
        aria-label="Coach scope"
        className="flex flex-wrap gap-1.5 px-1"
      >
        {COACH_SCOPES.map((c) => (
          <button
            key={c.value || "all"}
            type="button"
            role="radio"
            aria-checked={scope === c.value}
            onClick={() => onScope(c.value)}
            className={`min-h-[34px] rounded-lg border px-2.5 text-[0.78rem] font-medium transition ${
              scope === c.value
                ? "border-accent/60 bg-accent/12 text-accent"
                : "border-line/15 text-ink-dim hover:border-accent/40 hover:text-accent"
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>
      <p className="px-2 pt-1 text-[0.7rem] leading-snug text-ink-faint">
        {scope
          ? `Answers scoped to ${scope} unless your question names another coach.`
          : "Set a coach to skip the “which coach type?” question."}
      </p>

      <SectionLabel>Browse</SectionLabel>
      <button
        type="button"
        onClick={onOpenLibrary}
        className="flex min-h-[40px] w-full items-center gap-2 rounded-lg px-2.5 text-left text-[0.85rem] text-ink-dim transition hover:bg-line/5 hover:text-accent"
      >
        <Library size={16} aria-hidden /> Reference library
      </button>
      <button
        type="button"
        onClick={onOpenSaved}
        className="flex min-h-[40px] w-full items-center gap-2 rounded-lg px-2.5 text-left text-[0.85rem] text-ink-dim transition hover:bg-line/5 hover:text-accent"
      >
        <Star size={16} aria-hidden /> Saved answers
        {saved.length > 0 && (
          <span className="ml-auto rounded-full bg-line/10 px-1.5 text-[0.7rem] font-semibold text-ink-faint">
            {saved.length}
          </span>
        )}
      </button>

      <SectionLabel>Recent</SectionLabel>
      {threads.length === 0 ? (
        <p className="flex items-center gap-2 px-2.5 py-2 text-[0.78rem] text-ink-faint">
          <Clock size={14} aria-hidden /> Your questions will appear here.
        </p>
      ) : (
        <ul className="flex flex-col gap-0.5">
          {threads.map((t) => (
            <li key={t.id} className="group relative">
              <button
                type="button"
                onClick={() => onOpenThread(t.id)}
                aria-current={t.id === activeThreadId ? "true" : undefined}
                className={`w-full rounded-lg py-2 pl-2.5 pr-9 text-left transition ${
                  t.id === activeThreadId
                    ? "bg-accent/10 text-ink"
                    : "text-ink-dim hover:bg-line/5 hover:text-ink"
                }`}
              >
                <span className="block truncate text-[0.82rem] leading-snug">
                  {t.title}
                </span>
                <span className="mt-0.5 block text-[0.7rem] text-ink-faint">
                  {timeAgo(t.updatedAt)}
                </span>
              </button>
              <button
                type="button"
                onClick={() => onDeleteThread(t.id)}
                aria-label={`Delete “${t.title}”`}
                className="absolute right-1 top-1.5 grid h-8 w-8 place-items-center rounded-md text-ink-faint opacity-0 transition hover:text-accent-red focus-visible:opacity-100 group-hover:opacity-100"
              >
                <Trash2 size={14} aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-auto flex items-center gap-1.5 px-2 pt-4 text-[0.68rem] leading-snug text-ink-faint">
        <Train size={12} aria-hidden className="shrink-0" />
        ICD Sabarmati · Western Railway
      </p>
    </nav>
  );
}
