"""
feedback_to_eval.py — turn rated answers from the feedback Sheet into DRAFT
eval cases, so a confirmed wrong answer becomes a permanent regression test.

    1. In the feedback Sheet: File > Download > Comma-separated values (.csv)
    2. python ingest/eval/feedback_to_eval.py feedback.csv
    3. Review ingest/eval/feedback_candidates.jsonl: fill expect_doc / page /
       gold_value from the manual, then move the line into eval_set.jsonl.

Nothing here is trusted as ground truth. A 👎 says an answer was wrong, not what
the right one is — the `correction` a user typed is a lead to check against the
manual, which is why it lands in `notes` and never in `gold_value`.

By default only 👎 rows are drafted. `--up` also drafts 👍 rows as recall
checks against the document the answer cited first (still to be reviewed).
Rows already drafted (same id) are skipped, so re-running on a fresh export
only adds new ratings.
"""
import argparse
import csv
import json
import os

OUT = os.path.join(os.path.dirname(__file__), "feedback_candidates.jsonl")


def _case(row, rating):
    rid = (row.get("request_id") or row.get("message_id") or "").strip()
    sources = [s.strip() for s in (row.get("sources") or "").split(";") if s.strip()]
    first_doc = sources[0].split(" p.")[0] if sources else None
    notes = [f"FEEDBACK {rating} {row.get('timestamp', '')}".strip()]
    for field in ("reasons", "correction", "note", "provider"):
        if (row.get(field) or "").strip():
            notes.append(f"{field}: {row[field].strip()}")
    if sources:
        notes.append("retrieved: " + "; ".join(sources))
    notes.append("CANDIDATE — set expect_doc/expect_page/gold_value from the manual.")
    return {
        "id": f"fb-{rid[:10] or 'norid'}",
        "question": (row.get("question") or "").strip(),
        "coach_type": None,
        "oem": None,
        # A 👍 vouches for what it cited; a 👎 says nothing about the right doc.
        "expect_doc": first_doc if rating == "up" else None,
        "expect_clause": "",
        "expect_page": None,
        "gold_value": None,
        "planted_wrong": None,
        "notes": " | ".join(notes),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--up", action="store_true", help="also draft 👍 rows")
    args = ap.parse_args()

    seen = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            seen = {json.loads(l)["id"] for l in f if l.strip()}

    added = skipped = 0
    with open(args.csv_path, encoding="utf-8-sig", newline="") as f, \
            open(OUT, "a", encoding="utf-8") as out:
        for row in csv.DictReader(f):
            rating = (row.get("rating") or "").strip()
            if rating != "down" and not (args.up and rating == "up"):
                continue
            case = _case(row, rating)
            if not case["question"] or case["id"] in seen:
                skipped += 1
                continue
            seen.add(case["id"])
            out.write(json.dumps(case, ensure_ascii=False) + "\n")
            added += 1
    print(f"{added} candidate(s) added to {OUT} ({skipped} skipped: duplicate or no question)")


if __name__ == "__main__":
    main()
