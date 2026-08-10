"use client";
import { motion } from "framer-motion";
import { Ear } from "lucide-react";

export default function Disambiguation({
  heard,
  alternatives,
  onPick,
}: {
  heard: string;
  alternatives: string[];
  onPick: (text: string) => void;
}) {
  const options = [heard, ...alternatives].filter(Boolean);
  if (options.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="mx-auto w-full max-w-reading px-3 sm:px-4"
    >
      <div className="rounded-xl border border-accent-amber/40 bg-accent-amber/8 p-3">
        <p className="mb-2 flex items-center gap-1.5 text-[0.74rem] font-bold uppercase tracking-wide text-accent-amber">
          <Ear size={14} aria-hidden /> Tap what you meant
        </p>
        <div className="flex flex-col gap-2">
          {options.map((opt, i) => (
            <button
              key={`${opt}-${i}`}
              type="button"
              onClick={() => onPick(opt)}
              className="min-h-[44px] rounded-lg border border-line/15 bg-bg-elevated px-3 py-2 text-left text-[0.9rem] text-ink transition hover:border-accent/50 hover:bg-accent/8 active:scale-[0.99]"
            >
              <span className="mr-1.5 text-ink-faint">{i === 0 ? "●" : "○"}</span>
              {opt}
            </button>
          ))}
        </div>
      </div>
    </motion.div>
  );
}
