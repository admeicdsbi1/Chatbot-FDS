"use client";

const QUESTIONS = [
  "FSDS error codes?",
  "Smoke test FSDS?",
  "WSP self test procedure?",
  "Dump valve air gap setting?",
  "WSP error codes Faiveley?",
  "BTA safety pin",
  "Speed sensor maintenance?",
  "FDSS aerosol temp",
];

export default function QuickQuestions({
  onPick,
}: {
  onPick: (q: string) => void;
}) {
  return (
    <div className="mx-auto max-w-2xl px-3 pb-1">
      <div className="scroll-area -mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
        {QUESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => onPick(q)}
            className="shrink-0 whitespace-nowrap rounded-full border border-white/10 bg-bg-card px-3 py-1.5 text-[0.72rem] font-medium text-ink-dim transition hover:border-accent/40 hover:text-accent active:scale-95"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
