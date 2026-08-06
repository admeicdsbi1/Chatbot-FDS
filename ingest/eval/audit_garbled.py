"""
audit_garbled.py — find chunks whose text is mojibake (corrupted-font PDF
extraction), so those docs can be flagged force_ocr in doc_registry. No API.

    python ingest/eval/audit_garbled.py

Heuristic: a PROSE chunk (not a markdown table) with many alpha tokens but almost
no common English stopwords is almost certainly garbled. Tables and bilingual /
address / list slides are deliberately excluded to avoid false positives.
"""
import json, os, re, sys
from collections import defaultdict

# The heuristic itself lives in parse_pdf, because ingestion applies it per PAGE
# (to decide whether OCR should replace a page's text layer) and this audit
# applies the same test per CHUNK. One definition, two callers.
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))
from parse_pdf import STOP_MIN, stopword_ratio as score  # noqa: E402,F401

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..",
                                   "backend", "data", "chunks_merged.jsonl"))


def main():
    chunks = [json.loads(l) for l in open(CH, encoding="utf-8") if l.strip()]
    by_doc = defaultdict(lambda: [0, 0])
    flagged = []
    for c in chunks:
        r = score(c.get("text", ""))
        if r is None:
            continue
        by_doc[c["doc_id"]][1] += 1
        if r < STOP_MIN:
            by_doc[c["doc_id"]][0] += 1
            flagged.append((r, c["doc_id"], c.get("page_num"),
                            re.sub(r"\s+", " ", c.get("text", ""))[:100]))

    print("=== docs with likely-garbled prose chunks (garbled / prose-judged) ===")
    for doc, (g, t) in sorted(by_doc.items(), key=lambda x: -x[1][0]):
        if g:
            print(f"  {g:3}/{t:3}  {doc}")
    print("\n=== flagged chunks (verify before setting force_ocr) ===")
    for r, doc, pg, prev in sorted(flagged):
        print(f"  stop={r:.3f}  {doc} p{pg}\n      {prev}")


if __name__ == "__main__":
    main()
