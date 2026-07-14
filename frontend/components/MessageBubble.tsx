"use client";
import { useState } from "react";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BookOpen, Volume2, ChevronDown } from "lucide-react";
import type { Message } from "@/lib/types";

export default function MessageBubble({
  msg,
  onReplay,
}: {
  msg: Message;
  onReplay?: (m: Message) => void;
}) {
  const [showSources, setShowSources] = useState(true);
  const isUser = msg.role === "user";

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-end"
      >
        <div className="max-w-[82%] rounded-2xl rounded-br-md bg-gradient-to-br from-accent/25 to-accent-glow/20 px-4 py-2.5 text-[0.92rem] text-ink shadow-card ring-1 ring-accent/20">
          {msg.content}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex justify-start"
    >
      <div className="max-w-[88%] rounded-2xl rounded-bl-md border border-white/8 bg-bg-card/80 px-4 py-3 shadow-card">
        <div className="answer-md text-ink">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
        </div>

        <div className="mt-2 flex items-center gap-3">
          {onReplay && (
            <button
              onClick={() => onReplay(msg)}
              className="inline-flex items-center gap-1 text-[0.7rem] text-ink-dim transition hover:text-accent"
            >
              <Volume2 size={13} /> Replay
            </button>
          )}
          {msg.sources && (
            <button
              onClick={() => setShowSources((s) => !s)}
              className="inline-flex items-center gap-1 text-[0.7rem] text-ink-dim transition hover:text-accent"
            >
              <BookOpen size={13} /> Sources
              <ChevronDown
                size={13}
                className={`transition ${showSources ? "rotate-180" : ""}`}
              />
            </button>
          )}
        </div>

        {showSources && msg.sources && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            className="answer-md mt-2 rounded-lg border border-white/8 bg-black/20 px-3 py-2 text-[0.78rem] text-ink-dim"
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.sources}</ReactMarkdown>
          </motion.div>
        )}
      </div>
    </motion.div>
  );
}
