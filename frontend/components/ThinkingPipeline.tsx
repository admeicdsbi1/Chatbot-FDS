"use client";
import { motion, AnimatePresence } from "framer-motion";
import type { Stage } from "@/lib/types";

const STEPS: { id: Stage; icon: string; label: string }[] = [
  { id: "understanding", icon: "🧠", label: "Understand" },
  { id: "searching", icon: "🔎", label: "Search" },
  { id: "reading", icon: "📖", label: "Read" },
  { id: "generating", icon: "⚡", label: "Generate" },
  { id: "speaking", icon: "🔊", label: "Voice" },
];

const ORDER: Stage[] = [
  "understanding",
  "searching",
  "reading",
  "generating",
  "speaking",
];

export default function ThinkingPipeline({ stage }: { stage: Stage }) {
  const visible = stage !== "idle";
  const currentIdx = ORDER.indexOf(stage);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          className="mx-auto max-w-2xl px-3"
        >
          <div className="glass overflow-hidden rounded-xl">
            {stage === "transcribing" ? (
              <div className="flex items-center gap-2 px-4 py-2.5 text-xs font-semibold text-accent">
                <span className="animate-pulseDot">🎙️</span>
                Transcribing your voice…
              </div>
            ) : (
              <div className="flex">
                {STEPS.map((s, i) => {
                  const done = i < currentIdx;
                  const active = i === currentIdx;
                  return (
                    <div
                      key={s.id}
                      className={`relative flex flex-1 items-center justify-center gap-1 border-r border-white/5 px-1 py-2 text-[0.58rem] font-semibold uppercase tracking-wide last:border-r-0 ${
                        active
                          ? "text-accent"
                          : done
                          ? "text-accent-green"
                          : "text-ink-faint"
                      }`}
                    >
                      <span className={`text-sm ${active ? "animate-spin" : ""}`}>
                        {done ? "✓" : s.icon}
                      </span>
                      <span className="hidden sm:inline">{s.label}</span>
                      {active && (
                        <span className="absolute bottom-0 left-0 h-0.5 animate-sweep bg-accent" />
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
