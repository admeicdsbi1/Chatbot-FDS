"use client";
import { useState } from "react";
import { motion } from "framer-motion";
import {
  BookOpen,
  Check,
  ChevronDown,
  Copy,
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

export default function MessageBubble({
  msg,
  onReplay,
  onToggleSave,
  saved,
  question,
}: {
  msg: Message;
  onReplay?: (m: Message) => void;
  onToggleSave?: (m: Message) => void;
  saved?: boolean;
  /** The user turn this answer responds to — sent with feedback for context. */
  question?: string;
}) {
  const [showSources, setShowSources] = useState(true);
  const [copied, setCopied] = useState(false);
  const [rating, setRating] = useState<"up" | "down" | null>(null);
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

  function rate(value: "up" | "down") {
    const next = rating === value ? null : value;
    setRating(next);
    if (next) {
      sendFeedback({
        message_id: msg.id,
        rating: next,
        question: question || "",
        answer_preview: msg.content.slice(0, 300),
      });
    }
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
          {!isError && (
            <div className="ml-auto flex items-center gap-0.5">
              <IconAction
                onClick={() => rate("up")}
                label="This answer was helpful"
                active={rating === "up"}
              >
                <ThumbsUp size={14} aria-hidden />
              </IconAction>
              <IconAction
                onClick={() => rate("down")}
                label="This answer was wrong or unhelpful"
                active={rating === "down"}
              >
                <ThumbsDown size={14} aria-hidden />
              </IconAction>
            </div>
          )}
        </div>

        {showSources && (
          <SourceList sources={msg.sources} sourcesList={msg.sourcesList} />
        )}
      </div>
    </motion.div>
  );
}
