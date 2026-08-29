"""
verify_kb.py — schema *and corpus-property* validation of the committed KB.
Run before committing a rebuilt KB. Exits nonzero on any violation.

    python ingest/verify_kb.py

Costs no API quota and touches no PDF: it reads only the two committed
artifacts, so it can be run as often as you like. The corpus checks below exist
because each property was bought by a session of work and nothing was stopping
it silently regressing — see the comment on each for what it is protecting and
the measurement its bound came from (KB of 2026-08-19, 2,414 chunks / 97 docs).
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_DATA = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "backend", "data"))
JSONL = os.path.join(_DATA, "chunks_merged.jsonl")
EMBEDDINGS = os.path.join(_DATA, "embeddings.npy")

REQUIRED = ["chunk_id", "doc_id", "doc_type", "title", "source", "section",
            "section_num", "page_num", "chunk_index", "total_chunks_in_section",
            "tags", "oem", "text", "char_count"]
MAX_CHUNK_CHARS = 4000          # artifact ceiling; chunker.TABLE_MAX (2500) is the
                                # table budget. Highest chunk in this KB is 2,536,
                                # so prose legitimately sits between the two.

# ---- corpus-property bounds, each measured on the KB of 2026-08-19 -----------
MAX_COLN = 1200                 # unnamed-column placeholders. Was 2,702 before the
                                # header-repair pass, 1,554 after it, 962 today.
MAX_WORD_SPLIT_PIPES = 400      # prose gridded into a table: a `|` between two word
                                # characters. 300 today. This is the artifact-side
                                # proxy for parse_pdf's SHATTER_MAX, which only
                                # exists during the build.
MIN_REPORT_SECTIONS = 20        # canary for the column-scoped equipment groups: the
                                # vibration report's chunks carried a generic title
                                # until _mark_column_groups recovered the equipment
                                # name from a vertically merged column. 25 today.
REPORT_CANARY = "VB_Vibration_Report_SS1_2024"

_PUA = re.compile(r"[-]")
_COLN = re.compile(r"\bCol\d+\b")
# A pipe wedged between two word characters — the signature of prose being
# split into table cells, as opposed to a legitimate table delimiter.
_WORD_SPLIT_PIPE = re.compile(r"(?<=[A-Za-z])\s?\|\s?(?=[a-z])")

errors = 0
ids = set()
n = 0
docs = {}
coln_total = 0
pipe_total = 0
sections_by_doc = {}
with open(JSONL, encoding="utf-8") as f:
    for lineno, line in enumerate(f, 1):
        if not line.strip():
            continue
        n += 1
        try:
            c = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"line {lineno}: bad JSON: {e}")
            errors += 1
            continue
        missing = [k for k in REQUIRED if k not in c]
        if missing:
            print(f"line {lineno}: missing keys {missing}")
            errors += 1
        if c.get("char_count") != len(c.get("text", "")):
            print(f"line {lineno}: char_count {c.get('char_count')} != len(text) {len(c.get('text',''))}")
            errors += 1
        if len(c.get("text", "")) > MAX_CHUNK_CHARS:
            print(f"line {lineno}: chunk too big ({len(c['text'])} chars)")
            errors += 1
        if not c.get("text", "").strip():
            print(f"line {lineno}: empty text")
            errors += 1
        cid = c.get("chunk_id")
        if cid in ids:
            print(f"line {lineno}: duplicate chunk_id {cid}")
            errors += 1
        ids.add(cid)
        if not isinstance(c.get("tags"), list):
            print(f"line {lineno}: tags not a list")
            errors += 1

        text = c.get("text", "")
        doc = c.get("doc_id", "")
        docs[doc] = docs.get(doc, 0) + 1
        sections_by_doc.setdefault(doc, set()).add(c.get("section", ""))
        coln_total += len(_COLN.findall(text))
        pipe_total += len(_WORD_SPLIT_PIPE.findall(text))
        # Wingdings/Symbol glyphs extract as Private Use Area codepoints: a tick
        # becomes U+F0FC. Nothing downstream can read them — not the embedding
        # model, not the keyword index ([a-zA-Z]{3,}), not the LLM — while char
        # counts and OCR gates all look healthy. Data present and invisible.
        if _PUA.search(text):
            found = sorted({hex(ord(ch)) for ch in _PUA.findall(text)})[:4]
            print(f"line {lineno}: PUA glyphs in {doc} p.{c.get('page_num')} {found}")
            errors += 1

# ---- corpus-level checks ----------------------------------------------------
print(f"{n} chunks checked across {len(docs)} documents")

# 1. The KB is a PAIR. chunks_merged.jsonl and embeddings.npy must move together
#    and be committed together. They silently drifted for three sessions — 2,659
#    committed chunks against the ~2,429 the committed parser produced — because
#    build_kb.py only *prints* that embeddings are stale. A print is not a check.
try:
    import numpy as np
    emb = np.load(EMBEDDINGS, mmap_mode="r")
    if emb.shape[0] != n:
        print(f"PAIR MISMATCH: {n} chunks but embeddings.npy has {emb.shape[0]} rows "
              f"— rerun backend/generate_embeddings.py before committing")
        errors += 1
    want_dim = int(os.environ.get("GEMINI_EMBED_DIM", emb.shape[1]))
    if emb.shape[1] != want_dim:
        print(f"embedding dim {emb.shape[1]} != GEMINI_EMBED_DIM {want_dim}")
        errors += 1
    print(f"  pair: {n} chunks / {emb.shape[0]} vectors x {emb.shape[1]}d  ok")
except FileNotFoundError:
    print(f"embeddings.npy not found at {EMBEDDINGS}")
    errors += 1
except ImportError:
    print("  pair: SKIPPED (numpy unavailable)")

# 2. Every registered document produced at least one chunk. This replaces the
#    intent of build_kb's MIN_TOTAL_CHUNKS, which is a corpus-wide constant with
#    ~14 chunks of margin and would not notice a small document vanishing at all.
try:
    sys.path.insert(0, os.path.dirname(__file__))
    from doc_registry import REGISTRY
    registered = {d["doc_id"] for d in REGISTRY}
    missing_docs = registered - set(docs)
    unknown_docs = set(docs) - registered
    if missing_docs:
        print(f"REGISTERED BUT NOT IN KB ({len(missing_docs)}): {sorted(missing_docs)}")
        errors += 1
    if unknown_docs:
        print(f"IN KB BUT NOT REGISTERED ({len(unknown_docs)}): {sorted(unknown_docs)}")
        errors += 1
    if not missing_docs and not unknown_docs:
        print(f"  registry: all {len(registered)} documents present  ok")
except Exception as e:                                  # noqa: BLE001
    print(f"  registry: SKIPPED ({e})")

# 3. Structural properties bought by earlier sessions, held at their measured level.
for label, value, bound in (
    ("ColN placeholders", coln_total, MAX_COLN),
    ("word-split pipes", pipe_total, MAX_WORD_SPLIT_PIPES),
):
    if value > bound:
        print(f"{label.upper()}: {value} exceeds bound {bound}")
        errors += 1
    else:
        print(f"  {label}: {value} (bound {bound})  ok")

report_sections = len(sections_by_doc.get(REPORT_CANARY, ()))
if REPORT_CANARY in docs and report_sections < MIN_REPORT_SECTIONS:
    print(f"CANARY: {REPORT_CANARY} has {report_sections} distinct section titles "
          f"(< {MIN_REPORT_SECTIONS}) — equipment-group recovery may have regressed")
    errors += 1
elif REPORT_CANARY in docs:
    print(f"  canary: {REPORT_CANARY} {report_sections} section titles "
          f"(min {MIN_REPORT_SECTIONS})  ok")

# Deliberately NOT checked: "no document has >30% of its chunks under one section
# title". Measured before writing it — 8+ documents are legitimately at 100%,
# because a short instruction letter has exactly one section, and even among the
# 13 documents with 30+ chunks two sit at 100% and 89% for the same honest
# reason. There is no threshold that separates a generic title from a document
# with one subject, so the property is watched by the canary above instead.

print(f"\n{errors} error(s)")
sys.exit(1 if errors else 0)
