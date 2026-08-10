"use client";
import { useMemo } from "react";
import { AlertTriangle, BookMarked, ListOrdered } from "lucide-react";
import Markdown from "./Markdown";

/**
 * The answer prompt already asks for four labelled sections (Direct Answer /
 * Step-by-step Action / Safety Caution / Reference). Until now they rendered as
 * four bold paragraphs, so a safety warning looked exactly like a heading.
 *
 * This splits them out and gives each the weight it deserves — most importantly
 * the safety caution, which becomes an amber callout a technician can spot
 * while scrolling. If the shape is not found (the model may translate the
 * labels in Hindi mode, or drop them on a short answer) we render the answer
 * verbatim as plain markdown, so nothing is ever hidden.
 */

type Kind = "answer" | "steps" | "safety" | "reference";

const LABELS: { re: RegExp; kind: Kind }[] = [
  { re: /^direct answer$/i, kind: "answer" },
  { re: /^(step[- ]by[- ]step(?: action)?|steps?|action)$/i, kind: "steps" },
  { re: /^(safety(?: caution| warning)?|caution)$/i, kind: "safety" },
  { re: /^(references?|source)$/i, kind: "reference" },
];

// A section header the model emits, e.g. "**Direct Answer:**" at the start of a
// line, optionally preceded by a markdown heading marker.
const HEADER_RE =
  /^[ \t]*(?:#{1,4}[ \t]*)?\*\*[ \t]*([A-Za-z][A-Za-z \-]{2,30}?)[ \t]*:?[ \t]*\*\*[ \t]*:?/gm;

interface Section {
  kind: Kind;
  body: string;
}

function parse(md: string): Section[] | null {
  const found: { kind: Kind; start: number; end: number }[] = [];
  HEADER_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = HEADER_RE.exec(md)) !== null) {
    const label = m[1].trim();
    const hit = LABELS.find((l) => l.re.test(label));
    if (hit) found.push({ kind: hit.kind, start: m.index, end: m.index + m[0].length });
  }
  // One lone header is more likely a coincidence than the intended format.
  if (found.length < 2) return null;

  const sections: Section[] = [];
  // Anything before the first header (rare) is kept as a lead paragraph.
  const preamble = md.slice(0, found[0].start).trim();
  if (preamble) sections.push({ kind: "answer", body: preamble });

  found.forEach((f, i) => {
    const stop = i + 1 < found.length ? found[i + 1].start : md.length;
    const body = md.slice(f.end, stop).trim();
    if (body) sections.push({ kind: f.kind, body });
  });
  return sections.length ? sections : null;
}

function Steps({ body }: { body: string }) {
  return (
    <section className="mt-3">
      <h3 className="mb-1.5 flex items-center gap-1.5 text-[0.7rem] font-bold uppercase tracking-wider text-ink-dim">
        <ListOrdered size={13} aria-hidden /> Step-by-step
      </h3>
      <Markdown>{body}</Markdown>
    </section>
  );
}

function Safety({ body }: { body: string }) {
  return (
    <section
      className="mt-3 rounded-xl border border-accent-amber/45 bg-accent-amber/10 px-3 py-2.5"
      role="note"
    >
      <h3 className="mb-1 flex items-center gap-1.5 text-[0.72rem] font-bold uppercase tracking-wider text-accent-amber">
        <AlertTriangle size={14} aria-hidden /> Safety caution
      </h3>
      <div className="[&_p]:text-ink">
        <Markdown>{body}</Markdown>
      </div>
    </section>
  );
}

function Reference({ body }: { body: string }) {
  return (
    <section className="mt-3 border-t border-line/15 pt-2">
      <h3 className="mb-1 flex items-center gap-1.5 text-[0.7rem] font-bold uppercase tracking-wider text-ink-dim">
        <BookMarked size={13} aria-hidden /> Reference
      </h3>
      <div className="text-[0.82rem] text-ink-dim">
        <Markdown>{body}</Markdown>
      </div>
    </section>
  );
}

export default function AnswerBody({ content }: { content: string }) {
  const sections = useMemo(() => parse(content), [content]);

  if (!sections) {
    return (
      <div className="answer-md">
        <Markdown>{content}</Markdown>
      </div>
    );
  }

  return (
    <div className="answer-md">
      {sections.map((s, i) => {
        if (s.kind === "safety") return <Safety key={i} body={s.body} />;
        if (s.kind === "steps") return <Steps key={i} body={s.body} />;
        if (s.kind === "reference") return <Reference key={i} body={s.body} />;
        return (
          <div key={i} className="text-[0.97rem] leading-relaxed">
            <Markdown>{s.body}</Markdown>
          </div>
        );
      })}
    </div>
  );
}
