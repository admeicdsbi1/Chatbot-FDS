/**
 * storage.ts — everything the app remembers, in localStorage.
 *
 * Render's free tier has an ephemeral disk and no database, so history lives on
 * the device. That is also the right place for it: a depot phone is personal,
 * and nothing here needs to leave it.
 *
 * Keys are namespaced and versioned (`cma.v1.*`) so a future schema change can
 * be ignored rather than crash on someone's stale data. Every read is defensive:
 * a corrupt or foreign value returns the fallback instead of throwing, because a
 * broken history must never stop the app from answering a question.
 */
import type { CoachScope, Message, SavedAnswer, Theme, Thread } from "./types";

const NS = "cma.v1.";
/** Read by the pre-paint bootstrap script in app/layout.tsx — keep in sync. */
const THEME_KEY = "cma.theme";

const K = {
  threads: NS + "threads",
  activeThread: NS + "activeThread",
  saved: NS + "saved",
  scope: NS + "scope",
};

/** Oldest threads are dropped past this. Enough for weeks of depot use. */
const MAX_THREADS = 40;
const MAX_SAVED = 100;

function canUse(): boolean {
  try {
    return typeof window !== "undefined" && !!window.localStorage;
  } catch {
    return false;
  }
}

function read<T>(key: string, fallback: T): T {
  if (!canUse()) return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return parsed ?? fallback;
  } catch {
    // Corrupt entry — drop it so it can't fail again on every read.
    try {
      window.localStorage.removeItem(key);
    } catch {}
    return fallback;
  }
}

function write(key: string, value: unknown): void {
  if (!canUse()) return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Almost always the 5MB quota. Shed the oldest history and retry once;
    // if it still fails, silently continue — persistence is a convenience,
    // never a precondition for answering.
    try {
      const threads = read<Thread[]>(K.threads, []);
      if (threads.length > 5) {
        window.localStorage.setItem(
          K.threads,
          JSON.stringify(threads.slice(0, 5))
        );
        window.localStorage.setItem(key, JSON.stringify(value));
      }
    } catch {}
  }
}

// ---------------------------------------------------------------- threads

export function loadThreads(): Thread[] {
  const t = read<Thread[]>(K.threads, []);
  if (!Array.isArray(t)) return [];
  return t
    .filter((x) => x && typeof x.id === "string" && Array.isArray(x.messages))
    .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
}

export function saveThreads(threads: Thread[]): void {
  write(K.threads, threads.slice(0, MAX_THREADS));
}

/** First user message, trimmed — good enough as a history label. */
export function threadTitle(messages: Message[]): string {
  const first = messages.find((m) => m.role === "user" && m.content.trim());
  const text = (first?.content || "New question").trim().replace(/\s+/g, " ");
  return text.length > 60 ? text.slice(0, 59) + "…" : text;
}

export function upsertThread(threads: Thread[], thread: Thread): Thread[] {
  const rest = threads.filter((t) => t.id !== thread.id);
  return [thread, ...rest].slice(0, MAX_THREADS);
}

export function loadActiveThreadId(): string | null {
  return read<string | null>(K.activeThread, null);
}

export function saveActiveThreadId(id: string | null): void {
  write(K.activeThread, id);
}

// ------------------------------------------------------------- bookmarks

export function loadSaved(): SavedAnswer[] {
  const s = read<SavedAnswer[]>(K.saved, []);
  return Array.isArray(s) ? s.filter((x) => x && typeof x.id === "string") : [];
}

export function persistSaved(items: SavedAnswer[]): void {
  write(K.saved, items.slice(0, MAX_SAVED));
}

// --------------------------------------------------------- scope & theme

export function loadScope(): CoachScope {
  const v = read<string>(K.scope, "");
  const allowed = ["", "LHB", "ICF", "Vande Bharat", "Amrit Bharat"];
  return (allowed.includes(v) ? v : "") as CoachScope;
}

export function saveScope(scope: CoachScope): void {
  write(K.scope, scope);
}

export function loadTheme(): Theme {
  if (!canUse()) return "system";
  try {
    const v = window.localStorage.getItem(THEME_KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

/** Persists the choice and applies it immediately (the bootstrap script in
 *  layout.tsx replays it on the next load, before first paint). */
export function applyTheme(theme: Theme): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
  if (!canUse()) return;
  try {
    if (theme === "system") window.localStorage.removeItem(THEME_KEY);
    else window.localStorage.setItem(THEME_KEY, theme);
  } catch {}
}
