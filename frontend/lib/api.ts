import type {
  ChatResponse,
  CoachScope,
  DocumentInfo,
  HealthResponse,
  Message,
  SystemInfo,
  TranscribeResponse,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ||
  (process.env.NODE_ENV === "production" ? "" : "http://localhost:8000");

if (!API_BASE && typeof window !== "undefined") {
  // Fail fast in production instead of silently POSTing to localhost.
  console.error("NEXT_PUBLIC_API_BASE is not set — API calls will fail.");
}

export type ApiErrorKind = "timeout" | "cancelled" | "network" | "server" | "http";

export class ApiError extends Error {
  kind: ApiErrorKind;
  status?: number;
  constructor(kind: ApiErrorKind, message: string, status?: number) {
    super(message);
    this.kind = kind;
    this.status = status;
  }
}

// Render free tier can take ~50s to spin up from cold — allow for that.
const CHAT_TIMEOUT_MS = 75_000;

async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number,
  external?: AbortSignal
): Promise<Response> {
  const ctrl = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    ctrl.abort();
  }, timeoutMs);
  const onExternalAbort = () => ctrl.abort();
  external?.addEventListener("abort", onExternalAbort);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } catch (e) {
    if (ctrl.signal.aborted) {
      if (timedOut) throw new ApiError("timeout", "request timed out");
      throw new ApiError("cancelled", "request cancelled");
    }
    throw new ApiError("network", "network failure");
  } finally {
    clearTimeout(timer);
    external?.removeEventListener("abort", onExternalAbort);
  }
}

function checkStatus(res: Response, what: string) {
  if (res.ok) return;
  const kind: ApiErrorKind = res.status >= 500 ? "server" : "http";
  throw new ApiError(kind, `${what} failed: ${res.status}`, res.status);
}

/** Send a question plus recent history; returns the structured answer.
 *  `coach` is the UI scope chip — omitted when "all coaches", so the request is
 *  byte-identical to the previous version's in the default case. */
export async function sendChat(
  question: string,
  history: Message[],
  coach: CoachScope = "",
  signal?: AbortSignal
): Promise<ChatResponse> {
  const trimmed = history
    .filter((m) => m.content?.trim())
    .slice(-8)
    .map((m) => ({ role: m.role, content: m.content }));

  const res = await fetchWithTimeout(
    `${API_BASE}/api/chat`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        coach ? { question, history: trimmed, coach } : { question, history: trimmed }
      ),
    },
    CHAT_TIMEOUT_MS,
    signal
  );
  checkStatus(res, "chat");
  return res.json();
}

// Reference data is small (9 systems, 97 documents) and only changes on an
// ingest, so fetch it once per page load and reuse the promise.
let _systems: Promise<SystemInfo[]> | null = null;
let _documents: Promise<DocumentInfo[]> | null = null;

/** Maintenance areas with live counts. Empty array if the backend is asleep —
 *  the caller falls back to a static list rather than showing an error. */
export function fetchSystems(): Promise<SystemInfo[]> {
  if (!_systems) {
    _systems = fetchWithTimeout(`${API_BASE}/api/systems`, {}, 20_000)
      .then((r) => (r.ok ? r.json() : { systems: [] }))
      .then((d) => (Array.isArray(d.systems) ? d.systems : []))
      .catch(() => {
        _systems = null; // let a later attempt retry after a cold start
        return [];
      });
  }
  return _systems;
}

/** The reference shelf. */
export function fetchDocuments(): Promise<DocumentInfo[]> {
  if (!_documents) {
    _documents = fetchWithTimeout(`${API_BASE}/api/documents`, {}, 30_000)
      .then((r) => (r.ok ? r.json() : { documents: [] }))
      .then((d) => (Array.isArray(d.documents) ? d.documents : []))
      .catch(() => {
        _documents = null;
        return [];
      });
  }
  return _documents;
}

export async function fetchHealth(): Promise<HealthResponse | null> {
  try {
    const r = await fetchWithTimeout(`${API_BASE}/api/health`, {}, 20_000);
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

/** Thumbs up/down. Fire-and-forget: a failed rating must never surface as an
 *  error to someone who is trying to read an answer. */
export function sendFeedback(payload: {
  message_id: string;
  rating: "up" | "down";
  question?: string;
  answer_preview?: string;
  note?: string;
}): void {
  fetchWithTimeout(
    `${API_BASE}/api/feedback`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    15_000
  ).catch(() => {});
}

/** Upload recorded audio for transcription + confidence + alternatives. */
export async function transcribe(blob: Blob): Promise<TranscribeResponse> {
  const fd = new FormData();
  const ext = blob.type.includes("ogg") ? "ogg" : "webm";
  fd.append("audio", blob, `voice.${ext}`);
  const res = await fetchWithTimeout(
    `${API_BASE}/api/transcribe`,
    { method: "POST", body: fd },
    CHAT_TIMEOUT_MS
  );
  checkStatus(res, "transcribe");
  return res.json();
}

/** Optional server TTS (only used when browser SpeechSynthesis is off). */
export async function serverTTS(text: string, lang: string): Promise<string | null> {
  try {
    const res = await fetchWithTimeout(
      `${API_BASE}/api/tts`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, lang }),
      },
      30_000
    );
    if (!res.ok) return null;
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  } catch {
    return null;
  }
}

export { API_BASE };
