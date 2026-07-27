"""
seed_eval.py — draft candidate eval cases from the KB with Gemini flash-lite, so
building an eval set for a new manual family is fast. Output is CANDIDATES ONLY:
a mechanical engineer must review each row (especially gold_value) before it goes
into eval_set.jsonl — an unreviewed gold value is worthless as ground truth.

    set GEMINI_API_KEY=...
    python ingest/eval/seed_eval.py --doc IRCAMTECH_WSP_Handbook --n 5
    python ingest/eval/seed_eval.py --n 2         # 2 per document, whole KB

Writes ingest/eval/eval_candidates.jsonl. Curate, then move good rows into
eval_set.jsonl and delete the rest.
"""
import argparse
import json
import os
import random
import re
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = os.path.dirname(__file__)
JSONL = os.path.normpath(os.path.join(_HERE, "..", "..", "backend", "data", "chunks_merged.jsonl"))
OUT = os.path.join(_HERE, "eval_candidates.jsonl")

API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = os.environ.get("GEMINI_SEED_MODEL", "gemini-3.1-flash-lite")
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

PROMPT = """You are helping build a test set for a railway maintenance assistant.
From the manual excerpt below, write ONE realistic question a NEW maintenance
technician would ask — phrased as a SYMPTOM or plain request, usually WITHOUT
naming the coach type or OEM (that is how they really ask). Then give the single
most important exact value the answer must contain, copied verbatim from the
excerpt (a voltage, air gap, pressure, torque, fault code, MCB rating, timing,
part number). If the excerpt has no such value, use null.

Return STRICT JSON only:
{"question": "...", "gold_value": "... or null"}

EXCERPT:
"""


def _gen(text):
    payload = {
        "contents": [{"role": "user", "parts": [{"text": PROMPT + text[:2000]}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 300,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }
    r = requests.post(URL, params={"key": API_KEY}, json=payload, timeout=60)
    if r.status_code != 200:
        print(f"  gen {r.status_code}: {r.text[:120]}")
        return None
    cands = r.json().get("candidates", [])
    if not cands:
        return None
    txt = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []))
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", help="only this doc_id")
    ap.add_argument("--n", type=int, default=3, help="candidates per document")
    args = ap.parse_args()
    if not API_KEY:
        raise SystemExit("GEMINI_API_KEY not set.")

    with open(JSONL, encoding="utf-8") as f:
        chunks = [json.loads(l) for l in f if l.strip()]

    by_doc = {}
    for c in chunks:
        if args.doc and c.get("doc_id") != args.doc:
            continue
        # prefer value-bearing chunks (tables, specs, fault codes)
        if re.search(r"\d", c.get("text", "")):
            by_doc.setdefault(c["doc_id"], []).append(c)

    written = 0
    with open(OUT, "w", encoding="utf-8") as out:
        for doc_id, cs in by_doc.items():
            for c in random.sample(cs, min(args.n, len(cs))):
                g = _gen(c.get("text", ""))
                if not g or not g.get("question"):
                    continue
                row = {
                    "id": f"{doc_id[:12]}-{written}",
                    "question": g["question"],
                    "coach_type": (c.get("coach_type") or [None])[0],
                    "oem": c.get("oem") or None,
                    "expect_doc": doc_id,
                    "expect_clause": c.get("section_num", ""),
                    "expect_page": c.get("page_num"),
                    "gold_value": g.get("gold_value") or None,
                    "planted_wrong": None,
                    "notes": "CANDIDATE — review gold_value against the manual before use.",
                }
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                written += 1
                print(f"  {row['id']}: {row['question'][:70]}")
    print(f"\nWrote {written} candidates to {OUT}. Curate before adding to eval_set.jsonl.")


if __name__ == "__main__":
    main()
