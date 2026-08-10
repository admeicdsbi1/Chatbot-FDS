export type Role = "user" | "assistant";

/** One citation row, as returned by the backend's `sources_list`. */
export interface SourceRef {
  doc_id: string;
  title: string;
  section: string;
  clause: string;
  page: number | string | null;
  letter_no: string;
  issue_date: string;
  date_label: string;
  ref: string;
  coach_type: string[];
  oem: string;
  /** R2 PDF, already deep-linked to the cited page (#page=N). */
  url: string;
}

export interface Message {
  id: string;
  role: Role;
  content: string;
  /** Markdown citation block — kept for backwards compatibility. */
  sources?: string;
  /** Structured citations; preferred when present. */
  sourcesList?: SourceRef[];
  lang?: string;
  retrievalCount?: number;
  retrievalMode?: string;
  /** Values the numeric guard withheld because they were not in the source. */
  valuesSuppressed?: number;
  clarify?: boolean;
  /** Epoch ms — used for history ordering and persistence. */
  ts?: number;
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
  sources_list?: SourceRef[];
  retrieval_count: number;
  lang: string;
  retrieval_mode?: string;
  values_suppressed?: number;
  clarify?: boolean;
}

export interface TranscribeResponse {
  text: string;
  lang: string;
  confidence: number;
  alternatives: string[];
  error?: string;
}

/** A maintenance area, with counts derived live from the KB. */
export interface SystemInfo {
  id: string;
  label: string;
  sublabel: string;
  icon: string;
  chunks: number;
  documents: number;
  questions: string[];
}

/** One source document on the reference shelf. */
export interface DocumentInfo {
  doc_id: string;
  title: string;
  coach_type: string[];
  subsystem: string;
  system: string | null;
  doc_type: string;
  doc_type_label: string;
  issue_date: string;
  letter_no: string;
  revision: string;
  oem: string;
  download_url: string;
  chunks: number;
  pages: number;
}

export interface HealthResponse {
  status: string;
  chunks: number;
  documents?: number;
  retrieval_mode: string;
  embedding_shape: number[] | null;
}

/** Coach scope chip. Empty string means "all coaches" (default behaviour). */
export type CoachScope = "" | "LHB" | "ICF" | "Vande Bharat" | "Amrit Bharat";

export const COACH_SCOPES: { value: CoachScope; label: string; short: string }[] = [
  { value: "", label: "All coaches", short: "All" },
  { value: "LHB", label: "LHB", short: "LHB" },
  { value: "ICF", label: "ICF", short: "ICF" },
  { value: "Vande Bharat", label: "Vande Bharat", short: "VB" },
  { value: "Amrit Bharat", label: "Amrit Bharat", short: "AB" },
];

export type Theme = "light" | "dark" | "system";

/** A saved conversation. */
export interface Thread {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: Message[];
}

/** A bookmarked answer, detached from its thread so deleting one keeps it. */
export interface SavedAnswer {
  id: string;
  question: string;
  answer: string;
  sourcesList?: SourceRef[];
  savedAt: number;
}
