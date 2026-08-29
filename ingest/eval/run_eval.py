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


LEDGER = os.path.join(os.path.dirname(__file__), "results.tsv")
LEDGER_COLUMNS = [
    "timestamp", "commit", "k", "rerank", "recall", "mrr", "value_retrieved",
    "guard", "ctx_chars_mean", "cases", "status", "description",
]


def _git_commit():
    try:
        import subprocess
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(__file__), capture_output=True, text=True, timeout=5,
        ).stdout.strip() or "unknown"
    except Exception:                                       # noqa: BLE001
        return "unknown"


def append_ledger(row):
    """One row per gated run, appended to an untracked results.tsv.

    Four sessions of eval figures live only as prose tables on the wiki, one per
    session, so "has value-retrieved moved since July?" needs three pages
    re-read. Tab-separated because descriptions contain commas. The discarded
    runs matter as much as the kept ones — a status column with only successes
    in it cannot tell you whether the search is finding anything.
    """
    new = not os.path.exists(LEDGER)
    with open(LEDGER, "a", encoding="utf-8", newline="") as f:
        if new:
            f.write("\t".join(LEDGER_COLUMNS) + "\n")
        f.write("\t".join(str(row[c]) for c in LEDGER_COLUMNS) + "\n")


def absence_check(wrong, ctx):
    """An absence case: the KB does not hold this value, so the guard must strip it.

    Same machinery as guard_check with the gold half removed. Every other metric
    here assumes a value exists — recall@k and MRR need `expect_doc`,
    value-retrieved needs a `gold_value` that must be PRESENT — so the one path
    none of them can reach is the one where the honest answer is "not in these 97
    documents". That path is what this scores.

    Worth having on this corpus specifically: guard_answer compacts all retrieved
    chunks into a single haystack, so a value confirms if it appears anywhere. On
    1,775 Vande Bharat chunks against 192 Amrit Bharat, an Amrit Bharat question
    retrieves mostly VB material — so a failure here is cross-coach contamination
    caught in the act, not merely a missing suppression.
    """
    answer = f"The specified value is {wrong}."
    clean, _ = verify.guard_answer(answer, ctx)
    return verify._compact(wrong) not in verify._compact(clean)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default=DEFAULT_SET)
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--note", default="", help="description for the results.tsv row")
    ap.add_argument("--status", default="run",
                    help="run | keep | discard — discard a run that logged either 429")
    ap.add_argument("--no-ledger", action="store_true", help="skip the results.tsv append")
    args = ap.parse_args()

    rag.init_kb()
    print(f"Retrieval mode: {rag.retrieval_mode()}  |  KB: {len(rag.chunks)} chunks\n")

    cases = load_set(args.set)
    n = len(cases)
    hits = 0
    mrr = 0.0
    val_total = val_ok = 0
    guard_total = guard_ok = 0
    abs_total = abs_ok = 0
    retr_total = 0
    # value-retrieved is a substring test over the assembled context, and `k`
    # controls how big that context is — so the score rises with k on its own,
    # with no improvement in retrieval. Recording the denominator alongside the
    # numerator is what makes that visible in the ledger instead of looking like
    # a win. Same for anything else that widens context (the per-doc cap,
    # TOP_K_FINAL, disabling the reranker's pruning).
    ctx_chars = []

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
        ctx_chars.append(len(ctx))

        # An absence case has no right document, so it takes no part in recall@k
        # or MRR. Their denominator is the number of cases that name an
        # expect_doc, NOT len(cases) — otherwise adding absence cases would move
        # the four existing metrics and silently break comparability with every
        # figure recorded before them.
        if c.get("expect_absent"):
            abs_total += 1
            pw = c.get("planted_wrong")
            ok = absence_check(pw, ctx) if pw else False
            abs_ok += ok
            print(f"[ABS ] {c['id']:18} "
                  f"{'suppressed' if ok else f'LEAKED - {pw!r} survived the guard'}")
            continue

        retr_total += 1
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

    mean_ctx = sum(ctx_chars) // len(ctx_chars) if ctx_chars else 0
    recall = hits / retr_total if retr_total else 0.0
    mrr_v = mrr / retr_total if retr_total else 0.0
    val_v = val_ok / val_total if val_total else 0.0
    guard_v = guard_ok / guard_total if guard_total else 0.0

    print("\n" + "=" * 60)
    print(f"recall@{args.k}:      {hits}/{retr_total} = {recall:.2f}")
    print(f"MRR:            {mrr_v:.3f}")
    if val_total:
        print(f"value-retrieved: {val_ok}/{val_total} = {val_v:.2f}")
    if guard_total:
        print(f"guard-suppress:  {guard_ok}/{guard_total} = {guard_v:.2f}")
    if abs_total:
        print(f"absence-suppress: {abs_ok}/{abs_total} = {abs_ok / abs_total:.2f}"
              f"   (unsupported value stripped when the KB has no answer)")
    # The denominator, printed next to the numerator it can inflate.
    print(f"context:         k={args.k}, mean {mean_ctx:,} chars/query")
    print("=" * 60)

    if not args.no_ledger:
        append_ledger({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M"),
            "commit": _git_commit(),
            "k": args.k,
            "rerank": os.environ.get("RERANK_ENABLED", "0"),
            "recall": f"{recall:.4f}",
            "mrr": f"{mrr_v:.4f}",
            "value_retrieved": f"{val_v:.4f}" if val_total else "",
            "guard": f"{guard_v:.4f}" if guard_total else "",
            "ctx_chars_mean": mean_ctx,
            "cases": n,
            "status": args.status,
            "description": args.note.replace("\t", " ") or "(no note)",
        })
        print(f"logged to {os.path.relpath(LEDGER)} as status={args.status}")


if __name__ == "__main__":
    main()
