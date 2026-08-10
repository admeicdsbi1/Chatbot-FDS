"use client";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain,
  Check,
  BookOpen,
  Loader2,
  Mic,
  Search,
  Volume2,
  Zap,
} from "lucide-react";
import type { Stage } from "@/lib/types";

const STEPS: { id: Stage; icon: typeof Brain; label: string }[] = [
  { id: "understanding", icon: Brain, label: "Understand" },
  { id: "searching", icon: Search, label: "Search" },
  { id: "reading", icon: BookOpen, label: "Read" },
  { id: "generating", icon: Zap, label: "Generate" },
  { id: "speaking", icon: Volume2, label: "Voice" },
];

const ORDER: Stage[] = [
  "understanding",
  "searching",
  "reading",
  "generating",
  "speaking",
];

// Plain-language status. Below `sm` the five-step strip degrades to five bare
// icons with no labels, which says nothing — so small screens get this instead.
const STATUS: Partial<Record<Stage, string>> = {
  transcribing: "Transcribing your voice…",
  understanding: "Understanding the question…",
  searching: "Searching the maintenance documents…",
  reading: "Reading the matching sections…",
  generating: "Writing the answer…",
  speaking: "Reading the answer aloud…",
};

export default function ThinkingPipeline({ stage }: { stage: Stage }) {
  const visible = stage !== "idle";
  const currentIdx = ORDER.indexOf(stage);
  const status = STATUS[stage] || "Working…";

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          className="mx-auto w-full max-w-reading px-3 sm:px-4"
        >
          {/* One announcement for assistive tech, whichever layout is shown. */}
          <p className="sr-only" role="status" aria-live="polite">
            {status}
          </p>

          <div className="glass overflow-hidden rounded-xl">
            {stage === "transcribing" || currentIdx < 0 ? (
              <div className="flex items-center gap-2 px-4 py-2.5 text-[0.8rem] font-semibold text-accent">
                {stage === "transcribing" ? (
                  <Mic size={15} className="animate-pulseDot" aria-hidden />
                ) : (
                  <Loader2 size={15} className="animate-spin" aria-hidden />
                )}
                {status}
              </div>
            ) : (
              <>
                <div className="flex items-center gap-2 px-4 py-2.5 text-[0.8rem] font-semibold text-accent sm:hidden">
                  <Loader2 size={15} className="animate-spin" aria-hidden />
                  {status}
                </div>

                <div className="hidden sm:flex">
                  {STEPS.map((s, i) => {
                    const done = i < currentIdx;
                    const active = i === currentIdx;
                    const Icon = s.icon;
                    return (
                      <div
                        key={s.id}
                        className={`relative flex flex-1 items-center justify-center gap-1.5 border-r border-line/10 px-1 py-2.5 text-[0.7rem] font-semibold uppercase tracking-wide last:border-r-0 ${
                          active
                            ? "text-accent"
                            : done
                            ? "text-accent-green"
                            : "text-ink-faint"
                        }`}
                      >
                        {done ? (
                          <Check size={14} aria-hidden />
                        ) : (
                          <Icon
                            size={14}
                            aria-hidden
                            className={active ? "animate-pulseDot" : ""}
                          />
                        )}
                        <span>{s.label}</span>
                        {active && (
                          <span className="absolute bottom-0 left-0 h-0.5 animate-sweep bg-accent" />
                        )}
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
