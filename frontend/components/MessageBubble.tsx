"use client";
import { useState } from "react";
import { motion } from "framer-motion";
import {
  BookOpen,
  Check,
  ChevronDown,
  Copy,
  RotateCcw,
  ShieldAlert,
  Star,
  ThumbsDown,
  ThumbsUp,
  Volume2,
  WifiOff,
} from "lucide-react";
import AnswerBody from "./AnswerBody";
import SourceList from "./SourceList";
import { sendFeedback } from "@/lib/api";
import type { Message } from "@/lib/types";

function IconAction({
  onClick,
  active,
  label,
  children,
}: {
  onClick: () => void;
  active?: boolean;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      aria-pressed={active}
      className={`inline-flex min-h-[32px] items-center gap-1 rounded-lg px-1.5 py-1 text-[0.72rem] font-medium transition ${
        active
          ? "text-accent"
          : "text-ink-dim hover:bg-line/5 hover:text-accent"
      }`}
    >
      {children}
    </button>
  );
}

// What a 👎 can say was wrong. Each maps to a different fix — see
// ingest/eval/README.md "Feedback triage" — so they are worth the extra tap.
const DOWN_REASONS = [
  "Wrong value",
  "Wrong coach/OEM",
  "Incomplete",
  "Outdated (newer letter exists)",
  "Not found but should be",
  "Other",
];

export default function MessageBubble({
  msg,
  onReplay,
  onToggleSave,
  onRate,
  onRetry,
  saved,
  question,
}: {
  msg: Message;
  onReplay?: (m: Message) => void;
  onToggleSave?: (m: Message) => void;
  /** Persist the rating on the message, so it survives a reload. */
  onRate?: (m: Message, rating: "up" | "down") => void;
  /** Re-ask the question — offered on a failed (⚠️) answer. */
  onRetry?: () => void;
  saved?: boolean;
  /** The user turn this answer responds to — sent with feedback for context. */
  question?: string;
}) {
  const [showSources, setShowSources] = useState(true);
  const [copied, setCopied] = useState(false);
  const [downOpen, setDownOpen] = useState(false);
  const [reasons, setReasons] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [correction, setCorrection] = useState("");
  const [thanks, setThanks] = useState(false);
  const rating = msg.rating ?? null;
  const isUser = msg.role === "user";

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-end"
      >
        <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-accent/15 px-4 py-2.5 text-[0.95rem] text-ink ring-1 ring-accent/30">
          {msg.content}
        </div>
      </motion.div>
    );
  }

  const nSources = msg.sourcesList?.length ?? 0;
  const isError = msg.content.startsWith("⚠️");
  const degraded = msg.retrievalMode === "keyword-only";
  const withheld = msg.valuesSuppressed ?? 0;

  function copy() {
    navigator.clipboard?.writeText(msg.content).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1600);
      },
      () => {}
    );
  }

  function submit(
    value: "up" | "down",
    extra?: { reasons: string[]; note: string; correction: string }
  ) {
    sendFeedback({
      message_id: msg.id,
      rating: value,
      question: question || "",
      answer_preview: msg.content.slice(0, 300),
      answer: msg.content.slice(0, 4000),
      request_id: msg.requestId,
      provider: msg.provider,
      values_suppressed: msg.valuesSuppressed ?? 0,
      sources: (msg.sourcesList ?? []).map(
        (s) => `${s.doc_id}${s.page ? ` p.${s.page}` : ""}`
      ),
      ...extra,
    });
    onRate?.(msg, value);
    setDownOpen(false);
    setThanks(true);
    setTimeout(() => setThanks(false), 2500);
  }

  function rateUp() {
    if (rating !== "up") submit("up");
  }

  function rateDown() {
    // A 👎 is only actionable with a reason, so ask before sending.
    setDownOpen((o) => !o);
  }

  function toggleReason(r: string) {
    setReasons((prev) =>
      prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r]
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex justify-start"
    >
      <div className="w-full max-w-full min-w-0 rounded-2xl rounded-bl-md border border-line/12 bg-bg-card px-3.5 py-3 shadow-card sm:px-4">
        <AnswerBody content={msg.content} />

        {/* Honest quality signals. A maintenance user must be able to tell a
            grounded answer from a degraded one at a glance. */}
        {!isError && (degraded || withheld > 0 || nSources > 0) && (
          <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.72rem]">
            {nSources > 0 && (
              <span className="text-ink-faint">
                Grounded in {nSources} source{nSources === 1 ? "" : "s"}
              </span>
            )}
            {withheld > 0 && (
              <span className="inline-flex items-center gap-1 text-accent-amber">
                <ShieldAlert size={12} aria-hidden />
                {withheld} value{withheld === 1 ? "" : "s"} withheld — not
                verifiable in the source
              </span>
            )}
            {degraded && (
              <span className="inline-flex items-center gap-1 text-accent-amber">
                <WifiOff size={12} aria-hidden />
                Reduced search mode
              </span>
            )}
          </div>
        )}

        <div className="mt-2 flex flex-wrap items-center gap-0.5 border-t border-line/10 pt-1.5">
          {onReplay && (
            <IconAction onClick={() => onReplay(msg)} label="Read the answer aloud">
              <Volume2 size={14} aria-hidden /> Replay
            </IconAction>
          )}
          <IconAction onClick={copy} label="Copy answer" active={copied}>
            {copied ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />}
            {copied ? "Copied" : "Copy"}
          </IconAction>
          {onToggleSave && !isError && (
            <IconAction
              onClick={() => onToggleSave(msg)}
              label={saved ? "Remove from saved" : "Save this answer"}
              active={saved}
            >
              <Star size={14} fill={saved ? "currentColor" : "none"} aria-hidden />
              {saved ? "Saved" : "Save"}
            </IconAction>
          )}
          {(msg.sources || nSources > 0) && (
            <IconAction
              onClick={() => setShowSources((s) => !s)}
              label={showSources ? "Hide sources" : "Show sources"}
            >
              <BookOpen size={14} aria-hidden /> Sources
              <ChevronDown
                size={13}
                aria-hidden
                className={`transition ${showSources ? "rotate-180" : ""}`}
              />
            </IconAction>
          )}
          {isError && onRetry && (
            <IconAction onClick={onRetry} label="Ask this question again">
              <RotateCcw size={14} aria-hidden /> Try again
            </IconAction>
          )}
          {/* Shown on failed answers too: "it failed" is feedback worth having. */}
          <div className="ml-auto flex items-center gap-0.5">
            {thanks && (
              <span className="mr-1 text-[0.72rem] text-accent-green" role="status">
                Thanks — sent
              </span>
            )}
            <IconAction
              onClick={rateUp}
              label="This answer was helpful"
              active={rating === "up"}
            >
              <ThumbsUp size={14} aria-hidden />
            </IconAction>
            <IconAction
              onClick={rateDown}
              label="This answer was wrong or unhelpful"
              active={rating === "down" || downOpen}
            >
              <ThumbsDown size={14} aria-hidden />
            </IconAction>
          </div>
        </div>

        {downOpen && (
          <div className="mt-2 rounded-xl border border-line/12 px-3 py-2.5 text-[0.8rem]">
            <p className="mb-2 font-medium text-ink">What was wrong?</p>
            <div className="mb-2 flex flex-wrap gap-1.5">
              {DOWN_REASONS.map((r) => {
                const on = reasons.includes(r);
                return (
                  <button
                    key={r}
                    type="button"
                    aria-pressed={on}
                    onClick={() => toggleReason(r)}
                    className={`min-h-[32px] rounded-full border px-2.5 py-1 text-[0.72rem] font-medium transition ${
                      on
                        ? "border-accent bg-accent/15 text-accent"
                        : "border-line/15 text-ink-dim hover:text-accent"
                    }`}
                  >
                    {r}
                  </button>
                );
              })}
            </div>
            <textarea
              value={correction}
              onChange={(e) => setCorrection(e.target.value)}
              rows={2}
              aria-label="Correct value or reference"
              placeholder="Correct value / reference, if you know it (optional)"
              className="mb-1.5 w-full resize-y rounded-lg border border-line/15 bg-bg-card px-2.5 py-1.5 text-[0.8rem] text-ink placeholder:text-ink-faint"
            />
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={1}
              aria-label="Other comments"
              placeholder="Anything else (optional)"
              className="mb-2 w-full resize-y rounded-lg border border-line/15 bg-bg-card px-2.5 py-1.5 text-[0.8rem] text-ink placeholder:text-ink-faint"
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setDownOpen(false)}
                className="min-h-[32px] rounded-lg px-3 py-1.5 text-[0.75rem] font-medium text-ink-dim hover:text-ink"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() =>
                  submit("down", {
                    reasons,
                    note: note.trim(),
                    correction: correction.trim(),
                  })
                }
                className="min-h-[32px] rounded-lg bg-accent/15 px-3 py-1.5 text-[0.75rem] font-semibold text-accent ring-1 ring-accent/30 hover:bg-accent/25"
              >
                Send feedback
              </button>
            </div>
          </div>
        )}

        {showSources && (
          <SourceList sources={msg.sources} sourcesList={msg.sourcesList} />
        )}
      </div>
    </motion.div>
  );
}
