"use client";
import { motion } from "framer-motion";

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
      className="mx-auto max-w-2xl px-3"
    >
      <div className="rounded-xl border border-accent-amber/30 bg-accent-amber/5 p-3">
        <p className="mb-2 text-[0.72rem] font-semibold uppercase tracking-wide text-accent-amber">
          👇 Tap what you meant
        </p>
        <div className="flex flex-col gap-2">
          {options.map((opt, i) => (
            <button
              key={`${opt}-${i}`}
              onClick={() => onPick(opt)}
              className="rounded-lg border border-white/10 bg-bg-elevated px-3 py-2 text-left text-sm text-ink transition hover:border-accent/50 hover:bg-accent/10 active:scale-[0.99]"
            >
              {i === 0 ? "● " : "○ "}
              {opt}
            </button>
          ))}
        </div>
      </div>
    </motion.div>
  );
}
