import type { ChatResponse, Message, TranscribeResponse } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

/** Send a question plus recent history; returns the structured answer. */
export async function sendChat(
  question: string,
  history: Message[]
): Promise<ChatResponse> {
  const trimmed = history
    .filter((m) => m.content?.trim())
    .slice(-8)
    .map((m) => ({ role: m.role, content: m.content }));

  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history: trimmed }),
  });
  if (!res.ok) throw new Error(`chat failed: ${res.status}`);
  return res.json();
}

/** Upload recorded audio for transcription + confidence + alternatives. */
export async function transcribe(blob: Blob): Promise<TranscribeResponse> {
  const fd = new FormData();
  const ext = blob.type.includes("ogg") ? "ogg" : "webm";
  fd.append("audio", blob, `voice.${ext}`);
  const res = await fetch(`${API_BASE}/api/transcribe`, {
    method: "POST",
    body: fd,
  });
  if (!res.ok) throw new Error(`transcribe failed: ${res.status}`);
  return res.json();
}

/** Optional server TTS (only used when browser SpeechSynthesis is off). */
export async function serverTTS(text: string, lang: string): Promise<string | null> {
  const res = await fetch(`${API_BASE}/api/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, lang }),
  });
  if (!res.ok) return null;
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export { API_BASE };
