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
import load_env  # noqa: F401  — must precede doc_registry (reads PDF_BUCKET_BASE at import)

import argparse
import json
import os
import re
import sys
from collections import Counter

from doc_registry import REGISTRY, pdf_path, full, download_url
from parse_pdf import extract
from chunker import chunk_document
from tagger import tag_chunk

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_OUT = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "backend", "data", "chunks_merged.jsonl"))

# Per-system HARD canaries — only enforced when a document of that `system` is
# in the build, so adding a new manual family never fails on another system's
# terms. Extend this dict when a new subsystem (brakes, bogie, electrical…) is
# ingested so a silent extraction failure on that manual is caught early.
SYSTEM_HARD_CANARIES = {
    "FSDS": {
        "failure/fault code": re.compile(r"\b(failure|fault)\s*codes?\b", re.I),
        "data download": re.compile(r"\bdata\s+download\b", re.I),
    },
    "WSP": {
        "timer relay": re.compile(r"\btimer\s+relay\b", re.I),
        "dump/anti-skid valve": re.compile(r"\bdump\s+valve\b|\banti[- ]?skid\b", re.I),
    },
    "VB": {
        "CTRB": re.compile(r"\bCTRB\b", re.I),
        "Vande Bharat": re.compile(r"\bvande\s*bharat\b", re.I),
    },
}
# Soft canaries only warn. "K05"/"off delay" are soft: verified absent from all
# source PDFs (text AND OCR'd diagrams) — K-designations come from wiring
# schematics not in Documents/; query-side aliasing covers them instead.
SOFT_CANARIES = {
    "K05": re.compile(r"\bK[\s\-]?05\b", re.I),
    "off delay": re.compile(r"\boff[\s\-]?delay\b", re.I),
}
MIN_TOTAL_CHUNKS = 2400   # ~2545 after VB waves 1-3 (wheels/bearings, schedules/SMI, CAI)


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
        # complete schema (defaults) + resolve the source-PDF download link so
        # every chunk carries it (empty when PDF_BUCKET_BASE is unset).
        entry = full(entry)
        entry["download_url"] = download_url(entry)
        path = pdf_path(entry)
        if not os.path.exists(path):
            print(f"!! MISSING PDF: {path}")
            continue
        sections, page_stats = extract(path, entry)
        chunks = chunk_document(sections, entry, tag_chunk)
        all_chunks.extend(chunks)

        chars = sum(c["char_count"] for c in chunks)
        weak_unocr = [s["page"] for s in page_stats
                      if s["chars"] < 300 and s["big_images"] and not s["ocr_merged"]]
        # Scanner-OCR / mojibake pages not yet OCR'd are the dangerous ones:
        # unlike a blank scan they contribute text, so they land in the KB
        # looking perfectly valid.
        # Only pages OCR has never seen are actionable. A page OCR examined and
        # declared [UNREADABLE] (photo/drawing, no text) has nothing better
        # available, so re-reporting it every build is noise that hides real gaps.
        suspect_unocr = [s["page"] for s in page_stats
                         if s.get("suspect_layer") and not s["ocr_merged"]
                         and not s.get("ocr_attempted")]
        merged = sum(1 for s in page_stats if s["ocr_merged"])
        pending = sorted(set(weak_unocr) | set(suspect_unocr))
        if pending:
            ocr_pending[entry["doc_id"]] = pending
        print(f"{entry['doc_id']}: {len(chunks)} chunks, {chars} chars, "
              f"{len(sections)} sections, OCR merged on {merged} pages")
        if pending:
            print(f"    pages needing OCR (run ingest/ocr_gemini.py): {pending}")
        if suspect_unocr:
            print(f"    !! untrusted text layer (scan/mojibake), still in KB: {suspect_unocr}")

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
    systems_present = {e.get("system") for e in entries}
    active_canaries = {}
    for sysname in systems_present:
        active_canaries.update(SYSTEM_HARD_CANARIES.get(sysname, {}))
    for name, pat in active_canaries.items():
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
