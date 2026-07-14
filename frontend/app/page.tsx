"use client";
import { useCallback, useRef, useState } from "react";
import Header from "@/components/Header";
import Chat from "@/components/Chat";
import Composer from "@/components/Composer";
import ThinkingPipeline from "@/components/ThinkingPipeline";
import Disambiguation from "@/components/Disambiguation";
import QuickQuestions from "@/components/QuickQuestions";
import { ApiError, sendChat, transcribe } from "@/lib/api";
import { speak, stopSpeaking, isTTSSupported } from "@/lib/tts";
import type { Message, Stage } from "@/lib/types";

function uid() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function chatErrorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    switch (e.kind) {
      case "timeout":
        return "⚠️ Server took too long to respond — it may be waking up from sleep. Please try again in a minute.";
      case "network":
        return "⚠️ No connection to the server. Check your internet and try again.";
      case "server":
        return "⚠️ Server error while answering. Please try again.";
      case "http":
        return `⚠️ Request failed (${e.status ?? "error"}). Please try again.`;
      case "cancelled":
        return "Request stopped.";
    }
  }
  return "⚠️ Could not reach the server. Check your connection and try again.";
}

interface Disamb {
  heard: string;
  alternatives: string[];
}

export default function Page() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [stage, setStage] = useState<Stage>("idle");
  const [voiceOn, setVoiceOn] = useState(isTTSSupported());
  const [disamb, setDisamb] = useState<Disamb | null>(null);
  const busy = stage !== "idle";
  const messagesRef = useRef<Message[]>([]);
  messagesRef.current = messages;
  const abortRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const ask = useCallback(
    async (questionRaw: string) => {
      const question = questionRaw.trim();
      if (!question || busy) return;
      setDisamb(null);
      setInput("");
      stopSpeaking();

      const userMsg: Message = { id: uid(), role: "user", content: question };
      setMessages((m) => [...m, userMsg]);

      const ctrl = new AbortController();
      abortRef.current = ctrl;
      try {
        const history = messagesRef.current; // prior turns for context
        setStage("searching");
        const res = await sendChat(question, history, ctrl.signal);
        setStage("generating");

        const degraded =
          res.retrieval_mode === "keyword-only"
            ? "\n\n_⚠️ Search is running in reduced mode right now — answers may be less accurate._"
            : "";
        const botMsg: Message = {
          id: uid(),
          role: "assistant",
          content: res.answer + degraded,
          sources: res.sources || undefined,
          lang: res.lang,
        };
        setMessages((m) => [...m, botMsg]);

        if (voiceOn && res.answer && !res.answer.startsWith("⚠️")) {
          setStage("speaking");
          speak(res.answer, res.lang);
        }
      } catch (e) {
        console.error("chat failed:", e);
        setMessages((m) => [
          ...m,
          { id: uid(), role: "assistant", content: chatErrorMessage(e) },
        ]);
      } finally {
        abortRef.current = null;
        setStage("idle");
      }
    },
    [busy, voiceOn]
  );

  const handleAudio = useCallback(
    async (blob: Blob) => {
      setDisamb(null);
      setStage("transcribing");
      try {
        const res = await transcribe(blob);
        if (!res.text) {
          setMessages((m) => [
            ...m,
            {
              id: uid(),
              role: "assistant",
              content:
                "⚠️ Could not understand the audio. Speak clearly close to the mic, or type your question.",
            },
          ]);
          return;
        }
        if (res.confidence >= 0.55) {
          // Confident → drop into the box for one-tap confirm/edit.
          setInput(res.text);
        } else {
          setDisamb({ heard: res.text, alternatives: res.alternatives || [] });
          setInput(res.text);
        }
      } catch {
        setMessages((m) => [
          ...m,
          {
            id: uid(),
            role: "assistant",
            content: "⚠️ Voice service unavailable. Please type your question.",
          },
        ]);
      } finally {
        setStage("idle");
      }
    },
    []
  );

  const replay = useCallback(
    (m: Message) => {
      if (!voiceOn) setVoiceOn(true);
      speak(m.content, m.lang || "en");
    },
    [voiceOn]
  );

  const toggleVoice = useCallback(() => {
    setVoiceOn((v) => {
      if (v) stopSpeaking();
      return !v;
    });
  }, []);

  return (
    <div className="mx-auto flex h-[100dvh] max-w-2xl flex-col">
      <Header voiceOn={voiceOn} onToggleVoice={toggleVoice} />

      <Chat messages={messages} onReplay={replay} />

      <div className="flex flex-col gap-2">
        <ThinkingPipeline stage={stage} />

        {disamb && (
          <Disambiguation
            heard={disamb.heard}
            alternatives={disamb.alternatives}
            onPick={(t) => {
              setInput(t);
              setDisamb(null);
            }}
          />
        )}

        {messages.length === 0 && !disamb && (
          <QuickQuestions onPick={(q) => ask(q)} />
        )}

        <Composer
          value={input}
          onChange={setInput}
          onSubmit={() => ask(input)}
          onAudio={handleAudio}
          busy={busy}
          onStop={stop}
        />
      </div>
    </div>
  );
}
