"""
run_eval.py — measure retrieval + fidelity quality of the KB, so we can prove
answer effectiveness does NOT drop as the KB grows. Run it before and after each
ingestion batch.

    set GEMINI_API_KEY=...          # optional: enables semantic retrieval; without
                                    # it, eval runs on keyword-only retrieval
    python ingest/eval/run_eval.py
    python ingest/eval/run_eval.py --k 8 --set ingest/eval/eval_set.jsonl

Metrics (per the plan's WS9):
  recall@k         did the expected document appear in the top-k retrieved chunks?
  MRR              1/rank of the first hit on the expected document
  value-retrieved  is the gold value present verbatim in the retrieved context?
                   (a value the model can only cite correctly if it is retrieved)
  guard-suppress   fed an answer containing the gold value AND a planted WRONG
                   value, does verify.guard_answer keep the right one and strip
                   the wrong one? (end-to-end test of the numeric hard guard)

No LLM generation is exercised here — these are deterministic retrieval + guard
checks, so the eval is free to run and stable across runs.
"""
import argparse
import json
import os
import sys
import time

# Import the deployed backend brain (backend/ has flat, top-level module names).
_BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
sys.path.insert(0, _BACKEND)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import load_env     # noqa: E402,F401  — must precede rag (embed.py reads env at import)
import rag          # noqa: E402
import verify       # noqa: E402

DEFAULT_SET = os.path.join(os.path.dirname(__file__), "eval_set.jsonl")


def load_set(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def value_in_context(value, ctx):
    """True if `value` is present verbatim (unit-normalized) in ctx."""
    return verify._compact(value) in verify._compact(ctx)


def guard_check(gold, wrong, ctx):
    """Feed a synthetic answer with both values; guard must keep gold and remove
    the wrong one. Success = gold still present in the cleaned answer AND the wrong
    value no longer appears (robust to the guard stripping a sub-token, e.g. it
    strips '120kg' out of a '120kg/cm²' planted value)."""
    answer = f"The correct value is {gold}. An incorrect claim would be {wrong}."
    clean, _ = verify.guard_answer(answer, ctx)
    kept_gold = verify._compact(gold) in verify._compact(clean)
    removed_wrong = verify._compact(wrong) not in verify._compact(clean)
    return kept_gold, removed_wrong


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default=DEFAULT_SET)
    ap.add_argument("--k", type=int, default=8)
    args = ap.parse_args()

    rag.init_kb()
    print(f"Retrieval mode: {rag.retrieval_mode()}  |  KB: {len(rag.chunks)} chunks\n")

    cases = load_set(args.set)
    n = len(cases)
    hits = 0
    mrr = 0.0
    val_total = val_ok = 0
    guard_total = guard_ok = 0

    # Pacing. With RERANK_ENABLED=1 the free flash-lite tier throttles a
    # back-to-back 60-case run: a first attempt logged `rerank(gemini) 429` on 31
    # of 60 queries, and with no Groq key those queries silently fell back to
    # plain hybrid order — a MIXED condition that reports a rerank-on figure it
    # never measured. Space the cases out so a rerank-on run is really one.
    sleep_s = float(os.environ.get("EVAL_SLEEP", "0"))

    for i, c in enumerate(cases):
        if sleep_s and i:
            time.sleep(sleep_s)
        q = c["question"]
        expect = c.get("expect_doc")
        results = rag.retrieve(q, k=args.k)
        doc_ids = [ch.get("doc_id") for _, ch in results]
        ctx = rag.build_context(results)

        rank = doc_ids.index(expect) + 1 if expect in doc_ids else 0
        hit = rank > 0
        hits += hit
        mrr += (1.0 / rank) if rank else 0.0

        line = f"[{'HIT ' if hit else 'MISS'}] {c['id']:18} rank={rank or '-'}"

        gv = c.get("gold_value")
        if gv:
            val_total += 1
            got = value_in_context(gv, ctx)
            val_ok += got
            line += f" | value '{gv}' {'retrieved' if got else 'MISSING'}"
            pw = c.get("planted_wrong")
            if pw:
                guard_total += 1
                kept, stripped = guard_check(gv, pw, ctx)
                ok = kept and stripped
                guard_ok += ok
                line += f" | guard {'OK' if ok else f'FAIL(keep={kept},strip={stripped})'}"
        print(line)

    print("\n" + "=" * 60)
    print(f"recall@{args.k}:      {hits}/{n} = {hits / n:.2f}")
    print(f"MRR:            {mrr / n:.3f}")
    if val_total:
        print(f"value-retrieved: {val_ok}/{val_total} = {val_ok / val_total:.2f}")
    if guard_total:
        print(f"guard-suppress:  {guard_ok}/{guard_total} = {guard_ok / guard_total:.2f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
