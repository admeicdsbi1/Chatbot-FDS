"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ExternalLink } from "lucide-react";
import type { Components } from "react-markdown";

/**
 * The one place answer markdown is rendered.
 *
 * Two overrides matter:
 *  - `table` is wrapped in its own horizontal scroller. 64% of KB chunks are
 *    markdown tables, so answers quote them constantly; without a wrapper a
 *    wide maintenance schedule pushed the whole page sideways on a phone.
 *  - `a` opens source PDFs in a new tab. The href already carries the R2
 *    `#page=N` deep link built by the backend.
 */
const components: Components = {
  table: ({ node, ...props }) => (
    <div className="md-table-wrap scroll-area" role="region" tabIndex={0} aria-label="Table — scroll sideways to see all columns">
      <table {...props} />
    </div>
  ),
  a: ({ href, children, node, ...props }) => {
    const external = !!href && /^https?:/i.test(href);
    return (
      <a
        href={href}
        target={external ? "_blank" : undefined}
        rel={external ? "noopener noreferrer" : undefined}
        className="text-accent-glow underline decoration-dotted underline-offset-2 hover:decoration-solid"
        {...props}
      >
        {children}
        {external && (
          <ExternalLink size={11} className="ml-0.5 inline-block opacity-70" aria-hidden />
        )}
      </a>
    );
  },
};

export default function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {children}
    </ReactMarkdown>
  );
}
