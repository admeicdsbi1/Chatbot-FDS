"use client";
import { useEffect } from "react";
import { Star, Trash2, X } from "lucide-react";
import AnswerBody from "./AnswerBody";
import SourceList from "./SourceList";
import type { SavedAnswer } from "@/lib/types";

/**
 * Saved answers, readable without the network.
 *
 * Depot signal is unreliable and Render's free tier sleeps, so a technician who
 * bookmarked a procedure needs to be able to read it back cold. These live in
 * localStorage with their citations, so the whole panel works offline.
 */
export default function SavedPanel({
  items,
  onRemove,
  onClose,
}: {
  items: SavedAnswer[];
  onRemove: (id: string) => void;
  onClose: () => void;
}) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-stretch justify-center bg-bg-base/70 backdrop-blur-sm sm:items-center sm:p-6"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Saved answers"
        className="flex h-full w-full flex-col overflow-hidden border-line/15 bg-bg-panel shadow-rail sm:h-[min(85vh,880px)] sm:max-w-2xl sm:rounded-2xl sm:border"
      >
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-line/12 px-4 pb-3 pt-[calc(env(safe-area-inset-top,0px)+0.85rem)] sm:pt-4">
          <div>
            <h2 className="text-[0.98rem] font-bold text-ink">Saved answers</h2>
            <p className="text-[0.76rem] text-ink-dim">
              {items.length === 0
                ? "Nothing saved yet"
                : `${items.length} saved · available offline`}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close saved answers"
            className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-line/15 text-ink-dim transition hover:text-accent active:scale-95"
          >
            <X size={18} aria-hidden />
          </button>
        </header>

        <div className="scroll-area flex-1 overflow-y-auto px-4 py-3">
          {items.length === 0 ? (
            <p className="flex flex-col items-center gap-2 py-14 text-center text-[0.85rem] text-ink-dim">
              <Star size={22} className="text-ink-faint" aria-hidden />
              Tap <strong className="font-semibold text-ink">Save</strong> under
              any answer to keep it here for offline reference.
            </p>
          ) : (
            <ul className="flex flex-col gap-3">
              {items.map((s) => (
                <li
                  key={s.id}
                  className="rounded-xl border border-line/15 bg-bg-card p-3"
                >
                  <div className="mb-2 flex items-start justify-between gap-3">
                    <p className="text-[0.85rem] font-semibold leading-snug text-ink">
                      {s.question}
                    </p>
                    <button
                      type="button"
                      onClick={() => onRemove(s.id)}
                      aria-label="Remove from saved"
                      className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-ink-faint transition hover:text-accent-red"
                    >
                      <Trash2 size={14} aria-hidden />
                    </button>
                  </div>
                  <AnswerBody content={s.answer} />
                  <SourceList sourcesList={s.sourcesList} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
