export type Role = "user" | "assistant";

export interface Message {
  id: string;
  role: Role;
  content: string;
  sources?: string;
  lang?: string;
}

export type Stage =
  | "idle"
  | "transcribing"
  | "understanding"
  | "searching"
  | "reading"
  | "generating"
  | "speaking";

export interface ChatResponse {
  answer: string;
  sources: string;
  retrieval_count: number;
  lang: string;
}

export interface TranscribeResponse {
  text: string;
  lang: string;
  confidence: number;
  alternatives: string[];
  error?: string;
}
