"use client";
import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";
import type { Message } from "@/lib/types";

export default function Chat({
  messages,
  onReplay,
}: {
  messages: Message[];
  onReplay: (m: Message) => void;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to latest on every new message — no fixed-height jank.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center px-8 text-center">
        <div className="mb-4 grid h-16 w-16 place-items-center rounded-2xl bg-gradient-to-br from-accent/20 to-accent-violet/20 shadow-glow">
          <span className="text-3xl">🛠️</span>
        </div>
        <h2 className="text-base font-semibold text-ink">How can I help?</h2>
        <p className="mt-1 max-w-xs text-sm text-ink-dim">
          Ask about FSDS, FDSS or WSP — fault codes, test procedures,
          maintenance schedules. Type or tap the mic. Hindi & English supported.
        </p>
      </div>
    );
  }

  return (
    <div className="scroll-area flex-1 overflow-y-auto px-3 py-4">
      <div className="mx-auto flex max-w-2xl flex-col gap-3">
        {messages.map((m) => (
          <MessageBubble
            key={m.id}
            msg={m}
            onReplay={m.role === "assistant" ? onReplay : undefined}
          />
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}
