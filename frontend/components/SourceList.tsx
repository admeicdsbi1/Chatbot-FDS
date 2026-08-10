"use client";
import { FileText, Download } from "lucide-react";
import Markdown from "./Markdown";
import type { SourceRef } from "@/lib/types";

/**
 * Citations as scannable cards rather than one markdown blob.
 *
 * A maintenance user checks the source before acting on a value, so the things
 * that decide whether they trust it — which document, which clause, which page,
 * which letter number and date, which coach it applies to — each get their own
 * slot. The whole card is the link; the backend already deep-links it to the
 * cited page of the R2-hosted PDF.
 *
 * Falls back to the legacy markdown string when `sources_list` is absent, so an
 * answer restored from an older saved thread still renders.
 */
export default function SourceList({
  sources,
  sourcesList,
}: {
  sources?: string;
  sourcesList?: SourceRef[];
}) {
  if (sourcesList && sourcesList.length > 0) {
    return (
      <ul className="mt-2 flex flex-col gap-1.5">
        {sourcesList.map((s, i) => {
          const loc = [
            s.clause ? `Clause ${s.clause}` : "",
            s.section || "",
            s.page ? `p.${s.page}` : "",
          ]
            .filter(Boolean)
            .join(" · ");
          const Tag = s.url ? "a" : "div";
          return (
            <li key={`${s.doc_id}-${i}`}>
              <Tag
                {...(s.url
                  ? {
                      href: s.url,
                      target: "_blank",
                      rel: "noopener noreferrer",
                    }
                  : {})}
                className={`group flex gap-2.5 rounded-xl border border-line/15 bg-bg-sunken px-3 py-2 transition ${
                  s.url ? "hover:border-accent/50 hover:bg-accent/5" : ""
                }`}
              >
                <FileText
                  size={15}
                  className="mt-0.5 shrink-0 text-accent"
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <p className="text-[0.82rem] font-semibold leading-snug text-ink">
                    {s.title}
                  </p>
                  {loc && (
                    <p className="mt-0.5 text-[0.75rem] leading-snug text-ink-dim">
                      {loc}
                    </p>
                  )}
                  <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[0.72rem] text-ink-faint">
                    {s.ref && <span>{s.ref}</span>}
                    {s.coach_type
                      .filter((c) => c && c !== "common")
                      .map((c) => (
                        <span
                          key={c}
                          className="rounded border border-line/20 px-1 py-px text-[0.68rem] font-medium"
                        >
                          {c}
                        </span>
                      ))}
                    {s.oem && (
                      <span className="rounded border border-line/20 px-1 py-px text-[0.68rem] font-medium">
                        {s.oem}
                      </span>
                    )}
                  </p>
                </div>
                {s.url && (
                  <Download
                    size={14}
                    className="mt-0.5 shrink-0 text-ink-faint transition group-hover:text-accent"
                    aria-label="Open source PDF at the cited page"
                  />
                )}
              </Tag>
            </li>
          );
        })}
      </ul>
    );
  }

  if (!sources) return null;
  return (
    <div className="answer-md mt-2 rounded-xl border border-line/15 bg-bg-sunken px-3 py-2 text-[0.8rem] text-ink-dim">
      <Markdown>{sources}</Markdown>
    </div>
  );
}
