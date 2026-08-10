"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { Download, FileText, Loader2, Search, X } from "lucide-react";
import { fetchDocuments } from "@/lib/api";
import type { DocumentInfo } from "@/lib/types";

/**
 * The reference shelf.
 *
 * Every source PDF is already on R2 and every chunk already carries its URL,
 * but until now the only way to reach a document was to ask a question that
 * happened to retrieve it. A depot technician often knows exactly which letter
 * they want — this is the direct route to all 97 of them.
 */

function fmtDate(iso: string): string {
  if (!iso) return "";
  const p = iso.split("-");
  if (p.length === 3) return `${p[2]}.${p[1]}.${p[0]}`;
  if (p.length === 2) return `${p[1]}.${p[0]}`;
  return iso;
}

type Filter = { key: string; label: string };

export default function ReferenceLibrary({ onClose }: { onClose: () => void }) {
  const [docs, setDocs] = useState<DocumentInfo[] | null>(null);
  const [q, setQ] = useState("");
  const [coach, setCoach] = useState("");
  const [type, setType] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchDocuments().then(setDocs);
  }, []);

  useEffect(() => {
    searchRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const coaches: Filter[] = useMemo(() => {
    const set = new Set<string>();
    (docs || []).forEach((d) => d.coach_type.forEach((c) => c && set.add(c)));
    return [...set].sort().map((c) => ({
      key: c,
      label: c === "common" ? "All-IR" : c,
    }));
  }, [docs]);

  const types: Filter[] = useMemo(() => {
    const m = new Map<string, string>();
    (docs || []).forEach((d) => d.doc_type && m.set(d.doc_type, d.doc_type_label));
    return [...m].map(([key, label]) => ({ key, label })).sort((a, b) =>
      a.label.localeCompare(b.label)
    );
  }, [docs]);

  const shown = useMemo(() => {
    if (!docs) return [];
    const needle = q.trim().toLowerCase();
    return docs.filter((d) => {
      if (coach && !d.coach_type.includes(coach)) return false;
      if (type && d.doc_type !== type) return false;
      if (!needle) return true;
      return (
        d.title.toLowerCase().includes(needle) ||
        d.letter_no.toLowerCase().includes(needle) ||
        d.subsystem.toLowerCase().includes(needle) ||
        d.oem.toLowerCase().includes(needle)
      );
    });
  }, [docs, q, coach, type]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-stretch justify-center bg-bg-base/70 backdrop-blur-sm sm:items-center sm:p-6"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Reference library"
        className="flex h-full w-full flex-col overflow-hidden border-line/15 bg-bg-panel shadow-rail sm:h-[min(85vh,880px)] sm:max-w-3xl sm:rounded-2xl sm:border"
      >
        <header className="shrink-0 border-b border-line/12 px-4 pb-3 pt-[calc(env(safe-area-inset-top,0px)+0.85rem)] sm:pt-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-[0.98rem] font-bold text-ink">Reference library</h2>
              <p className="text-[0.76rem] text-ink-dim">
                {docs === null
                  ? "Loading documents…"
                  : `${shown.length} of ${docs.length} documents`}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close reference library"
              className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-line/15 text-ink-dim transition hover:text-accent active:scale-95"
            >
              <X size={18} aria-hidden />
            </button>
          </div>

          <div className="mt-3 flex items-center gap-2 rounded-xl border border-line/15 bg-bg-card px-3">
            <Search size={16} className="shrink-0 text-ink-faint" aria-hidden />
            <input
              ref={searchRef}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              type="search"
              placeholder="Search title, letter no., OEM…"
              aria-label="Search documents"
              className="min-w-0 flex-1 bg-transparent py-2.5 text-[0.92rem] text-ink placeholder:text-ink-faint focus:outline-none"
            />
          </div>

          {docs !== null && (
            <div className="scroll-area -mx-1 mt-2 flex gap-1.5 overflow-x-auto px-1 pb-1">
              <Chip active={!coach && !type} onClick={() => { setCoach(""); setType(""); }}>
                All
              </Chip>
              {coaches.map((c) => (
                <Chip
                  key={c.key}
                  active={coach === c.key}
                  onClick={() => setCoach(coach === c.key ? "" : c.key)}
                >
                  {c.label}
                </Chip>
              ))}
              <span className="mx-0.5 w-px shrink-0 self-stretch bg-line/20" />
              {types.map((t) => (
                <Chip
                  key={t.key}
                  active={type === t.key}
                  onClick={() => setType(type === t.key ? "" : t.key)}
                >
                  {t.label}
                </Chip>
              ))}
            </div>
          )}
        </header>

        <div className="scroll-area flex-1 overflow-y-auto px-4 py-3">
          {docs === null && (
            <p className="flex items-center justify-center gap-2 py-12 text-[0.85rem] text-ink-dim">
              <Loader2 size={16} className="animate-spin" aria-hidden />
              Fetching the document list — the server may be waking up.
            </p>
          )}
          {docs !== null && docs.length === 0 && (
            <p className="py-12 text-center text-[0.85rem] text-ink-dim">
              Could not reach the server. Check your connection and reopen.
            </p>
          )}
          {docs !== null && docs.length > 0 && shown.length === 0 && (
            <p className="py-12 text-center text-[0.85rem] text-ink-dim">
              No document matches those filters.
            </p>
          )}
          <ul className="flex flex-col gap-2">
            {shown.map((d) => {
              const Tag = d.download_url ? "a" : "div";
              return (
                <li key={d.doc_id}>
                  <Tag
                    {...(d.download_url
                      ? { href: d.download_url, target: "_blank", rel: "noopener noreferrer" }
                      : {})}
                    className={`group flex gap-3 rounded-xl border border-line/15 bg-bg-card p-3 transition ${
                      d.download_url ? "hover:border-accent/50 hover:bg-accent/5" : ""
                    }`}
                  >
                    <FileText size={16} className="mt-0.5 shrink-0 text-accent" aria-hidden />
                    <div className="min-w-0 flex-1">
                      <p className="text-[0.88rem] font-semibold leading-snug text-ink">
                        {d.title}
                      </p>
                      <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.72rem] text-ink-faint">
                        <span className="rounded border border-line/20 px-1.5 py-px font-medium">
                          {d.doc_type_label}
                        </span>
                        {d.coach_type
                          .filter(Boolean)
                          .map((c) => (
                            <span key={c} className="rounded border border-line/20 px-1.5 py-px font-medium">
                              {c === "common" ? "All-IR" : c}
                            </span>
                          ))}
                        {d.oem && <span>{d.oem}</span>}
                        {d.letter_no && <span>{d.letter_no}</span>}
                        {d.issue_date && <span>dt. {fmtDate(d.issue_date)}</span>}
                        <span>{d.pages || d.chunks} pp.</span>
                      </p>
                    </div>
                    {d.download_url && (
                      <Download
                        size={15}
                        className="mt-0.5 shrink-0 text-ink-faint transition group-hover:text-accent"
                        aria-label={`Open ${d.title}`}
                      />
                    )}
                  </Tag>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`shrink-0 whitespace-nowrap rounded-full border px-2.5 py-1 text-[0.74rem] font-medium transition ${
        active
          ? "border-accent/60 bg-accent/12 text-accent"
          : "border-line/15 bg-bg-card text-ink-dim hover:border-accent/40 hover:text-accent"
      }`}
    >
      {children}
    </button>
  );
}
