"use client";
import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";
import SystemGrid from "./SystemGrid";
import type { Message } from "@/lib/types";

export default function Chat({
  messages,
  onReplay,
  onPickQuestion,
  onToggleSave,
  isSaved,
}: {
  messages: Message[];
  onReplay: (m: Message) => void;
  onPickQuestion: (q: string) => void;
  onToggleSave: (m: Message, question: string) => void;
  isSaved: (id: string) => boolean;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to latest on every new message — no fixed-height jank.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="scroll-area flex flex-1 flex-col overflow-y-auto">
        <div className="m-auto w-full">
          <SystemGrid onPick={onPickQuestion} />
        </div>
      </div>
    );
  }

  return (
    <div className="scroll-area flex-1 overflow-y-auto px-3 py-4 sm:px-4">
      <div className="mx-auto flex w-full max-w-reading flex-col gap-3">
        {messages.map((m, i) => {
          // The user turn this answer responds to — used for feedback context
          // and as the label when the answer is saved.
          const question =
            m.role === "assistant"
              ? messages
                  .slice(0, i)
                  .reverse()
                  .find((p) => p.role === "user")?.content || ""
              : "";
          return (
            <MessageBubble
              key={m.id}
              msg={m}
              question={question}
              onReplay={m.role === "assistant" ? onReplay : undefined}
              onToggleSave={
                m.role === "assistant" ? (msg) => onToggleSave(msg, question) : undefined
              }
              saved={isSaved(m.id)}
            />
          );
        })}
        <div ref={endRef} />
      </div>
    </div>
  );
}
