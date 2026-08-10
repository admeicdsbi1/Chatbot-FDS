"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import AppShell from "@/components/AppShell";
import Header from "@/components/Header";
import Rail from "@/components/Rail";
import Chat from "@/components/Chat";
import Composer from "@/components/Composer";
import ThinkingPipeline from "@/components/ThinkingPipeline";
import Disambiguation from "@/components/Disambiguation";
import ReferenceLibrary from "@/components/ReferenceLibrary";
import SavedPanel from "@/components/SavedPanel";
import { ApiError, fetchHealth, sendChat, transcribe } from "@/lib/api";
import { speak, stopSpeaking, isTTSSupported } from "@/lib/tts";
import {
  loadActiveThreadId,
  loadSaved,
  loadScope,
  loadThreads,
  persistSaved,
  saveActiveThreadId,
  saveScope,
  saveThreads,
  threadTitle,
  upsertThread,
} from "@/lib/storage";
import type {
  CoachScope,
  Message,
  SavedAnswer,
  Stage,
  Thread,
} from "@/lib/types";

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

  const [threads, setThreads] = useState<Thread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [saved, setSaved] = useState<SavedAnswer[]>([]);
  const [scope, setScope] = useState<CoachScope>("");
  const [railOpen, setRailOpen] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [savedOpen, setSavedOpen] = useState(false);
  const [kbLabel, setKbLabel] = useState("Coach maintenance knowledge base");

  const busy = stage !== "idle";
  const messagesRef = useRef<Message[]>([]);
  messagesRef.current = messages;
  const abortRef = useRef<AbortController | null>(null);
  const hydrated = useRef(false);

  // ---- restore from the device ----
  useEffect(() => {
    const t = loadThreads();
    setThreads(t);
    setSaved(loadSaved());
    setScope(loadScope());
    const activeId = loadActiveThreadId();
    const active = activeId ? t.find((x) => x.id === activeId) : undefined;
    if (active) {
      setMessages(active.messages);
      setActiveThreadId(active.id);
    }
    hydrated.current = true;
  }, []);

  useEffect(() => {
    fetchHealth().then((h) => {
      if (h?.chunks) {
        setKbLabel(
          `${h.documents ?? "—"} documents · ${h.chunks.toLocaleString()} passages`
        );
      }
    });
  }, []);

  // ---- persist the conversation as it grows ----
  useEffect(() => {
    if (!hydrated.current || messages.length === 0) return;
    const id = activeThreadId || uid();
    if (!activeThreadId) {
      setActiveThreadId(id);
      saveActiveThreadId(id);
    }
    setThreads((prev) => {
      const existing = prev.find((t) => t.id === id);
      const next = upsertThread(prev, {
        id,
        title: threadTitle(messages),
        createdAt: existing?.createdAt ?? Date.now(),
        updatedAt: Date.now(),
        messages,
      });
      saveThreads(next);
      return next;
    });
  }, [messages, activeThreadId]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const ask = useCallback(
    async (questionRaw: string) => {
      const question = questionRaw.trim();
      if (!question || busy) return;
      setDisamb(null);
      setInput("");
      setRailOpen(false);
      stopSpeaking();

      const userMsg: Message = {
        id: uid(),
        role: "user",
        content: question,
        ts: Date.now(),
      };
      setMessages((m) => [...m, userMsg]);

      const ctrl = new AbortController();
      abortRef.current = ctrl;
      try {
        const history = messagesRef.current; // prior turns for context
        setStage("searching");
        const res = await sendChat(question, history, scope, ctrl.signal);
        setStage("generating");

        const botMsg: Message = {
          id: uid(),
          role: "assistant",
          content: res.answer,
          sources: res.sources || undefined,
          sourcesList: res.sources_list?.length ? res.sources_list : undefined,
          lang: res.lang,
          retrievalCount: res.retrieval_count,
          retrievalMode: res.retrieval_mode,
          valuesSuppressed: res.values_suppressed,
          clarify: res.clarify,
          ts: Date.now(),
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
          {
            id: uid(),
            role: "assistant",
            content: chatErrorMessage(e),
            ts: Date.now(),
          },
        ]);
      } finally {
        abortRef.current = null;
        setStage("idle");
      }
    },
    [busy, voiceOn, scope]
  );

  const handleAudio = useCallback(async (blob: Blob) => {
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
            ts: Date.now(),
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
          ts: Date.now(),
        },
      ]);
    } finally {
      setStage("idle");
    }
  }, []);

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

  // ---- threads ----
  const newThread = useCallback(() => {
    stopSpeaking();
    setMessages([]);
    setActiveThreadId(null);
    saveActiveThreadId(null);
    setDisamb(null);
    setInput("");
    setRailOpen(false);
  }, []);

  const openThread = useCallback(
    (id: string) => {
      const t = threads.find((x) => x.id === id);
      if (!t) return;
      stopSpeaking();
      setMessages(t.messages);
      setActiveThreadId(id);
      saveActiveThreadId(id);
      setRailOpen(false);
    },
    [threads]
  );

  const deleteThread = useCallback(
    (id: string) => {
      setThreads((prev) => {
        const next = prev.filter((t) => t.id !== id);
        saveThreads(next);
        return next;
      });
      if (id === activeThreadId) {
        setMessages([]);
        setActiveThreadId(null);
        saveActiveThreadId(null);
      }
    },
    [activeThreadId]
  );

  // ---- saved answers ----
  const toggleSave = useCallback((m: Message, question: string) => {
    setSaved((prev) => {
      const exists = prev.some((s) => s.id === m.id);
      const next = exists
        ? prev.filter((s) => s.id !== m.id)
        : [
            {
              id: m.id,
              question: question || threadTitle([m]),
              answer: m.content,
              sourcesList: m.sourcesList,
              savedAt: Date.now(),
            },
            ...prev,
          ];
      persistSaved(next);
      return next;
    });
  }, []);

  const removeSaved = useCallback((id: string) => {
    setSaved((prev) => {
      const next = prev.filter((s) => s.id !== id);
      persistSaved(next);
      return next;
    });
  }, []);

  const isSaved = useCallback(
    (id: string) => saved.some((s) => s.id === id),
    [saved]
  );

  const changeScope = useCallback((s: CoachScope) => {
    setScope(s);
    saveScope(s);
  }, []);

  // ---- keyboard shortcuts ----
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setLibraryOpen(true);
        return;
      }
      if (e.key === "Escape" && busy) stop();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, stop]);

  const rail = (
    <Rail
      threads={threads}
      activeThreadId={activeThreadId}
      saved={saved}
      scope={scope}
      onScope={changeScope}
      onNewThread={newThread}
      onOpenThread={openThread}
      onDeleteThread={deleteThread}
      onOpenLibrary={() => {
        setLibraryOpen(true);
        setRailOpen(false);
      }}
      onOpenSaved={() => {
        setSavedOpen(true);
        setRailOpen(false);
      }}
    />
  );

  return (
    <AppShell rail={rail} railOpen={railOpen} onCloseRail={() => setRailOpen(false)}>
      <Header
        voiceOn={voiceOn}
        onToggleVoice={toggleVoice}
        onOpenRail={() => setRailOpen(true)}
        scope={scope}
        onScope={changeScope}
        kbLabel={kbLabel}
      />

      <Chat
        messages={messages}
        onReplay={replay}
        onPickQuestion={(q) => ask(q)}
        onToggleSave={toggleSave}
        isSaved={isSaved}
      />

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

        <Composer
          value={input}
          onChange={setInput}
          onSubmit={() => ask(input)}
          onAudio={handleAudio}
          busy={busy}
          onStop={stop}
        />
      </div>

      {libraryOpen && <ReferenceLibrary onClose={() => setLibraryOpen(false)} />}
      {savedOpen && (
        <SavedPanel
          items={saved}
          onRemove={removeSaved}
          onClose={() => setSavedOpen(false)}
        />
      )}
    </AppShell>
  );
}
