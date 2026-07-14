"""
build_kb.py — rebuild backend/data/chunks_merged.jsonl from the PDFs in
Documents/ (registry-driven, see doc_registry.py).

    pip install -r ingest/requirements.txt
    python ingest/build_kb.py                       # full build
    python ingest/build_kb.py --only <doc_id>       # single-doc dry run
    python ingest/build_kb.py --no-strict           # don't fail on canaries

Run ingest/ocr_gemini.py first (needs GEMINI_API_KEY) so scanned circulars and
diagram-only pages are included via the OCR cache; the build report lists any
pages still lacking OCR. After a full build, regenerate embeddings
(backend/generate_embeddings.py) and commit BOTH artifacts together.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

from doc_registry import REGISTRY, pdf_path
from parse_pdf import extract
from chunker import chunk_document
from tagger import tag_chunk

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_OUT = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "backend", "data", "chunks_merged.jsonl"))

# Hard canaries fail the build; soft canaries only warn. "K05"/"off delay" are
# soft: verified absent from all 10 source PDFs (text AND OCR'd diagrams) —
# K-designations come from wiring schematics not included in Documents/.
# Query-side aliasing (voice_text.ABBREVIATIONS) covers them instead.
HARD_CANARIES = {
    "failure/fault code": re.compile(r"\b(failure|fault)\s*codes?\b", re.I),
    "data download": re.compile(r"\bdata\s+download\b", re.I),
    "timer relay": re.compile(r"\btimer\s+relay\b", re.I),
}
SOFT_CANARIES = {
    "K05": re.compile(r"\bK[\s\-]?05\b", re.I),
    "off delay": re.compile(r"\boff[\s\-]?delay\b", re.I),
}
MIN_TOTAL_CHUNKS = 600


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="build a single doc_id (dry run, not written unless --out given)")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--no-strict", action="store_true",
                    help="report canary failures without exiting nonzero")
    args = ap.parse_args()

    entries = [e for e in REGISTRY if not args.only or e["doc_id"] == args.only]
    if not entries:
        raise SystemExit(f"no registry entry matches --only {args.only}")

    all_chunks = []
    ocr_pending = {}
    print("=" * 72)
    for entry in entries:
        path = pdf_path(entry)
        if not os.path.exists(path):
            print(f"!! MISSING PDF: {path}")
            continue
        sections, page_stats = extract(path, entry)
        chunks = chunk_document(sections, entry, tag_chunk)
        all_chunks.extend(chunks)

        chars = sum(c["char_count"] for c in chunks)
        need = [s["page"] for s in page_stats if s["needs_ocr"]]
        weak_unocr = [s["page"] for s in page_stats
                      if s["chars"] < 300 and s["big_images"] and not s["ocr_merged"]]
        merged = sum(1 for s in page_stats if s["ocr_merged"])
        if weak_unocr:
            ocr_pending[entry["doc_id"]] = weak_unocr
        print(f"{entry['doc_id']}: {len(chunks)} chunks, {chars} chars, "
              f"{len(sections)} sections, OCR merged on {merged} pages")
        if weak_unocr:
            print(f"    pages needing OCR (run ingest/ocr_gemini.py): {weak_unocr}")

    print("=" * 72)
    print(f"TOTAL: {len(all_chunks)} chunks "
          f"(avg {sum(c['char_count'] for c in all_chunks)//max(len(all_chunks),1)} chars)")
    tag_hist = Counter(t for c in all_chunks for t in c["tags"])
    oem_hist = Counter(c["oem"] for c in all_chunks if c["oem"])
    print(f"tags: {tag_hist.most_common(25)}")
    print(f"OEMs: {dict(oem_hist)}")

    full_build = not args.only
    failures = []
    joined = "\n".join(c["text"] for c in all_chunks)
    for name, pat in HARD_CANARIES.items():
        n = len(pat.findall(joined))
        print(f"canary '{name}': {n} hits")
        if n == 0:
            failures.append(name)
    for name, pat in SOFT_CANARIES.items():
        n = len(pat.findall(joined))
        print(f"canary '{name}' (soft): {n} hits" + (" — WARNING" if n == 0 else ""))
    if full_build and len(all_chunks) < MIN_TOTAL_CHUNKS:
        failures.append(f"total chunks {len(all_chunks)} < {MIN_TOTAL_CHUNKS}")

    if full_build or args.out != DEFAULT_OUT:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            for c in all_chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        print(f"wrote {args.out}")
        print("NOTE: embeddings.npy is now stale — rerun backend/generate_embeddings.py "
              "and commit both files together.")
    else:
        print("(dry run --only: JSONL not written)")

    if failures:
        print(f"CANARY/SIZE FAILURES: {failures}")
        if ocr_pending:
            print("Hint: unresolved OCR pages above may contain the missing terms.")
        if not args.no_strict and full_build:
            sys.exit(1)


if __name__ == "__main__":
    main()
