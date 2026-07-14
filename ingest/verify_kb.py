"""
verify_kb.py — schema validation of backend/data/chunks_merged.jsonl.
Run before committing a rebuilt KB. Exits nonzero on any violation.
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JSONL = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "backend", "data", "chunks_merged.jsonl"))

REQUIRED = ["chunk_id", "doc_id", "doc_type", "title", "source", "section",
            "section_num", "page_num", "chunk_index", "total_chunks_in_section",
            "tags", "oem", "text", "char_count"]
MAX_CHUNK_CHARS = 4000

errors = 0
ids = set()
n = 0
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

print(f"{n} chunks checked, {errors} errors")
sys.exit(1 if errors else 0)
